"""證券索引：合併上市、上櫃的當日行情與公司基本資料，提供基本資料與最新可用行情。"""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from app.core.errors import StockNotFoundError, UpstreamError
from app.data_providers.base import (
    MarketProvider,
    Profile,
    Quote,
    guess_type_without_profile,
)
from app.data_providers.http import Fetched, Fetcher
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import StockInfo, StockPrice
from app.services import calc

AFTER_MARKET_NOTE = "這是最近一個交易日的盤後資料，不是即時行情。"


@dataclass(frozen=True)
class Resolved:
    """某個代號在某個市場查到的結果。"""

    provider: MarketProvider
    stock_id: str
    name: str
    quote: Fetched[Quote] | None
    quotes_date: date | None
    profile: Fetched[Profile] | None


class SecuritiesService:
    def __init__(self, fetcher: Fetcher, providers: Sequence[MarketProvider]):
        self._fetcher = fetcher
        self._providers = list(providers)

    def provider_for(self, market: str) -> MarketProvider:
        return next(p for p in self._providers if p.market == market)

    async def _lookup(self, provider: MarketProvider, stock_id: str) -> Resolved | None:
        quotes, profiles = await asyncio.gather(
            provider.daily_quotes(self._fetcher), provider.profiles(self._fetcher)
        )
        if not quotes.value.quotes and not profiles.value:
            # 兩份清單都是空的多半是來源異常，不能當成「查無此股」
            raise UpstreamError(provider.openapi_source, "回傳的證券清單是空的")
        quote = quotes.value.quotes.get(stock_id)
        profile = profiles.value.get(stock_id)
        if quote is None and profile is None:
            return None
        return Resolved(
            provider=provider,
            stock_id=stock_id,
            name=profile.name if profile else quote.name,  # type: ignore[union-attr]
            quote=Fetched(quote, quotes.retrieved_at) if quote else None,
            quotes_date=quotes.value.data_date,
            profile=Fetched(profile, profiles.retrieved_at) if profile else None,
        )

    async def resolve(self, stock_id: str) -> Resolved:
        results = await asyncio.gather(
            *(self._lookup(p, stock_id) for p in self._providers), return_exceptions=True
        )
        failures: list[UpstreamError] = []
        for result in results:
            if isinstance(result, UpstreamError):
                failures.append(result)
            elif isinstance(result, BaseException):
                raise result
            elif result is not None:
                return result
        if failures:
            # 有來源查不了，就不能斷定「查無此股」
            raise failures[0]
        raise StockNotFoundError(stock_id)

    async def get_stock_info(self, stock_id: str) -> Envelope[StockInfo]:
        found = await self.resolve(stock_id)
        profile = found.profile.value if found.profile else None
        security_type = "stock" if profile else guess_type_without_profile(stock_id)
        warnings = []
        if security_type == "other":
            warnings.append("此代號不在公司基本資料內，無法判定證券類別，也沒有產業與上市櫃日期。")
        origin = found.profile or found.quote
        assert origin is not None
        return Envelope[StockInfo](
            data=StockInfo(
                stock_id=stock_id,
                name=found.name,
                full_name=profile.full_name if profile else None,
                market=found.provider.market,
                security_type=security_type,
                industry_code=profile.industry_code if profile else None,
                listing_date=profile.listing_date if profile else None,
            ),
            metadata=Metadata(
                source=found.provider.openapi_source,
                data_date=found.quotes_date,
                retrieved_at=origin.retrieved_at,
                data_type="reference",
            ),
            warnings=warnings,
        )

    async def get_stock_price(self, stock_id: str) -> Envelope[StockPrice]:
        found = await self.resolve(stock_id)
        warnings = [AFTER_MARKET_NOTE]
        if found.quote is None:
            # 在公司基本資料內、但不在當日行情清單
            warnings.append("最近一個交易日的行情清單沒有這檔證券，可能是暫停交易。")
            quote, retrieved_at = None, found.profile.retrieved_at  # type: ignore[union-attr]
        else:
            quote, retrieved_at = found.quote.value, found.quote.retrieved_at
            if quote.close is None:
                warnings.append("這檔證券在該交易日沒有成交，價格欄位為 null。")
            elif quote.change is None:
                warnings.append("來源未提供可比較的漲跌價差（例如除權息日），漲跌相關欄位為 null。")

        close = quote.close if quote else None
        change = quote.change if quote else None
        return Envelope[StockPrice](
            data=StockPrice(
                stock_id=stock_id,
                name=found.name,
                market=found.provider.market,
                trade_date=found.quotes_date,
                open=quote.open if quote else None,
                high=quote.high if quote else None,
                low=quote.low if quote else None,
                close=close,
                change=change,
                previous_close=calc.previous_close(close, change),
                change_percent=calc.change_percent(close, change),
                volume=quote.volume if quote else None,
                value=quote.value if quote else None,
                transactions=quote.transactions if quote else None,
            ),
            metadata=Metadata(
                source=found.provider.openapi_source,
                data_date=found.quotes_date,
                retrieved_at=retrieved_at,
                data_type="after_market",
                unit="價格：新台幣元；volume：股；value：元",
            ),
            warnings=warnings,
        )
