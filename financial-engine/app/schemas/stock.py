from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Market

SecurityType = Literal["stock", "etf", "other"]
Direction = Literal["buy", "sell", "flat"]


class StockInfo(BaseModel):
    stock_id: str
    name: str = Field(description="證券簡稱")
    full_name: str | None = Field(default=None, description="公司全名；ETF 等無公司資料者為 null")
    market: Market
    security_type: SecurityType
    industry_code: str | None = Field(default=None, description="交易所產業別代碼")
    listing_date: date | None = Field(default=None, description="上市／上櫃日期")


class StockPrice(BaseModel):
    stock_id: str
    name: str
    market: Market
    trade_date: date | None = Field(description="這筆行情所屬的交易日")
    open: float | None
    high: float | None
    low: float | None
    close: float | None = Field(description="收盤價；當日無成交為 null")
    change: float | None = Field(description="漲跌價差")
    previous_close: float | None = Field(description="由 close - change 算出的前一日收盤價")
    change_percent: float | None = Field(description="漲跌幅（%），由程式計算")
    volume: int | None = Field(description="成交股數")
    value: int | None = Field(description="成交金額（元）")
    transactions: int | None = Field(description="成交筆數")


class PriceBar(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change: float | None
    volume: int | None
    value: int | None
    transactions: int | None


class StockHistory(BaseModel):
    stock_id: str
    name: str
    market: Market
    start_date: date
    end_date: date
    count: int = Field(description="期間內的交易日數")
    bars: list[PriceBar] = Field(description="依日期由舊到新")


class FlowModel(BaseModel):
    buy: int
    sell: int
    net: int = Field(description="買賣超 = buy - sell；正為買超、負為賣超")


class InstitutionalDay(BaseModel):
    date: date
    reported: bool = Field(description="該日三大法人報表是否列有此證券")
    foreign: FlowModel | None = Field(description="外資及陸資，含外資自營商")
    investment_trust: FlowModel | None = Field(description="投信")
    dealer: FlowModel | None = Field(description="自營商，自行買賣與避險合計")
    total_net: int | None = Field(description="三大法人買賣超合計")


class Streak(BaseModel):
    direction: Direction | None = Field(description="最近一個有資料交易日的方向")
    days: int = Field(description="截至最近一個有資料的交易日，同方向連續的天數")


class CumulativeNet(BaseModel):
    foreign: int
    investment_trust: int
    dealer: int
    total: int


class Streaks(BaseModel):
    foreign: Streak
    investment_trust: Streak
    dealer: Streak
    total: Streak


class InstitutionalSummary(BaseModel):
    trading_days: int = Field(description="期間內的交易日數")
    days_with_data: int = Field(description="其中有法人資料的天數")
    cumulative_net: CumulativeNet = Field(description="期間累計買賣超，只計有資料的日子")
    streaks: Streaks
    latest_alignment: Literal["all_buy", "all_sell", "mixed"] | None = Field(
        description="最近一個有資料的交易日，外資、投信、自營商方向是否一致"
    )


class InstitutionalFlow(BaseModel):
    stock_id: str
    name: str
    market: Market
    start_date: date
    end_date: date
    days: list[InstitutionalDay] = Field(description="依日期由舊到新")
    summary: InstitutionalSummary


class IndexPoint(BaseModel):
    date: date
    close: float
    change: float | None


class MarketSummary(BaseModel):
    market: Market
    index_name: str
    trade_date: date
    close: float
    change: float | None
    previous_close: float | None = Field(description="由 close - change 算出")
    change_percent: float | None = Field(description="漲跌幅（%），由程式計算")
    open: float | None
    high: float | None
    low: float | None
    volume: int | None = Field(description="市場成交股數")
    value: int | None = Field(description="市場成交金額（元）")
    transactions: int | None = Field(description="市場成交筆數")
    recent: list[IndexPoint] = Field(description="近期收盤指數，依日期由舊到新，最多 10 日")
