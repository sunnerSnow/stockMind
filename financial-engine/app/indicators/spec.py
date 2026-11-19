"""指標名稱的解析與定義。名稱是對外的介面：MA20、RSI14、MACD。"""

import math
import re
from dataclasses import dataclass
from typing import Literal

from app.core.errors import InvalidRangeError

Kind = Literal["SMA", "RSI", "MACD"]

DEFAULT_INDICATORS = ("MA5", "MA20", "RSI14", "MACD")
MAX_INDICATORS = 8
MA_RANGE = (2, 120)
RSI_RANGE = (2, 30)
MACD_PARAMS = {"fast": 12, "slow": 26, "signal": 9}

# RSI、MACD 用的是遞迴平滑，起算值的影響每多一筆資料就乘上 (1 − α) 衰減一次。
# 起算後再多取下列筆數，起算值的殘餘權重會低於千分之一，不同起點算出的結果才會一致。
# MACD：最慢的是 EMA26（α = 2/27），(25/27)^93 ≈ 0.001，取 100。
_MACD_SETTLE_BARS = 100
# RSI：Wilder 平滑的 α = 1/N，(1 − 1/N)^(7N) ≈ e^-7 ≈ 0.001。
_RSI_SETTLE_FACTOR = 7

_NAME = re.compile(r"^(MA|RSI)(\d{1,3})$")


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    kind: Kind
    params: dict[str, int]
    definition: str
    # 最少要有幾筆收盤價，最新一日才算得出完整的值
    required_bars: int
    # 為了讓查詢區間第一天就有穩定的值，要往前多取幾筆
    warmup_bars: int


def parse_indicator(raw: str) -> IndicatorSpec:
    name = raw.strip().upper()
    if name == "MACD":
        p = MACD_PARAMS
        required = p["slow"] + p["signal"] - 1
        return IndicatorSpec(
            name="MACD",
            kind="MACD",
            params=dict(p),
            definition=(
                f"DIF = 收盤價 EMA{p['fast']} − EMA{p['slow']}；"
                f"訊號線 = DIF 的 EMA{p['signal']}；柱狀體 = DIF − 訊號線（不乘以 2）。"
                "EMA 以前 N 筆的簡單平均起算，平滑係數 2 ÷ (N + 1)。"
            ),
            required_bars=required,
            warmup_bars=required + _MACD_SETTLE_BARS,
        )

    match = _NAME.match(name)
    if not match:
        raise InvalidRangeError(
            f"不支援的指標「{raw.strip()[:20]}」。"
            "可用：MA 加期數（如 MA20）、RSI 加期數（如 RSI14）、MACD"
        )
    prefix, n = match.group(1), int(match.group(2))
    low, high = MA_RANGE if prefix == "MA" else RSI_RANGE
    if not low <= n <= high:
        raise InvalidRangeError(f"{prefix} 的期數需在 {low} 到 {high} 之間，收到 {n}")

    if prefix == "MA":
        return IndicatorSpec(
            name=f"MA{n}",
            kind="SMA",
            params={"window": n},
            definition=f"最近 {n} 個交易日收盤價的簡單算術平均。",
            required_bars=n,
            warmup_bars=n,
        )
    return IndicatorSpec(
        name=f"RSI{n}",
        kind="RSI",
        params={"period": n},
        definition=(
            f"Wilder 平滑法的 {n} 日 RSI：以前 {n} 個漲跌的簡單平均起算，"
            f"之後 平均 = (前一日平均 × {n - 1} + 當日值) ÷ {n}；"
            "RSI = 100 − 100 ÷ (1 + 平均漲幅 ÷ 平均跌幅)。"
        ),
        required_bars=n + 1,
        warmup_bars=n + 1 + _RSI_SETTLE_FACTOR * n,
    )


def parse_indicators(raw: list[str] | None) -> list[IndicatorSpec]:
    """接受重複的參數或逗號分隔；去除重複並保留順序。"""
    names = [part for item in (raw or []) for part in item.split(",") if part.strip()]
    specs: dict[str, IndicatorSpec] = {}
    for name in names or DEFAULT_INDICATORS:
        spec = parse_indicator(name)
        specs.setdefault(spec.name, spec)
    if len(specs) > MAX_INDICATORS:
        raise InvalidRangeError(f"一次最多查 {MAX_INDICATORS} 個指標")
    return list(specs.values())


def warmup_calendar_days(specs: list[IndicatorSpec]) -> int:
    """把需要的暖機筆數換成要往前多取的日曆天數。

    一年約 245 個交易日，另加 30 天緩衝以涵蓋農曆春節這類長假。
    """
    bars = max(spec.warmup_bars for spec in specs)
    return math.ceil(bars * 365 / 245) + 30
