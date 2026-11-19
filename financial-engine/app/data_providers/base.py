"""各資料來源共用的標準化結構與解析工具。

來源之間的差異（欄位名稱、民國年、千分位、張與股、仟元與元）都在 Provider 內消化，
出了 Provider 之後一律是：日期為 date、價格為 float（新台幣元）、成交量為股、成交金額為元。
"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

from app.core.errors import UpstreamError
from app.data_providers.http import Fetched, Fetcher

Market = Literal["TWSE", "TPEx"]


@dataclass(frozen=True)
class Profile:
    """公司基本資料。ETF 等非公司證券沒有這份資料。"""

    stock_id: str
    name: str
    full_name: str | None
    industry_code: str | None
    listing_date: date | None


@dataclass(frozen=True)
class Quote:
    """單一證券在某個交易日的盤後行情。當日無成交時價格為 None。"""

    stock_id: str
    name: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    volume: int | None
    value: int | None
    transactions: int | None


@dataclass(frozen=True)
class DailyQuotes:
    data_date: date | None
    quotes: dict[str, Quote]


@dataclass(frozen=True)
class Bar:
    trade_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    volume: int | None
    value: int | None
    transactions: int | None


@dataclass(frozen=True)
class Flow:
    """單一類別法人的買賣股數。net = buy - sell。"""

    buy: int
    sell: int
    net: int


@dataclass(frozen=True)
class InstitutionalRow:
    """三大法人單日買賣超，單位為股。

    foreign 含外資自營商；dealer 為自行買賣與避險合計。
    """

    foreign: Flow
    investment_trust: Flow
    dealer: Flow
    total_net: int


@dataclass(frozen=True)
class IndexDay:
    trade_date: date
    close: float
    change: float | None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None
    value: int | None = None
    transactions: int | None = None


class MarketProvider(Protocol):
    market: Market
    # 各類資料實際的來源名稱，會原樣放進回應的 metadata.source
    openapi_source: str
    site_source: str
    index_name: str

    async def daily_quotes(self, fetcher: Fetcher) -> Fetched[DailyQuotes]: ...

    async def profiles(self, fetcher: Fetcher) -> Fetched[dict[str, Profile]]: ...

    async def month_bars(
        self, fetcher: Fetcher, stock_id: str, year: int, month: int, *, final: bool
    ) -> Fetched[list[Bar]]:
        """某檔證券某個月的日行情。final 表示該月已結束、資料不會再變。"""
        ...

    async def institutional_day(
        self, fetcher: Fetcher, day: date, *, final: bool
    ) -> Fetched[dict[str, InstitutionalRow] | None]:
        """某一天全市場的三大法人買賣超。該日沒有資料（非交易日或尚未公布）時回 None。"""
        ...

    async def index_days(self, fetcher: Fetcher) -> Fetched[list[IndexDay]]:
        """近期的大盤指數日資料，依日期由舊到新。"""
        ...


# --- 解析工具 ---

_PLACEHOLDERS = {"-", "－", "--", "---", "----"}


def clean(value: Any) -> str | None:
    """去空白；空字串與來源常見的佔位符視為無資料。"""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text not in _PLACEHOLDERS else None


def parse_float(value: Any) -> float | None:
    """'2,340.00' → 2340.0。無資料或不是數字時回 None，不猜測。"""
    text = clean(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    """'52,604,545' → 52604545。帶小數的值不視為整數。"""
    text = clean(value)
    if text is None:
        return None
    try:
        return int(text.replace(",", ""))
    except ValueError:
        return None


def parse_change(value: Any) -> float | None:
    """漲跌價差：'+30.00'、'-135.00'。'X0.00'（不比價）或除權息等文字回 None。"""
    text = clean(value)
    if text is None or text[0] in "Xx":
        return None
    return parse_float(text)


def scale(value: int | None, factor: int) -> int | None:
    return None if value is None else value * factor


def require_int(value: Any, source: str, field: str) -> int:
    """法人買賣股數必須是整數；解析不出來代表來源格式變了，不能當成 0。"""
    number = parse_int(value)
    if number is None:
        raise UpstreamError(source, f"欄位「{field}」不是預期的數字")
    return number


def guess_type_without_profile(stock_id: str) -> Literal["etf", "other"]:
    """不在公司基本資料內的證券：代號 00 開頭者為 ETF，其餘無法判定。"""
    return "etf" if stock_id.startswith("00") else "other"


def require_rows(payload: Any, source: str) -> list[dict[str, Any]]:
    """OpenAPI 應回傳物件陣列；不是的話視為來源異常，不嘗試解讀。"""
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise UpstreamError(source, "回傳格式與預期不符")
    return payload
