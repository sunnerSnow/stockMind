from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Market

SecurityType = Literal["stock", "etf", "other"]


class StockInfo(BaseModel):
    stock_id: str
    name: str = Field(description="證券簡稱")
    full_name: str | None = Field(default=None, description="公司全名；ETF 等無公司資料者為 null")
    market: Market
    security_type: SecurityType
    industry_code: str | None = Field(default=None, description="交易所產業別代碼")
    listing_date: date | None = Field(default=None, description="上市／上櫃日期")
