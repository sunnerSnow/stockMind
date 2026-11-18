"""台灣市場的日期與時間處理。"""

from datetime import date, datetime, timedelta, timezone

TAIPEI = timezone(timedelta(hours=8))


def taipei_now() -> datetime:
    return datetime.now(TAIPEI)


def taipei_timestamp(now: datetime | None = None) -> str:
    """ISO 8601、秒精度、帶 +08:00。"""
    return (now or taipei_now()).astimezone(TAIPEI).isoformat(timespec="seconds")


def parse_roc_compact(value: str | None) -> date | None:
    """民國年緊湊格式 '1151117' → 2026-11-17。無法解析時回 None，不猜測。"""
    if not value:
        return None
    text = value.strip()
    if not text.isdigit() or len(text) not in (6, 7):
        return None
    try:
        return date(int(text[:-4]) + 1911, int(text[-4:-2]), int(text[-2:]))
    except ValueError:
        return None


def parse_western_compact(value: str | None) -> date | None:
    """西元緊湊格式 '19620209' → 1962-02-09。"""
    if not value:
        return None
    text = value.strip()
    if not text.isdigit() or len(text) != 8:
        return None
    try:
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))
    except ValueError:
        return None
