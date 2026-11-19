"""技術指標服務：取得含暖機期的歷史行情，計算指標，只回傳查詢區間內的結果。"""

from datetime import date, timedelta

from app.core.dates import taipei_today
from app.data_providers.base import Bar
from app.data_providers.http import Fetcher
from app.indicators import core
from app.indicators.spec import IndicatorSpec, parse_indicators, warmup_calendar_days
from app.schemas.common import Envelope, Metadata
from app.schemas.stock import IndicatorPoint, IndicatorResult, TechnicalIndicators
from app.services.history import PERIOD_DAYS, HistoryService, resolve_range
from app.services.securities import SecuritiesService

DEFAULT_PERIOD = "3mo"
DECIMALS = 4


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, DECIMALS)


def compute(spec: IndicatorSpec, bars: list[Bar], start: date) -> IndicatorResult:
    """bars 必須都有收盤價，且已含暖機期。只輸出 start 當天及之後的點。"""
    closes = [bar.close for bar in bars]  # type: ignore[misc]
    empty: core.Series = [None] * len(bars)
    if spec.kind == "SMA":
        main, signal, histogram = core.sma(closes, spec.params["window"]), empty, empty
    elif spec.kind == "RSI":
        main, signal, histogram = core.rsi(closes, spec.params["period"]), empty, empty
    else:
        main, signal, histogram = core.macd(closes, **spec.params)

    points = [
        IndicatorPoint(
            date=bar.trade_date,
            value=_round(main[i]),
            signal=_round(signal[i]),
            histogram=_round(histogram[i]),
        )
        for i, bar in enumerate(bars)
        if bar.trade_date >= start
    ]
    latest = points[-1] if points else None
    complete = latest is not None and latest.value is not None
    if spec.kind == "MACD":
        complete = complete and latest.signal is not None  # type: ignore[union-attr]

    return IndicatorResult(
        name=spec.name,
        kind=spec.kind,
        params=spec.params,
        definition=spec.definition,
        required_bars=spec.required_bars,
        available_bars=len(bars),
        status=(
            "ok"
            if complete
            else "insufficient_data"
            if len(bars) < spec.required_bars or not points
            else "undefined"
        ),
        latest=latest if complete else None,
        values=points,
    )


class IndicatorService:
    def __init__(self, fetcher: Fetcher, securities: SecuritiesService, history: HistoryService):
        self._fetcher = fetcher
        self._securities = securities
        self._history = history

    async def get_indicators(
        self,
        stock_id: str,
        *,
        indicators: list[str] | None,
        period: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> Envelope[TechnicalIndicators]:
        specs = parse_indicators(indicators)
        start, end = resolve_range(
            period,
            start_date,
            end_date,
            today=taipei_today(),
            max_days=self._fetcher.settings.max_history_days,
            default_days=PERIOD_DAYS[DEFAULT_PERIOD],
        )
        found = await self._securities.resolve(stock_id)

        # 往前多取暖機期：區間第一天的指標才有值，遞迴平滑的指標也才會收斂
        load_from = start - timedelta(days=warmup_calendar_days(specs))
        series = await self._history.load_bars(found, load_from, end)
        priced = [bar for bar in series.bars if bar.close is not None]
        in_range = [bar for bar in priced if bar.trade_date >= start]

        results = [compute(spec, priced, start) for spec in specs]

        warnings = [
            "指標以未還原收盤價計算，除權息、分割會造成價格跳空並影響指標數值。",
            "技術指標是對歷史價格的統計描述，不代表未來股價方向。",
        ]
        skipped = sum(1 for bar in series.bars if bar.close is None)
        if skipped:
            warnings.append(f"計算範圍內有 {skipped} 個交易日沒有成交，已略過這些日子。")
        if not in_range:
            warnings.append("此期間沒有可用的收盤價。")
        undefined = [r.name for r in results if r.status == "undefined"]
        if undefined:
            warnings.append(
                f"下列指標在最新一日數學上無定義（用來計算的資料範圍內價格沒有變動）："
                f"{'、'.join(undefined)}。"
            )
        # 遞迴平滑的指標要有足夠的暖機期才會收斂。算到區間第一天時用了幾筆資料：
        lead = len(priced) - len(in_range) + 1
        unsettled = [
            spec.name
            for spec, result in zip(specs, results, strict=True)
            if spec.kind != "SMA" and result.status == "ok" and lead < spec.warmup_bars
        ]
        if unsettled:
            warnings.append(
                f"區間之前可用的歷史資料不足以讓下列指標完全收斂（通常是上市櫃時間不夠久），"
                f"數值會受起算點影響，區間前段尤其明顯，請保守解讀：{'、'.join(unsettled)}。"
            )
        short = [r for r in results if r.status == "insufficient_data"]
        if short and in_range:
            listed = "、".join(f"{r.name}（需 {r.required_bars} 筆）" for r in short)
            warnings.append(
                f"可用的收盤價只有 {len(priced)} 筆，不足以算出下列指標的最新值：{listed}。"
                "通常是上市櫃時間不夠久。"
            )

        return Envelope[TechnicalIndicators](
            data=TechnicalIndicators(
                stock_id=stock_id,
                name=found.name,
                market=found.provider.market,
                start_date=start,
                end_date=end,
                latest_date=in_range[-1].trade_date if in_range else None,
                latest_close=in_range[-1].close if in_range else None,
                indicators=results,
            ),
            metadata=Metadata(
                source=series.source,
                data_date=in_range[-1].trade_date if in_range else None,
                retrieved_at=series.retrieved_at,
                data_type="historical",
                unit="MA、MACD：新台幣元；RSI：0–100",
            ),
            warnings=warnings,
        )
