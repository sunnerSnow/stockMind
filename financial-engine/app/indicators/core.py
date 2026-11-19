"""技術指標的計算。純函式：輸入一串由舊到新的數值，輸出等長的結果。

還沒有足夠資料可算的位置一律是 None，不補值、不外插。
每個函式的公式與起算方式都寫在說明裡，因為同名指標在不同軟體的起算方式不盡相同，
數值會有些微差異。
"""

from collections.abc import Sequence

Series = list[float | None]


def sma(values: Sequence[float], window: int) -> Series:
    """簡單移動平均：最近 window 筆的算術平均。第 window 筆起有值。"""
    _check_window(window)
    out: Series = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def ema(values: Sequence[float | None], window: int) -> Series:
    """指數移動平均，平滑係數 α = 2 ÷ (window + 1)。

    起算值是前 window 筆的簡單平均，之後 EMA = 前一日 EMA + α × (當日值 − 前一日 EMA)。
    輸入開頭可以有 None（例如拿另一個指標的結果再平滑），從第一個有值的位置起算。
    """
    _check_window(window)
    out: Series = [None] * len(values)
    start = next((i for i, v in enumerate(values) if v is not None), len(values))
    seed_at = start + window - 1
    if seed_at >= len(values):
        return out
    body = values[start:]
    if any(v is None for v in body):
        raise ValueError("ema 的輸入在第一個有值的位置之後不能再有 None")

    alpha = 2 / (window + 1)
    current = sum(body[:window]) / window  # type: ignore[arg-type]
    out[seed_at] = current
    for i in range(seed_at + 1, len(values)):
        current += alpha * (values[i] - current)  # type: ignore[operator]
        out[i] = current
    return out


def rsi(values: Sequence[float], period: int) -> Series:
    """相對強弱指標（Wilder 平滑法）。第 period + 1 筆起有值。

    先算每日漲跌；第一個平均漲幅／平均跌幅是前 period 個漲跌的簡單平均，
    之後 平均 = (前一日平均 × (period − 1) + 當日值) ÷ period。
    RSI = 100 − 100 ÷ (1 + 平均漲幅 ÷ 平均跌幅)。
    平均跌幅為 0 時：有漲幅則 RSI 為 100；漲跌幅都是 0（價格完全沒動）則無定義，回 None。
    """
    _check_window(period)
    out: Series = [None] * len(values)
    if len(values) <= period:
        return out

    gains, losses = [], []
    for prev, cur in zip(values, values[1:], strict=False):
        delta = cur - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i + 1] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float | None:
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else None
    return 100 - 100 / (1 + avg_gain / avg_loss)


def macd(
    values: Sequence[float], fast: int, slow: int, signal: int
) -> tuple[Series, Series, Series]:
    """MACD。回傳 (DIF, 訊號線, 柱狀體)。

    DIF = EMA(fast) − EMA(slow)，第 slow 筆起有值。
    訊號線 = DIF 的 EMA(signal)，第 slow + signal − 1 筆起有值。
    柱狀體 = DIF − 訊號線（不乘以 2）。
    """
    if not fast < slow:
        raise ValueError("MACD 的 fast 必須小於 slow")
    fast_ema, slow_ema = ema(values, fast), ema(values, slow)
    dif: Series = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_ema, slow_ema, strict=True)
    ]
    signal_line = ema(dif, signal)
    histogram: Series = [
        d - s if d is not None and s is not None else None
        for d, s in zip(dif, signal_line, strict=True)
    ]
    return dif, signal_line, histogram


def _check_window(window: int) -> None:
    if window < 1:
        raise ValueError("期數必須是正整數")
