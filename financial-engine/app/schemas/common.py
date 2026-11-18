from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

DataType = Literal["reference", "historical", "delayed", "intraday", "after_market"]
Market = Literal["TWSE", "TPEx"]

# 與 mcp-server 的 stockIdSchema 一致：4–6 位數字，可帶一個大寫英文字尾
STOCK_ID_PATTERN = r"^\d{4,6}[A-Z]?$"


class Metadata(BaseModel):
    source: str = Field(description="資料來源名稱")
    data_date: date | None = Field(description="資料日期（台灣市場日期）")
    retrieved_at: str = Field(description="自來源擷取的時間，ISO 8601 含時區")
    data_type: DataType
    unit: str | None = Field(default=None, description="數值單位")


class Envelope[T](BaseModel):
    success: Literal[True] = True
    data: T
    metadata: Metadata
    warnings: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorEnvelope(BaseModel):
    success: Literal[False] = False
    error: ErrorBody
