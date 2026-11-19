"""證券櫃檯買賣中心（上櫃）。OpenAPI 提供最新一日的全市場資料，網站盤後資訊提供歷史查詢。"""

from datetime import date
from typing import Any

from app.core.dates import parse_roc_compact, parse_roc_slash, parse_western_compact
from app.core.errors import UpstreamError
from app.data_providers.base import (
    Bar,
    DailyQuotes,
    Flow,
    IndexDay,
    InstitutionalRow,
    Profile,
    Quote,
    clean,
    parse_change,
    parse_float,
    parse_int,
    require_int,
    require_rows,
    scale,
)
from app.data_providers.http import Fetched, Fetcher

OPENAPI = "https://www.tpex.org.tw/openapi/v1"
SITE = "https://www.tpex.org.tw/www/zh-tw"

# 當日上櫃證券收盤行情（含 ETF）
QUOTES_URL = f"{OPENAPI}/tpex_mainboard_daily_close_quotes"
# 上櫃公司基本資料（只有公司，沒有 ETF）
PROFILES_URL = f"{OPENAPI}/mopsfin_t187ap03_O"
# 近期櫃買指數
INDEX_URL = f"{OPENAPI}/tpex_index"
# 個股日成交資訊，一次一個月
STOCK_URL = f"{SITE}/afterTrading/tradingStock"
# 三大法人買賣明細，一次一天、全市場
INSTI_URL = f"{SITE}/insti/dailyTrade"

# 個股日成交資訊的欄位。成交量是「張」、成交金額是「仟元」，解析時換算成股與元。
_BAR_FIELDS = ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"]
# 三大法人明細固定 24 欄，買進／賣出／買賣超三欄一組，欄位名稱重複，只能靠位置。
# 各組依序為：外資及陸資(不含外資自營商)、外資自營商、外資合計、投信、
# 自營商(自行買賣)、自營商(避險)、自營商合計，最後一欄是三大法人合計。
_INSTI_COLUMNS = 24
_FOREIGN, _TRUST, _DEALER, _TOTAL = 8, 11, 20, 23


def _first_table(payload: Any, source: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or str(payload.get("stat", "")).lower() != "ok":
        raise UpstreamError(source, "回傳格式與預期不符")
    tables = payload.get("tables")
    if not isinstance(tables, list) or not tables or not isinstance(tables[0], dict):
        raise UpstreamError(source, "回傳格式與預期不符")
    table = tables[0]
    if not isinstance(table.get("fields"), list) or not isinstance(table.get("data"), list):
        raise UpstreamError(source, "回傳格式與預期不符")
    return table


def parse_quotes(rows: list[dict[str, Any]]) -> DailyQuotes:
    quotes: dict[str, Quote] = {}
    data_date = None
    for row in rows:
        stock_id, name = clean(row.get("SecuritiesCompanyCode")), clean(row.get("CompanyName"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("Date"))
        quotes[stock_id] = Quote(
            stock_id=stock_id,
            name=name,
            open=parse_float(row.get("Open")),
            high=parse_float(row.get("High")),
            low=parse_float(row.get("Low")),
            close=parse_float(row.get("Close")),
            change=parse_change(row.get("Change")),
            volume=parse_int(row.get("TradingShares")),
            value=parse_int(row.get("TransactionAmount")),
            transactions=parse_int(row.get("TransactionNumber")),
        )
    return DailyQuotes(data_date=data_date, quotes=quotes)


def parse_profiles(rows: list[dict[str, Any]]) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for row in rows:
        stock_id = clean(row.get("SecuritiesCompanyCode"))
        name = clean(row.get("CompanyAbbreviation")) or clean(row.get("CompanyName"))
        if not stock_id or not name:
            continue
        profiles[stock_id] = Profile(
            stock_id=stock_id,
            name=name,
            full_name=clean(row.get("CompanyName")),
            industry_code=clean(row.get("SecuritiesIndustryCode")),
            listing_date=parse_western_compact(row.get("DateOfListing")),
        )
    return profiles


def parse_month_bars(payload: Any, source: str) -> list[Bar]:
    table = _first_table(payload, source)
    # 單位換算依賴欄位名稱（張、仟元），欄位變了就不能沿用原本的換算
    if table["fields"] != _BAR_FIELDS:
        raise UpstreamError(source, "個股日成交資訊的欄位與預期不符")
    bars = []
    for row in table["data"]:
        ok = isinstance(row, list) and len(row) == len(_BAR_FIELDS)
        trade_date = parse_roc_slash(row[0]) if ok else None
        if trade_date is None:
            raise UpstreamError(source, "個股日成交資訊的資料列與預期不符")
        bars.append(
            Bar(
                trade_date=trade_date,
                volume=scale(parse_int(row[1]), 1000),
                value=scale(parse_int(row[2]), 1000),
                open=parse_float(row[3]),
                high=parse_float(row[4]),
                low=parse_float(row[5]),
                close=parse_float(row[6]),
                change=parse_change(row[7]),
                transactions=parse_int(row[8]),
            )
        )
    return bars


def parse_institutional(payload: Any, source: str) -> dict[str, InstitutionalRow] | None:
    table = _first_table(payload, source)
    fields, data = table["fields"], table["data"]
    if len(fields) != _INSTI_COLUMNS or "合計" not in str(fields[_TOTAL]):
        raise UpstreamError(source, "三大法人明細的欄位與預期不符")
    if not data:
        return None

    rows: dict[str, InstitutionalRow] = {}
    for row in data:
        if not isinstance(row, list) or len(row) != _INSTI_COLUMNS:
            raise UpstreamError(source, "三大法人明細的資料列與預期不符")
        stock_id = clean(row[0])
        if not stock_id:
            continue

        def flow(start: int, row: list[Any] = row) -> Flow:
            buy, sell, net = (
                require_int(row[start + i], source, f"第 {start + i + 1} 欄") for i in range(3)
            )
            return Flow(buy=buy, sell=sell, net=net)

        rows[stock_id] = InstitutionalRow(
            foreign=flow(_FOREIGN),
            investment_trust=flow(_TRUST),
            dealer=flow(_DEALER),
            total_net=require_int(row[_TOTAL], source, "三大法人買賣超股數合計"),
        )
    return rows


def parse_index_days(rows: list[dict[str, Any]]) -> list[IndexDay]:
    days = []
    for row in rows:
        trade_date, close = parse_western_compact(row.get("Date")), parse_float(row.get("Close"))
        if trade_date is None or close is None:
            continue
        days.append(
            IndexDay(
                trade_date=trade_date,
                close=close,
                change=parse_float(row.get("Change")),
                open=parse_float(row.get("Open")),
                high=parse_float(row.get("High")),
                low=parse_float(row.get("Low")),
            )
        )
    return sorted(days, key=lambda d: d.trade_date)


class TpexProvider:
    market = "TPEx"
    openapi_source = "TPEx OpenAPI"
    site_source = "TPEx 盤後資訊"
    index_name = "櫃買指數"

    async def daily_quotes(self, fetcher: Fetcher) -> Fetched[DailyQuotes]:
        src = self.openapi_source
        fetched = await fetcher.get_json(
            QUOTES_URL,
            source=src,
            ttl=fetcher.settings.quotes_ttl,
            validate=lambda p: require_rows(p, src),
        )
        return fetched.map(parse_quotes)

    async def profiles(self, fetcher: Fetcher) -> Fetched[dict[str, Profile]]:
        src = self.openapi_source
        fetched = await fetcher.get_json(
            PROFILES_URL,
            source=src,
            ttl=fetcher.settings.securities_ttl,
            validate=lambda p: require_rows(p, src),
        )
        return fetched.map(parse_profiles)

    async def month_bars(
        self, fetcher: Fetcher, stock_id: str, year: int, month: int, *, final: bool
    ) -> Fetched[list[Bar]]:
        src = self.site_source
        fetched = await fetcher.get_json(
            STOCK_URL,
            source=src,
            params={"code": stock_id, "date": f"{year:04d}/{month:02d}/01", "response": "json"},
            ttl=fetcher.settings.quotes_ttl,
            persist=final,
            throttle=True,
            validate=lambda p: parse_month_bars(p, src),
            persist_when=lambda p: bool(parse_month_bars(p, src)),
        )
        return fetched.map(lambda p: parse_month_bars(p, src))

    async def institutional_day(
        self, fetcher: Fetcher, day: date, *, final: bool
    ) -> Fetched[dict[str, InstitutionalRow] | None]:
        src = self.site_source
        fetched = await fetcher.get_json(
            INSTI_URL,
            source=src,
            params={
                "type": "Daily",
                "sect": "EW",
                "date": day.strftime("%Y/%m/%d"),
                "response": "json",
            },
            ttl=fetcher.settings.quotes_ttl,
            persist=final,
            throttle=True,
            validate=lambda p: parse_institutional(p, src),
            persist_when=lambda p: parse_institutional(p, src) is not None,
        )
        return fetched.map(lambda p: parse_institutional(p, src))

    async def index_days(self, fetcher: Fetcher) -> Fetched[list[IndexDay]]:
        src = self.openapi_source
        fetched = await fetcher.get_json(
            INDEX_URL,
            source=src,
            ttl=fetcher.settings.quotes_ttl,
            validate=lambda p: require_rows(p, src),
        )
        return fetched.map(parse_index_days)
