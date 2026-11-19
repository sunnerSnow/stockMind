"""技術指標的計算正確性。

兩種驗證：一是可以手算的小例子；二是用 pandas 以另一種寫法算出同一個定義，
對一段較長的序列逐點比對。pandas 只在測試中使用。
"""

import math

import pandas as pd
import pytest

from app.indicators import core
from tests.conftest import synthetic_closes

CLOSES = synthetic_closes(200)


def approx(expected: list[float | None]):
    return [None if v is None else pytest.approx(v, abs=1e-9) for v in expected]


# --- 手算 ---


def test_sma_by_hand():
    assert core.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]
    assert core.sma([10, 20], 1) == [10.0, 20.0]


def test_sma_with_too_few_values_has_no_value():
    assert core.sma([1, 2], 3) == [None, None]
    assert core.sma([], 5) == []


def test_ema_by_hand():
    # window 3 → α = 0.5；起算值是前三筆平均 2
    # 第 4 筆：2 + 0.5 × (4 − 2) = 3；第 5 筆：3 + 0.5 × (5 − 3) = 4
    assert core.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_skips_leading_none():
    assert core.ema([None, None, 1, 2, 3, 4], 3) == [None, None, None, None, 2.0, 3.0]
    assert core.ema([None, 1, 2], 3) == [None, None, None]


def test_ema_rejects_gap_inside_data():
    with pytest.raises(ValueError):
        core.ema([1, None, 3, 4], 2)


def test_rsi_by_hand():
    # period 2；漲跌依序為 +1、−1、+2
    # 起算：平均漲幅 0.5、平均跌幅 0.5 → RS = 1 → RSI = 50
    # 下一筆：平均漲幅 (0.5 × 1 + 2) ÷ 2 = 1.25、平均跌幅 (0.5 × 1 + 0) ÷ 2 = 0.25
    #        → RS = 5 → RSI = 100 − 100 ÷ 6 = 83.3333…
    result = core.rsi([10, 11, 10, 12], 2)
    assert result[:2] == [None, None]
    assert result[2] == pytest.approx(50.0)
    assert result[3] == pytest.approx(100 - 100 / 6)


def test_rsi_needs_period_plus_one_values():
    assert core.rsi([1, 2, 3], 3) == [None, None, None]
    assert core.rsi([1, 2, 3, 4], 3)[3] == 100.0


def test_rsi_extremes():
    assert core.rsi([1, 2, 3, 4, 5], 2)[2:] == [100.0, 100.0, 100.0]  # 只漲不跌
    assert core.rsi([5, 4, 3, 2, 1], 2)[2:] == [0.0, 0.0, 0.0]  # 只跌不漲
    assert core.rsi([7, 7, 7, 7], 2) == [None, None, None, None]  # 完全沒動：無定義


def test_macd_by_hand():
    # fast 2（α = 2/3）、slow 3（α = 1/2）、signal 2（α = 2/3），輸入 1…6
    # EMA2：起算 1.5，之後 2.5、3.5、4.5、5.5
    # EMA3：起算 2，之後 3、4、5
    # DIF（自第 3 筆起）：2.5 − 2 = 0.5，之後都是 0.5
    # 訊號線：前兩個 DIF 的平均 0.5 起算，之後維持 0.5；柱狀體為 0
    dif, signal, histogram = core.macd([1, 2, 3, 4, 5, 6], fast=2, slow=3, signal=2)
    assert dif == approx([None, None, 0.5, 0.5, 0.5, 0.5])
    assert signal == approx([None, None, None, 0.5, 0.5, 0.5])
    assert histogram == approx([None, None, None, 0.0, 0.0, 0.0])


def test_macd_first_values_appear_at_documented_positions():
    dif, signal, histogram = core.macd(CLOSES, fast=12, slow=26, signal=9)
    assert dif[24] is None and dif[25] is not None  # 第 26 筆起
    assert signal[32] is None and signal[33] is not None  # 第 34 筆起
    assert histogram[33] == pytest.approx(dif[33] - signal[33])


def test_macd_requires_fast_below_slow():
    with pytest.raises(ValueError):
        core.macd([1.0] * 50, fast=26, slow=12, signal=9)


@pytest.mark.parametrize("window", [0, -1])
def test_non_positive_window_is_rejected(window):
    for fn in (core.sma, core.ema, core.rsi):
        with pytest.raises(ValueError):
            fn([1.0, 2.0, 3.0], window)


# --- 與 pandas 交叉比對 ---


def to_list(series: pd.Series) -> list[float | None]:
    return [None if math.isnan(v) else float(v) for v in series]


def pandas_ema(values: pd.Series, window: int) -> pd.Series:
    """以前 window 筆的平均起算的 EMA，用 pandas 的遞迴式重算一次。"""
    first = values.first_valid_index()
    seeded = pd.Series(float("nan"), index=values.index)
    seed_at = first + window - 1
    if seed_at >= len(values):
        return seeded
    seeded.iloc[seed_at] = values.iloc[first : seed_at + 1].mean()
    seeded.iloc[seed_at + 1 :] = values.iloc[seed_at + 1 :]
    return seeded.ewm(alpha=2 / (window + 1), adjust=False).mean()


@pytest.mark.parametrize("window", [5, 20, 60])
def test_sma_matches_pandas(window):
    expected = to_list(pd.Series(CLOSES).rolling(window).mean())
    assert core.sma(CLOSES, window) == approx(expected)


@pytest.mark.parametrize("window", [9, 12, 26])
def test_ema_matches_pandas(window):
    assert core.ema(CLOSES, window) == approx(to_list(pandas_ema(pd.Series(CLOSES), window)))


@pytest.mark.parametrize("period", [6, 14])
def test_rsi_matches_pandas(period):
    delta = pd.Series(CLOSES).diff()
    gain, loss = delta.clip(lower=0), (-delta).clip(lower=0)

    def wilder(series: pd.Series) -> pd.Series:
        seeded = pd.Series(float("nan"), index=series.index)
        seeded.iloc[period] = series.iloc[1 : period + 1].mean()
        seeded.iloc[period + 1 :] = series.iloc[period + 1 :]
        return seeded.ewm(alpha=1 / period, adjust=False).mean()

    expected = 100 - 100 / (1 + wilder(gain) / wilder(loss))
    assert core.rsi(CLOSES, period) == approx(to_list(expected))


def test_macd_matches_pandas():
    closes = pd.Series(CLOSES)
    dif = pandas_ema(closes, 12) - pandas_ema(closes, 26)
    signal = pandas_ema(dif, 9)
    ours = core.macd(CLOSES, fast=12, slow=26, signal=9)
    assert ours[0] == approx(to_list(dif))
    assert ours[1] == approx(to_list(signal))
    assert ours[2] == approx(to_list(dif - signal))


# --- 暖機筆數是否足夠 ---


@pytest.mark.parametrize(
    ("name", "tolerance"),
    [("RSI14", 0.02), ("RSI30", 0.02), ("MACD", 0.02)],
)
def test_documented_warmup_makes_result_independent_of_start(name, tolerance):
    """多取規定的暖機筆數後，從不同起點算出的最新值應該一致。"""
    from app.indicators.spec import parse_indicator

    spec = parse_indicator(name)
    long = synthetic_closes(600)
    short = long[-spec.warmup_bars :]

    def latest(values: list[float]) -> float:
        if spec.kind == "RSI":
            return core.rsi(values, spec.params["period"])[-1]
        return core.macd(values, **spec.params)[1][-1]  # 訊號線收斂最慢

    assert latest(short) == pytest.approx(latest(long), abs=tolerance)
