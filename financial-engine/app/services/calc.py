"""行情與法人資料的衍生數值計算。純函式，不碰 I/O。"""

from collections.abc import Sequence
from typing import Literal

Direction = Literal["buy", "sell", "flat"]


def previous_close(close: float | None, change: float | None) -> float | None:
    if close is None or change is None:
        return None
    return round(close - change, 4)


def change_percent(close: float | None, change: float | None) -> float | None:
    """漲跌幅（%）＝ 漲跌價差 ÷ 前一日收盤價 × 100，四捨五入到小數第二位。"""
    prev = previous_close(close, change)
    if prev is None or prev <= 0:
        return None
    return round(change / prev * 100, 2)


def direction(net: int) -> Direction:
    return "buy" if net > 0 else "sell" if net < 0 else "flat"


def streak(nets: Sequence[int | None]) -> tuple[Direction | None, int]:
    """nets 依日期由舊到新。回傳最近一日的方向，以及往回同方向連續的天數。

    遇到沒有資料的日子（None）就停止計算，不把缺資料當成延續或中斷後重算。
    """
    if not nets or nets[-1] is None:
        return None, 0
    latest = direction(nets[-1])
    days = 0
    for net in reversed(nets):
        if net is None or direction(net) != latest:
            break
        days += 1
    return latest, days


def alignment(nets: Sequence[int]) -> Literal["all_buy", "all_sell", "mixed"]:
    """多個法人同一日的方向是否一致。任一為持平即視為不一致。"""
    if all(n > 0 for n in nets):
        return "all_buy"
    if all(n < 0 for n in nets):
        return "all_sell"
    return "mixed"
