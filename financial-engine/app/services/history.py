"""歷史行情：把逐月的來源資料接成指定期間的日 K。"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.core.dates import taipei_today
from app.core.errors import InvalidRangeError
from app.data_providers.base import Bar
from app.data_providers.http import Fetcher
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import PriceBar, StockHistory
from app.services.securities import Resolved, SecuritiesService

PERIOD_DAYS = {"5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366}
DEFAULT_PERIOD = "1mo"


def resolve_range(
    period: str | None,
    start_date: date | None,
    end_date: date | None,
    *,
    today: date,
    max_days: int,
    default_days: int,
) -> tuple[date, date]:
    """把 period 或起訖日期換成實際範圍，並檢查上限。"""
    if period is not None and (start_date is not None or end_date is not None):
        raise InvalidRangeError("period 與 start_date／end_date 只能擇一")
    if period is not None:
        if period not in PERIOD_DAYS:
            raise InvalidRangeError(f"period 只支援 {'、'.join(PERIOD_DAYS)}")
        start, end = today - timedelta(days=PERIOD_DAYS[period]), today
    elif start_date is None and end_date is None:
        start, end = today - timedelta(days=default_days), today
    elif start_date is None:
        raise InvalidRangeError("指定 end_date 時也要給 start_date")
    else:
        start, end = start_date, end_date or today

    if start > today:
        raise InvalidRangeError("start_date 不能是未來的日期")
    if start > end:
        raise InvalidRangeError("start_date 不能晚於 end_date")
    end = min(end, today)
    if (end - start).days > max_days:
        raise InvalidRangeError(f"查詢範圍最多 {max_days} 天，請縮小範圍")
    return start, end


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    months, year, month = [], start.year, start.month
    while (year, month) <= (end.year, end.month):
        months.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


@dataclass(frozen=True)
class BarSeries:
    bars: list[Bar]
    # 範圍內最新一段資料的擷取時間；較舊的月份已定案，擷取時間不影響新舊判斷
    retrieved_at: str
    source: str


class HistoryService:
    def __init__(self, fetcher: Fetcher, securities: SecuritiesService):
        self._fetcher = fetcher
        self._securities = securities

    async def load_bars(self, found: Resolved, start: date, end: date) -> BarSeries:
        """取得範圍內的日 K，依日期排序且不重複。逐月向來源請求（受節流限制）。"""
        today = taipei_today()
        by_date: dict[date, Bar] = {}
        retrieved_at = ""
        for year, month in months_between(start, end):
            final = (year, month) < (today.year, today.month)
            fetched = await found.provider.month_bars(
                self._fetcher, found.stock_id, year, month, final=final
            )
            retrieved_at = fetched.retrieved_at
            for bar in fetched.value:
                if start <= bar.trade_date <= end:
                    by_date[bar.trade_date] = bar
        bars = [by_date[d] for d in sorted(by_date)]
        return BarSeries(bars=bars, retrieved_at=retrieved_at, source=found.provider.site_source)

    async def get_history(
        self,
        stock_id: str,
        *,
        period: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> Envelope[StockHistory]:
        settings = self._fetcher.settings
        start, end = resolve_range(
            period,
            start_date,
            end_date,
            today=taipei_today(),
            max_days=settings.max_history_days,
            default_days=PERIOD_DAYS[DEFAULT_PERIOD],
        )
        found = await self._securities.resolve(stock_id)
        series = await self.load_bars(found, start, end)

        warnings = ["價格為未還原股價，除權息、分割前後不能直接比較。"]
        if not series.bars:
            warnings.append("此期間沒有交易資料。")
        if any(bar.close is None for bar in series.bars):
            warnings.append("部分交易日沒有成交，價格欄位為 null。")
        if found.provider.market == "TPEx":
            warnings.append(
                "上櫃歷史資料的來源單位是張與仟元，"
                "換算後 volume 精度為 1,000 股、value 精度為 1,000 元。"
            )

        return Envelope[StockHistory](
            data=StockHistory(
                stock_id=stock_id,
                name=found.name,
                market=found.provider.market,
                start_date=start,
                end_date=end,
                count=len(series.bars),
                bars=[
                    PriceBar(
                        date=b.trade_date,
                        open=b.open,
                        high=b.high,
                        low=b.low,
                        close=b.close,
                        change=b.change,
                        volume=b.volume,
                        value=b.value,
                        transactions=b.transactions,
                    )
                    for b in series.bars
                ],
            ),
            metadata=Metadata(
                source=series.source,
                data_date=series.bars[-1].trade_date if series.bars else None,
                retrieved_at=series.retrieved_at,
                data_type="historical",
                unit="價格：新台幣元；volume：股；value：元",
            ),
            warnings=warnings,
        )
