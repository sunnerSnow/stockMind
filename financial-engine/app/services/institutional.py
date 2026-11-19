"""三大法人買賣超：逐日取得全市場報表，取出單一證券並計算累計與連續天數。"""

from datetime import date

from app.core.dates import taipei_today
from app.data_providers.base import Flow
from app.data_providers.http import Fetcher
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import (
    CumulativeNet,
    FlowModel,
    InstitutionalDay,
    InstitutionalFlow,
    InstitutionalSummary,
    Streak,
    Streaks,
)
from app.services import calc
from app.services.history import HistoryService, resolve_range
from app.services.securities import SecuritiesService

DEFAULT_DAYS = 14


def _flow(flow: Flow) -> FlowModel:
    return FlowModel(buy=flow.buy, sell=flow.sell, net=flow.net)


def summarize(days: list[InstitutionalDay]) -> InstitutionalSummary:
    reported = [d for d in days if d.reported]

    def nets(pick) -> list[int | None]:
        return [pick(d) if d.reported else None for d in days]

    series = {
        "foreign": nets(lambda d: d.foreign.net),
        "investment_trust": nets(lambda d: d.investment_trust.net),
        "dealer": nets(lambda d: d.dealer.net),
        "total": nets(lambda d: d.total_net),
    }
    streaks = {}
    for name, values in series.items():
        direction, count = calc.streak(values)
        streaks[name] = Streak(direction=direction, days=count)

    latest = days[-1] if days and days[-1].reported else None
    return InstitutionalSummary(
        trading_days=len(days),
        days_with_data=len(reported),
        cumulative_net=CumulativeNet(
            **{name: sum(v for v in values if v is not None) for name, values in series.items()}
        ),
        streaks=Streaks(**streaks),
        latest_alignment=(
            calc.alignment(
                [latest.foreign.net, latest.investment_trust.net, latest.dealer.net]  # type: ignore[union-attr]
            )
            if latest
            else None
        ),
    )


class InstitutionalService:
    def __init__(self, fetcher: Fetcher, securities: SecuritiesService, history: HistoryService):
        self._fetcher = fetcher
        self._securities = securities
        self._history = history

    async def get_flow(
        self, stock_id: str, *, start_date: date | None, end_date: date | None
    ) -> Envelope[InstitutionalFlow]:
        settings = self._fetcher.settings
        today = taipei_today()
        start, end = resolve_range(
            None,
            start_date,
            end_date,
            today=today,
            max_days=settings.max_flow_days,
            default_days=DEFAULT_DAYS,
        )
        found = await self._securities.resolve(stock_id)
        provider = found.provider

        # 交易日以這檔證券實際有行情的日子為準，不用日曆天推算
        bars = await self._history.load_bars(found, start, end)
        trading_dates = [b.trade_date for b in bars.bars]

        def empty(day: date) -> InstitutionalDay:
            return InstitutionalDay(
                date=day,
                reported=False,
                foreign=None,
                investment_trust=None,
                dealer=None,
                total_net=None,
            )

        days: list[InstitutionalDay] = []
        no_report: list[date] = []
        unlisted: list[date] = []
        retrieved_at = bars.retrieved_at
        for day in trading_dates:
            fetched = await provider.institutional_day(self._fetcher, day, final=day < today)
            retrieved_at = fetched.retrieved_at
            table = fetched.value
            if table is None:
                no_report.append(day)
                days.append(empty(day))
                continue
            row = table.get(stock_id)
            if row is None:
                unlisted.append(day)
                days.append(empty(day))
                continue
            days.append(
                InstitutionalDay(
                    date=day,
                    reported=True,
                    foreign=_flow(row.foreign),
                    investment_trust=_flow(row.investment_trust),
                    dealer=_flow(row.dealer),
                    total_net=row.total_net,
                )
            )

        # 期間最後幾天還沒有報表（通常是今天尚未公布）：不列入，連續天數以最近有報表的那天為準。
        # 夾在中間的缺口日則保留為沒有資料，連續天數算到缺口就停，不會跨過去。
        unpublished: list[date] = []
        while days and days[-1].date in no_report:
            unpublished.insert(0, days.pop().date)
        gaps = [d for d in no_report if d not in unpublished]

        warnings = ["買賣超是已發生的交易統計，不代表未來股價方向。"]
        if not trading_dates:
            warnings.append("此期間沒有交易日。")
        if unpublished:
            listed = "、".join(d.isoformat() for d in unpublished)
            warnings.append(f"以下交易日的三大法人資料尚未公布，未列入：{listed}。")
        if gaps:
            listed = "、".join(d.isoformat() for d in gaps)
            warnings.append(
                f"以下交易日來源沒有三大法人資料，該日數值為 null，"
                f"且不計入累計與連續天數：{listed}。"
            )
        if unlisted:
            listed = "、".join(d.isoformat() for d in unlisted)
            warnings.append(
                f"以下交易日的三大法人報表未列此證券（通常表示當日法人沒有買賣），"
                f"該日數值為 null，且不計入累計與連續天數：{listed}。"
            )

        return Envelope[InstitutionalFlow](
            data=InstitutionalFlow(
                stock_id=stock_id,
                name=found.name,
                market=provider.market,
                start_date=start,
                end_date=end,
                days=days,
                summary=summarize(days),
            ),
            metadata=Metadata(
                source=provider.site_source,
                data_date=days[-1].date if days else None,
                retrieved_at=retrieved_at,
                data_type="historical",
                unit="股",
            ),
            warnings=warnings,
        )
