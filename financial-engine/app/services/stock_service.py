"""股票基本資料服務：合併上市、上櫃清單，並以記憶體快取減少對官方來源的請求。"""

import asyncio
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.core.dates import taipei_timestamp
from app.core.errors import StockNotFoundError, UpstreamError
from app.data_providers.base import SecuritiesProvider, SecuritiesSnapshot
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import StockInfo

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    snapshot: SecuritiesSnapshot
    retrieved_at: str
    expires_at: float


class StockService:
    def __init__(
        self,
        client: httpx.AsyncClient,
        providers: Sequence[SecuritiesProvider],
        settings: Settings,
    ):
        self._client = client
        self._providers = list(providers)
        self._settings = settings
        self._cache: dict[str, _CacheEntry] = {}
        self._locks = {p.source: asyncio.Lock() for p in self._providers}

    async def _snapshot(self, provider: SecuritiesProvider) -> _CacheEntry:
        async with self._locks[provider.source]:
            entry = self._cache.get(provider.source)
            if entry and entry.expires_at > time.monotonic():
                return entry
            snapshot = await provider.fetch_securities(self._client, self._settings)
            if not snapshot.records:
                # 空清單多半是來源異常；不快取，也不把它當成「查無此股」
                raise UpstreamError(provider.source, "回傳的證券清單是空的")
            entry = _CacheEntry(
                snapshot=snapshot,
                retrieved_at=taipei_timestamp(),
                expires_at=time.monotonic() + self._settings.securities_ttl,
            )
            self._cache[provider.source] = entry
            return entry

    async def get_stock_info(self, stock_id: str) -> Envelope[StockInfo]:
        results = await asyncio.gather(
            *(self._snapshot(p) for p in self._providers), return_exceptions=True
        )

        failures: list[UpstreamError] = []
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, UpstreamError):
                failures.append(result)
                continue
            if isinstance(result, BaseException):
                raise result
            record = result.snapshot.records.get(stock_id)
            if record is None:
                continue
            warnings = []
            if record.security_type == "other":
                warnings.append(
                    "此代號不在公司基本資料內，無法判定證券類別，也沒有產業與上市櫃日期。"
                )
            return Envelope[StockInfo](
                data=StockInfo(
                    stock_id=record.stock_id,
                    name=record.name,
                    full_name=record.full_name,
                    market=record.market,
                    security_type=record.security_type,
                    industry_code=record.industry_code,
                    listing_date=record.listing_date,
                ),
                metadata=Metadata(
                    source=provider.source,
                    data_date=result.snapshot.data_date,
                    retrieved_at=result.retrieved_at,
                    data_type="reference",
                ),
                warnings=warnings,
            )

        if failures:
            # 有來源查不了，就不能斷定「查無此股」
            raise failures[0]
        raise StockNotFoundError(stock_id)
