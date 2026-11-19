"""對外部資料來源的 HTTP 取用：逾時、有限次數重試、節流、快取、統一錯誤。"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.core.dates import taipei_timestamp
from app.core.errors import UpstreamError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MEMORY_LIMIT = 512

Validator = Callable[[Any], Any]


@dataclass(frozen=True)
class Fetched[T]:
    """一份資料加上它實際從來源擷取的時間（快取命中時是當初擷取的時間）。"""

    value: T
    retrieved_at: str

    def map[U](self, fn: Callable[[T], U]) -> "Fetched[U]":
        return Fetched(fn(self.value), self.retrieved_at)


class Fetcher:
    """所有對外請求的唯一出口。

    - ttl：回應在記憶體內可重用的秒數。
    - persist：資料已定案（過去的月份或交易日）時設為 True，會另存磁碟，重啟後仍可用。
    - persist_when：再依回應內容決定要不要存磁碟。「查無資料」可能只是來源暫時沒資料，
      永久存下來之後就再也查不到，所以這類回應只留在記憶體。
    - throttle：對交易所網站的請求要設為 True，同一主機的請求會排隊並保持最小間隔。
    - validate：檢查回應結構，不符時丟 UpstreamError；通過檢查的回應才會被快取。
    """

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self._client = client
        self.settings = settings
        self._memory: dict[str, tuple[float, Fetched[Any]]] = {}
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._disk = Path(settings.cache_dir) if settings.cache_dir else None

    async def get_json(
        self,
        url: str,
        *,
        source: str,
        params: dict[str, str] | None = None,
        ttl: float,
        persist: bool = False,
        throttle: bool = False,
        validate: Validator | None = None,
        persist_when: Callable[[Any], bool] | None = None,
    ) -> Fetched[Any]:
        key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
        lock = self._key_locks.setdefault(key, asyncio.Lock())
        try:
            async with lock:
                cached = self._memory.get(key)
                if cached and cached[0] > time.monotonic():
                    return cached[1]

                if persist and self._disk:
                    stored = await asyncio.to_thread(self._read_disk, key)
                    if stored is not None:
                        self._remember(key, stored, ttl)
                        return stored

                payload = await self._request(url, params, source, throttle)
                if validate:
                    validate(payload)
                fetched = Fetched(payload, taipei_timestamp())
                self._remember(key, fetched, ttl)
                if persist and self._disk and (persist_when is None or persist_when(payload)):
                    await asyncio.to_thread(self._write_disk, key, fetched)
                return fetched
        finally:
            if not lock.locked():
                self._key_locks.pop(key, None)

    # --- 請求 ---

    async def _request(
        self, url: str, params: dict[str, str] | None, source: str, throttle: bool
    ) -> Any:
        settings = self.settings
        attempts = settings.http_retries + 1
        detail = "未知錯誤"
        for attempt in range(1, attempts + 1):
            if throttle:
                await self._wait_turn(urlsplit(url).netloc)
            try:
                response = await self._client.get(url, params=params, timeout=settings.http_timeout)
                if response.status_code in _RETRYABLE_STATUS:
                    detail = f"HTTP {response.status_code}"
                elif response.status_code >= 300:
                    # 3xx（多半是被導去維護頁或封鎖頁）與 4xx 重試也不會好，直接失敗
                    raise UpstreamError(source, f"HTTP {response.status_code}")
                else:
                    try:
                        return response.json()
                    except ValueError:
                        raise UpstreamError(source, "回傳內容不是有效的 JSON") from None
            except httpx.TimeoutException:
                detail = "連線逾時"
            except httpx.TransportError as exc:
                detail = f"連線失敗（{type(exc).__name__}）"

            logger.warning("fetch %s 第 %d/%d 次失敗：%s", url, attempt, attempts, detail)
            if attempt < attempts:
                await asyncio.sleep(settings.http_backoff * 2 ** (attempt - 1))

        raise UpstreamError(source, detail)

    async def _wait_turn(self, host: str) -> None:
        async with self._host_locks.setdefault(host, asyncio.Lock()):
            wait = self._host_last.get(host, 0.0) + self.settings.throttle_interval
            delay = wait - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._host_last[host] = time.monotonic()

    # --- 快取 ---

    def _remember(self, key: str, fetched: Fetched[Any], ttl: float) -> None:
        if ttl <= 0:
            return
        now = time.monotonic()
        if len(self._memory) >= _MEMORY_LIMIT:
            for stale in [k for k, (expires, _) in self._memory.items() if expires <= now]:
                del self._memory[stale]
            while len(self._memory) >= _MEMORY_LIMIT:
                del self._memory[next(iter(self._memory))]
        self._memory[key] = (now + ttl, fetched)

    def _disk_path(self, key: str) -> Path:
        assert self._disk is not None
        return self._disk / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    def _read_disk(self, key: str) -> Fetched[Any] | None:
        path = self._disk_path(key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            logger.warning("磁碟快取 %s 無法讀取，改為重新擷取", path.name)
            return None
        # 檔名是雜湊，內容再比對一次 key，避免碰撞或檔案被換掉
        if not isinstance(entry, dict) or entry.get("key") != key or "payload" not in entry:
            return None
        if not isinstance(entry.get("retrieved_at"), str):
            return None
        return Fetched(entry["payload"], entry["retrieved_at"])

    def _write_disk(self, key: str, fetched: Fetched[Any]) -> None:
        path = self._disk_path(key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            entry = {"key": key, "retrieved_at": fetched.retrieved_at, "payload": fetched.value}
            tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
        except OSError:
            # 快取寫不進去不該讓查詢失敗
            logger.warning("磁碟快取 %s 寫入失敗", path.name, exc_info=True)
