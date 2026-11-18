"""各資料來源共用的標準化結構。來源的欄位名稱、日期格式差異都在 Provider 內消化。"""

from dataclasses import dataclass
from datetime import date
from typing import Any, Literal, Protocol

import httpx

from app.core.config import Settings
from app.core.errors import UpstreamError


@dataclass(frozen=True)
class SecurityRecord:
    stock_id: str
    name: str
    market: Literal["TWSE", "TPEx"]
    security_type: Literal["stock", "etf", "other"]
    full_name: str | None = None
    industry_code: str | None = None
    listing_date: date | None = None


@dataclass(frozen=True)
class SecuritiesSnapshot:
    """單一市場的證券清單快照。"""

    source: str
    records: dict[str, SecurityRecord]
    data_date: date | None


class SecuritiesProvider(Protocol):
    source: str

    async def fetch_securities(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> SecuritiesSnapshot: ...


def clean(value: Any) -> str | None:
    """去空白；空字串與來源常見的佔位符視為無資料。"""
    if value is None:
        return None
    text = str(value).strip()
    return text if text and text not in {"-", "－", "--"} else None


def guess_type_without_profile(stock_id: str) -> Literal["etf", "other"]:
    """不在公司基本資料內的證券：代號 00 開頭者為 ETF，其餘無法判定。"""
    return "etf" if stock_id.startswith("00") else "other"


def require_rows(payload: Any, source: str) -> list[dict[str, Any]]:
    """來源應回傳物件陣列；不是的話視為來源異常，不嘗試解讀。"""
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise UpstreamError(source, "回傳格式與預期不符")
    return payload
