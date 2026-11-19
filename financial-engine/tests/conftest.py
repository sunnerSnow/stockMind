"""測試不連真實來源：以 httpx.MockTransport 回放依官方回應格式裁剪的樣本。

樣本的欄位名稱、日期格式、千分位與單位都照 2026-11 實際抓到的回應。
測試中的「今天」固定為 2026-11-18（週三）。
"""

import math
from collections.abc import Callable, Iterator
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.data_providers import tpex, twse
from app.main import create_app

TODAY = date(2026, 11, 18)
NO_DATA = {"stat": "很抱歉，沒有符合條件的資料!", "total": 0}

# --- OpenAPI：最新一日的全市場資料 ---

TWSE_QUOTES = [
    {
        "Date": "1151117",
        "Code": "0050",
        "Name": "元大台灣50",
        "TradeVolume": "30000000",
        "TradeValue": "2853000000",
        "OpeningPrice": "96.00",
        "HighestPrice": "96.50",
        "LowestPrice": "94.80",
        "ClosingPrice": "95.10",
        "Change": "-1.2000",
        "Transaction": "41000",
    },
    {
        "Date": "1151117",
        "Code": "2330",
        "Name": "台積電",
        "TradeVolume": "61610981",
        "TradeValue": "135465361736",
        "OpeningPrice": "2195.00",
        "HighestPrice": "2270.00",
        "LowestPrice": "2155.00",
        "ClosingPrice": "2170.00",
        "Change": "-45.0000",
        "Transaction": "371462",
    },
    {
        # 當日無成交
        "Date": "1151117",
        "Code": "911608",
        "Name": "某存託憑證",
        "TradeVolume": "0",
        "TradeValue": "0",
        "OpeningPrice": "",
        "HighestPrice": "",
        "LowestPrice": "",
        "ClosingPrice": "",
        "Change": "0.0000",
        "Transaction": "0",
    },
]
TWSE_PROFILES = [
    {
        "出表日期": "1151117",
        "公司代號": "2330",
        "公司名稱": "台灣積體電路製造股份有限公司",
        "公司簡稱": "台積電",
        "產業別": "24",
        "上市日期": "19940905",
    },
    {
        # 只出現在公司基本資料、不在當日行情清單的股票
        "出表日期": "1151117",
        "公司代號": "1101",
        "公司名稱": "臺灣水泥股份有限公司",
        "公司簡稱": "台泥",
        "產業別": "01",
        "上市日期": "19620209",
    },
]
TWSE_INDEX = [
    {
        "Date": "1151116",
        "TradeVolume": "14000000000",
        "TradeValue": "900000000000",
        "Transaction": "6000000",
        "TAIEX": "41040.08",
        "Change": "-512.30",
    },
    {
        "Date": "1151117",
        "TradeVolume": "15218510001",
        "TradeValue": "1002035660990",
        "Transaction": "7682883",
        "TAIEX": "40092.11",
        "Change": "-947.97",
    },
]
TPEX_QUOTES = [
    {
        "Date": "1151117",
        "SecuritiesCompanyCode": "00679B",
        "CompanyName": "元大美債20年",
        "Close": "27.50",
        "Change": "+0.10 ",
        "Open": "27.40",
        "High": "27.55",
        "Low": "27.38",
        "TradingShares": "5000000",
        "TransactionAmount": "137500000",
        "TransactionNumber": "2100",
    },
    {
        "Date": "1151117",
        "SecuritiesCompanyCode": "6488",
        "CompanyName": "環球晶",
        "Close": "546.00",
        "Change": "-31.00 ",
        "Open": "544.00",
        "High": "575.00",
        "Low": "535.00",
        "TradingShares": "10450123",
        "TransactionAmount": "5735050000",
        "TransactionNumber": "18811",
    },
    {
        # 除息日：來源的漲跌欄位是文字
        "Date": "1151117",
        "SecuritiesCompanyCode": "5483",
        "CompanyName": "中美晶",
        "Close": "120.00",
        "Change": "除息 ",
        "Open": "119.00",
        "High": "121.00",
        "Low": "118.50",
        "TradingShares": "800000",
        "TransactionAmount": "96000000",
        "TransactionNumber": "900",
    },
]
TPEX_PROFILES = [
    {
        "Date": "1151117",
        "SecuritiesCompanyCode": "6488",
        "CompanyName": "環球晶圓股份有限公司",
        "CompanyAbbreviation": "環球晶",
        "SecuritiesIndustryCode": "24",
        "DateOfListing": "20150925",
    },
]
TPEX_INDEX = [
    {
        "Date": "20261116",
        "Open": "300.00",
        "High": "305.00",
        "Low": "298.00",
        "Close": "302.50",
        "Change": "1.50",
    },
    {
        "Date": "20261117",
        "Open": "301.00",
        "High": "303.00",
        "Low": "290.10",
        "Close": "292.42",
        "Change": "-10.08",
    },
]

# --- 網站盤後資訊：個股月行情 ---

TWSE_BAR_FIELDS = [
    "日期",
    "成交股數",
    "成交金額",
    "開盤價",
    "最高價",
    "最低價",
    "收盤價",
    "漲跌價差",
    "成交筆數",
    "註記",
]
TWSE_MONTHS = {
    ("2330", "20261001"): [
        [
            "115/10/29",
            "20,000,000",
            "50,000,000,000",
            "2,500.00",
            "2,520.00",
            "2,480.00",
            "2,500.00",
            "+10.00",
            "50,000",
            "",
        ],
        [
            "115/10/30",
            "21,000,000",
            "52,000,000,000",
            "2,500.00",
            "2,510.00",
            "2,470.00",
            "2,480.00",
            "-20.00",
            "51,000",
            "",
        ],
    ],
    ("2330", "20261101"): [
        [
            "115/11/12",
            "30,000,000",
            "70,000,000,000",
            "2,400.00",
            "2,410.00",
            "2,350.00",
            "2,360.00",
            "-40.00",
            "90,000",
            "",
        ],
        [
            "115/11/13",
            "28,000,000",
            "66,000,000,000",
            "2,360.00",
            "2,370.00",
            "2,340.00",
            "2,350.00",
            "X0.00",
            "80,000",
            "",
        ],
        [
            "115/11/16",
            "52,604,545",
            "119,305,254,268",
            "2,340.00",
            "2,350.00",
            "2,215.00",
            "2,215.00",
            "-135.00",
            "408,529",
            "",
        ],
        [
            "115/11/17",
            "61,610,981",
            "135,465,361,736",
            "2,195.00",
            "2,270.00",
            "2,155.00",
            "2,170.00",
            "-45.00",
            "371,462",
            "",
        ],
        [
            "115/11/18",
            "40,000,000",
            "88,000,000,000",
            "2,180.00",
            "2,220.00",
            "2,170.00",
            "2,200.00",
            "+30.00",
            "200,000",
            "",
        ],
    ],
}


def synthetic_closes(count: int) -> list[float]:
    """有漲有跌、可重現的收盤價序列，供技術指標測試使用。"""
    return [
        round(100 + 12 * math.sin(i / 6) + 0.05 * i + (i * 7 % 5) * 0.3, 2) for i in range(count)
    ]


def _weekdays(start: date, end: date) -> list[date]:
    days, day = [], start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


# 0050：2026-01-02 到 2026-11-17 的每個平日都有行情（指標測試需要夠長的歷史）
ETF_DAYS = _weekdays(date(2026, 1, 2), date(2026, 11, 17))
ETF_CLOSES = dict(zip(ETF_DAYS, synthetic_closes(len(ETF_DAYS)), strict=True))
for _day, _close in ETF_CLOSES.items():
    _row = [
        f"{_day.year - 1911}/{_day.month:02d}/{_day.day:02d}",
        "1,000,000", "100,000,000",
        f"{_close:.2f}", f"{_close + 1:.2f}", f"{_close - 1:.2f}", f"{_close:.2f}",
        "+0.00", "1,000", "",
    ]  # fmt: skip
    TWSE_MONTHS.setdefault(("0050", f"{_day.year}{_day.month:02d}01"), []).append(_row)

TPEX_BAR_FIELDS = ["日 期", "成交張數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"]
TPEX_MONTHS = {
    ("6488", "2026/11/01"): [
        [
            "115/11/16",
            "7,729",
            "4,607,056",
            "625.00",
            "638.00",
            "575.00",
            "577.00",
            "-53.00",
            "19,399",
        ],
        [
            "115/11/17",
            "10,450",
            "5,735,050",
            "544.00",
            "575.00",
            "535.00",
            "546.00",
            "-31.00",
            "18,811",
        ],
    ],
}

# --- 網站盤後資訊：三大法人 ---

T86_FIELDS = [
    "證券代號", "證券名稱",
    "外陸資買進股數(不含外資自營商)", "外陸資賣出股數(不含外資自營商)", "外陸資買賣超股數(不含外資自營商)",
    "外資自營商買進股數", "外資自營商賣出股數", "外資自營商買賣超股數",
    "投信買進股數", "投信賣出股數", "投信買賣超股數",
    "自營商買賣超股數",
    "自營商買進股數(自行買賣)", "自營商賣出股數(自行買賣)", "自營商買賣超股數(自行買賣)",
    "自營商買進股數(避險)", "自營商賣出股數(避險)", "自營商買賣超股數(避險)",
    "三大法人買賣超股數",
]  # fmt: skip


def t86_row(code: str, foreign: int, foreign_dealer: int, trust: int, self_: int, hedge: int):
    """以各類法人的買賣超組出一列；買進固定為 1,000,000，賣出反推。"""

    def trio(net: int) -> list[str]:
        return [f"{1_000_000:,}", f"{1_000_000 - net:,}", f"{net:,}"]

    dealer = self_ + hedge
    total = foreign + foreign_dealer + trust + dealer
    return [code, "名稱      ", *trio(foreign), *trio(foreign_dealer), *trio(trust),
            f"{dealer:,}", *trio(self_), *trio(hedge), f"{total:,}"]  # fmt: skip


T86_DAYS = {
    "20261112": [t86_row("2330", 90, 10, -10, 2, 3), t86_row("0050", 1, 0, 1, 1, 0)],
    "20261113": [t86_row("0050", 5, 0, 5, 5, 0)],  # 報表未列 2330
    "20261116": [t86_row("2330", -200, 0, -20, -10, -20)],
    "20261117": [t86_row("2330", -250, -50, -5, 4, -5)],
    # 20261118：今天，尚未公布
}

TPEX_INSTI_FIELDS = [
    "代號",
    "名稱",
    *["買進股數", "賣出股數", "買賣超股數"] * 7,
    "三大法人買賣超股數合計",
]
# 照實際回應：6488 於 115/11/16
TPEX_INSTI_DAYS = {
    "2026/11/16": [
        [
            "6488",
            "環球晶",
            "4,022,901",
            "3,508,193",
            "514,708",
            "0",
            "0",
            "0",
            "4,022,901",
            "3,508,193",
            "514,708",
            "12,577",
            "125,000",
            "-112,423",
            "109,400",
            "67,500",
            "41,900",
            "109,537",
            "245,456",
            "-135,919",
            "218,937",
            "312,956",
            "-94,019",
            "308,266",
        ],
    ],  # fmt: skip
    "2026/11/17": [
        [
            "6488",
            "環球晶",
            "1,000",
            "3,000",
            "-2,000",
            "0",
            "0",
            "0",
            "1,000",
            "3,000",
            "-2,000",
            "0",
            "500",
            "-500",
            "0",
            "100",
            "-100",
            "0",
            "0",
            "0",
            "0",
            "100",
            "-100",
            "-2,600",
        ],
    ],  # fmt: skip
}


def twse_stock_day(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    rows = TWSE_MONTHS.get((params["stockNo"], params["date"]))
    if rows is None:
        return httpx.Response(200, json=NO_DATA)
    return httpx.Response(200, json={"stat": "OK", "fields": TWSE_BAR_FIELDS, "data": rows})


def twse_t86(request: httpx.Request) -> httpx.Response:
    rows = T86_DAYS.get(request.url.params["date"])
    if rows is None:
        return httpx.Response(200, json=NO_DATA)
    return httpx.Response(200, json={"stat": "OK", "fields": T86_FIELDS, "data": rows})


def tpex_stock(request: httpx.Request) -> httpx.Response:
    params = request.url.params
    rows = TPEX_MONTHS.get((params["code"], params["date"]), [])
    table = {"fields": TPEX_BAR_FIELDS, "data": rows}
    return httpx.Response(200, json={"stat": "ok", "tables": [table]})


def tpex_insti(request: httpx.Request) -> httpx.Response:
    rows = TPEX_INSTI_DAYS.get(request.url.params["date"], [])
    table = {"fields": TPEX_INSTI_FIELDS, "data": rows}
    return httpx.Response(200, json={"stat": "ok", "tables": [table, {}]})


DEFAULT_ROUTES: dict[str, object] = {
    twse.QUOTES_URL: TWSE_QUOTES,
    twse.PROFILES_URL: TWSE_PROFILES,
    twse.INDEX_URL: TWSE_INDEX,
    twse.STOCK_DAY_URL: twse_stock_day,
    twse.T86_URL: twse_t86,
    tpex.QUOTES_URL: TPEX_QUOTES,
    tpex.PROFILES_URL: TPEX_PROFILES,
    tpex.INDEX_URL: TPEX_INDEX,
    tpex.STOCK_URL: tpex_stock,
    tpex.INSTI_URL: tpex_insti,
}

FAST = Settings(
    http_timeout=1.0, http_retries=2, http_backoff=0.0, throttle_interval=0.0, cache_dir=""
)


class FakeUpstream:
    """可逐端點覆寫回應，並記錄每個端點（不含查詢字串）被呼叫的次數。"""

    def __init__(self) -> None:
        self.routes: dict[str, object] = dict(DEFAULT_ROUTES)
        self.calls: dict[str, int] = {}
        self.requests: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url.copy_with(query=None))
        self.calls[url] = self.calls.get(url, 0) + 1
        self.requests.append(str(request.url))
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(request)
        return httpx.Response(200, json=route)

    def total_calls(self) -> int:
        return sum(self.calls.values())


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (
        "app.services.history",
        "app.services.institutional",
        "app.services.indicators",
    ):
        monkeypatch.setattr(f"{module}.taipei_today", lambda: TODAY)


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
def make_client(upstream: FakeUpstream) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def _make(settings: Settings = FAST) -> TestClient:
        app = create_app(settings=settings, transport=httpx.MockTransport(upstream.handler))
        client = TestClient(app, raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    return make_client()
