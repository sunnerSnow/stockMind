"""測試不連真實來源：以 httpx.MockTransport 回放依官方回應格式裁剪的樣本。"""

from collections.abc import Callable, Iterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.data_providers import tpex, twse
from app.main import create_app

TWSE_QUOTES = [
    {"Date": "1151117", "Code": "0050", "Name": "元大台灣50", "ClosingPrice": "95.10"},
    {"Date": "1151117", "Code": "2330", "Name": "台積電", "ClosingPrice": "2480.00"},
    {"Date": "1151117", "Code": "911608", "Name": "某存託憑證", "ClosingPrice": "1.00"},
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
        # 當日無成交、只出現在公司基本資料的股票
        "出表日期": "1151117",
        "公司代號": "1101",
        "公司名稱": "臺灣水泥股份有限公司",
        "公司簡稱": "台泥",
        "產業別": "01",
        "上市日期": "19620209",
    },
]
TPEX_QUOTES = [
    {"Date": "1151117", "SecuritiesCompanyCode": "00679B", "CompanyName": "元大美債20年"},
    {"Date": "1151117", "SecuritiesCompanyCode": "6488", "CompanyName": "環球晶"},
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

DEFAULT_ROUTES: dict[str, object] = {
    twse.QUOTES_URL: TWSE_QUOTES,
    twse.PROFILES_URL: TWSE_PROFILES,
    tpex.QUOTES_URL: TPEX_QUOTES,
    tpex.PROFILES_URL: TPEX_PROFILES,
}

FAST = Settings(http_timeout=1.0, http_retries=2, http_backoff=0.0)


class FakeUpstream:
    """可逐網址覆寫回應，並記錄每個網址被呼叫的次數。"""

    def __init__(self) -> None:
        self.routes: dict[str, object] = dict(DEFAULT_ROUTES)
        self.calls: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.calls[url] = self.calls.get(url, 0) + 1
        route = self.routes[url]
        if isinstance(route, Exception):
            raise route
        if callable(route):
            return route(request)
        return httpx.Response(200, json=route)

    def total_calls(self) -> int:
        return sum(self.calls.values())


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
