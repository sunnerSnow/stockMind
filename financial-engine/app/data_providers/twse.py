"""臺灣證券交易所（上市）。OpenAPI 提供最新一日的全市場資料，網站盤後資訊提供歷史查詢。"""

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
)
from app.data_providers.http import Fetched, Fetcher

OPENAPI = "https://openapi.twse.com.tw/v1"
SITE = "https://www.twse.com.tw/rwd/zh"

# 當日全部上市證券行情（含 ETF）
QUOTES_URL = f"{OPENAPI}/exchangeReport/STOCK_DAY_ALL"
# 上市公司基本資料（只有公司，沒有 ETF）
PROFILES_URL = f"{OPENAPI}/opendata/t187ap03_L"
# 近期每日市場成交資訊與加權指數
INDEX_URL = f"{OPENAPI}/exchangeReport/FMTQIK"
# 個股日成交資訊，一次一個月
STOCK_DAY_URL = f"{SITE}/afterTrading/STOCK_DAY"
# 三大法人買賣超日報，一次一天、全市場
T86_URL = f"{SITE}/fund/T86"

_NO_DATA = "沒有符合條件"

_BAR_FIELDS = ["日期", "成交股數", "成交金額", "開盤價", "最高價", "最低價", "收盤價", "漲跌價差"]


def _site_table(payload: Any, source: str) -> tuple[list[str], list[list[Any]]] | None:
    """網站端點的共同外層：stat 為 OK 時回 (fields, data)，查無資料時回 None。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("stat"), str):
        raise UpstreamError(source, "回傳格式與預期不符")
    stat = payload["stat"]
    if _NO_DATA in stat:
        return None
    fields, data = payload.get("fields"), payload.get("data")
    if stat != "OK" or not isinstance(fields, list) or not isinstance(data, list):
        raise UpstreamError(source, "回傳格式與預期不符")
    return fields, data


def parse_quotes(rows: list[dict[str, Any]]) -> DailyQuotes:
    quotes: dict[str, Quote] = {}
    data_date = None
    for row in rows:
        stock_id, name = clean(row.get("Code")), clean(row.get("Name"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("Date"))
        quotes[stock_id] = Quote(
            stock_id=stock_id,
            name=name,
            open=parse_float(row.get("OpeningPrice")),
            high=parse_float(row.get("HighestPrice")),
            low=parse_float(row.get("LowestPrice")),
            close=parse_float(row.get("ClosingPrice")),
            change=parse_change(row.get("Change")),
            volume=parse_int(row.get("TradeVolume")),
            value=parse_int(row.get("TradeValue")),
            transactions=parse_int(row.get("Transaction")),
        )
    return DailyQuotes(data_date=data_date, quotes=quotes)


def parse_profiles(rows: list[dict[str, Any]]) -> dict[str, Profile]:
    profiles: dict[str, Profile] = {}
    for row in rows:
        stock_id = clean(row.get("公司代號"))
        name = clean(row.get("公司簡稱")) or clean(row.get("公司名稱"))
        if not stock_id or not name:
            continue
        profiles[stock_id] = Profile(
            stock_id=stock_id,
            name=name,
            full_name=clean(row.get("公司名稱")),
            industry_code=clean(row.get("產業別")),
            listing_date=parse_western_compact(row.get("上市日期")),
        )
    return profiles


def parse_month_bars(payload: Any, source: str) -> list[Bar]:
    table = _site_table(payload, source)
    if table is None:
        return []
    fields, data = table
    # 單位（股、元）是由欄位名稱保證的，欄位變了就不能沿用原本的解讀
    if fields[: len(_BAR_FIELDS)] != _BAR_FIELDS:
        raise UpstreamError(source, "個股日成交資訊的欄位與預期不符")
    bars = []
    for row in data:
        trade_date = parse_roc_slash(row[0]) if isinstance(row, list) and len(row) >= 9 else None
        if trade_date is None:
            raise UpstreamError(source, "個股日成交資訊的資料列與預期不符")
        bars.append(
            Bar(
                trade_date=trade_date,
                volume=parse_int(row[1]),
                value=parse_int(row[2]),
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
    table = _site_table(payload, source)
    if table is None:
        return None
    fields, data = table
    index = {str(name): i for i, name in enumerate(fields)}

    def col(name: str) -> int:
        # 以欄位名稱定位：交易所調整過欄位順序與數量，位置不可靠
        if name not in index:
            raise UpstreamError(source, f"三大法人報表缺少欄位「{name}」")
        return index[name]

    code = col("證券代號")
    f_buy, f_sell, f_net = (
        col(f"外陸資{k}股數(不含外資自營商)") for k in ("買進", "賣出", "買賣超")
    )
    fd_buy, fd_sell, fd_net = (col(f"外資自營商{k}股數") for k in ("買進", "賣出", "買賣超"))
    t_buy, t_sell, t_net = (col(f"投信{k}股數") for k in ("買進", "賣出", "買賣超"))
    d_net = col("自營商買賣超股數")
    ds_buy, ds_sell = col("自營商買進股數(自行買賣)"), col("自營商賣出股數(自行買賣)")
    dh_buy, dh_sell = col("自營商買進股數(避險)"), col("自營商賣出股數(避險)")
    total = col("三大法人買賣超股數")

    rows: dict[str, InstitutionalRow] = {}
    for row in data:
        if not isinstance(row, list) or len(row) != len(fields):
            raise UpstreamError(source, "三大法人報表的資料列與預期不符")
        stock_id = clean(row[code])
        if not stock_id:
            continue

        def num(i: int, row: list[Any] = row) -> int:
            return require_int(row[i], source, str(fields[i]))

        rows[stock_id] = InstitutionalRow(
            foreign=Flow(
                buy=num(f_buy) + num(fd_buy),
                sell=num(f_sell) + num(fd_sell),
                net=num(f_net) + num(fd_net),
            ),
            investment_trust=Flow(buy=num(t_buy), sell=num(t_sell), net=num(t_net)),
            dealer=Flow(
                buy=num(ds_buy) + num(dh_buy), sell=num(ds_sell) + num(dh_sell), net=num(d_net)
            ),
            total_net=num(total),
        )
    return rows


def parse_index_days(rows: list[dict[str, Any]]) -> list[IndexDay]:
    days = []
    for row in rows:
        trade_date, close = parse_roc_compact(row.get("Date")), parse_float(row.get("TAIEX"))
        if trade_date is None or close is None:
            continue
        days.append(
            IndexDay(
                trade_date=trade_date,
                close=close,
                change=parse_float(row.get("Change")),
                volume=parse_int(row.get("TradeVolume")),
                value=parse_int(row.get("TradeValue")),
                transactions=parse_int(row.get("Transaction")),
            )
        )
    return sorted(days, key=lambda d: d.trade_date)


class TwseProvider:
    market = "TWSE"
    openapi_source = "TWSE OpenAPI"
    site_source = "TWSE 盤後資訊"
    index_name = "發行量加權股價指數"

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
            STOCK_DAY_URL,
            source=src,
            params={"response": "json", "date": f"{year:04d}{month:02d}01", "stockNo": stock_id},
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
            T86_URL,
            source=src,
            params={"response": "json", "date": day.strftime("%Y%m%d"), "selectType": "ALLBUT0999"},
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
