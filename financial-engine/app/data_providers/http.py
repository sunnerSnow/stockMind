"""對外部資料來源的 HTTP 取用：逾時、有限次數重試、統一錯誤。"""

import asyncio
import logging
from typing import Any

import httpx

from app.core.config import Settings
from app.core.errors import UpstreamError

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    source: str,
    settings: Settings,
    params: dict[str, str] | None = None,
) -> Any:
    """GET 並解析 JSON。暫時性失敗會重試；最終失敗丟 UpstreamError。"""
    attempts = settings.http_retries + 1
    detail = "未知錯誤"
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, params=params, timeout=settings.http_timeout)
            if response.status_code in _RETRYABLE_STATUS:
                detail = f"HTTP {response.status_code}"
            elif response.status_code >= 400:
                # 4xx 重試也不會好，直接失敗
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
