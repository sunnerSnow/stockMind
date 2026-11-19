"""大盤概況：最近一個交易日的指數與市場成交資訊。"""

from app.core.errors import UpstreamError
from app.data_providers.http import Fetcher
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import IndexPoint, MarketSummary
from app.services import calc
from app.services.securities import AFTER_MARKET_NOTE, SecuritiesService

RECENT_DAYS = 10


class MarketService:
    def __init__(self, fetcher: Fetcher, securities: SecuritiesService):
        self._fetcher = fetcher
        self._securities = securities

    async def get_summary(self, market: str) -> Envelope[MarketSummary]:
        provider = self._securities.provider_for(market)
        fetched = await provider.index_days(self._fetcher)
        days = fetched.value
        if not days:
            raise UpstreamError(provider.openapi_source, "回傳的指數資料是空的")
        latest = days[-1]

        warnings = [AFTER_MARKET_NOTE]
        if latest.volume is None:
            warnings.append("此市場的來源未提供成交量、成交金額與筆數，相關欄位為 null。")
        if latest.open is None:
            warnings.append("此市場的來源未提供指數的開盤、最高、最低，相關欄位為 null。")

        return Envelope[MarketSummary](
            data=MarketSummary(
                market=provider.market,
                index_name=provider.index_name,
                trade_date=latest.trade_date,
                close=latest.close,
                change=latest.change,
                previous_close=calc.previous_close(latest.close, latest.change),
                change_percent=calc.change_percent(latest.close, latest.change),
                open=latest.open,
                high=latest.high,
                low=latest.low,
                volume=latest.volume,
                value=latest.value,
                transactions=latest.transactions,
                recent=[
                    IndexPoint(date=d.trade_date, close=d.close, change=d.change)
                    for d in days[-RECENT_DAYS:]
                ],
            ),
            metadata=Metadata(
                source=provider.openapi_source,
                data_date=latest.trade_date,
                retrieved_at=fetched.retrieved_at,
                data_type="after_market",
                unit="指數：點；volume：股；value：元",
            ),
            warnings=warnings,
        )
