import re

import httpx
import pytest

from app.data_providers import tpex, twse
from tests.conftest import DEFAULT_ROUTES


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_listed_stock_has_profile_and_metadata(client):
    body = client.get("/stocks/2330").json()
    assert body["success"] is True
    assert body["data"] == {
        "stock_id": "2330",
        "name": "台積電",
        "full_name": "台灣積體電路製造股份有限公司",
        "market": "TWSE",
        "security_type": "stock",
        "industry_code": "24",
        "listing_date": "1994-09-05",
    }
    meta = body["metadata"]
    assert meta["source"] == "TWSE OpenAPI"
    assert meta["data_date"] == "2026-11-17"  # 民國 115/11/17
    assert meta["data_type"] == "reference"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00", meta["retrieved_at"])
    assert body["warnings"] == []


def test_otc_stock_reports_tpex(client):
    body = client.get("/stocks/6488").json()
    assert body["data"]["market"] == "TPEx"
    assert body["data"]["listing_date"] == "2015-09-25"
    assert body["metadata"]["source"] == "TPEx OpenAPI"


@pytest.mark.parametrize(("stock_id", "market"), [("0050", "TWSE"), ("00679B", "TPEx")])
def test_etf_without_company_profile(client, stock_id, market):
    data = client.get(f"/stocks/{stock_id}").json()["data"]
    assert data["security_type"] == "etf"
    assert data["market"] == market
    assert data["full_name"] is None
    assert data["industry_code"] is None
    assert data["listing_date"] is None


def test_stock_only_in_profiles_is_found(client):
    data = client.get("/stocks/1101").json()["data"]
    assert data["name"] == "台泥"
    assert data["security_type"] == "stock"


def test_unclassifiable_security_gets_warning(client):
    body = client.get("/stocks/911608").json()
    assert body["data"]["security_type"] == "other"
    assert len(body["warnings"]) == 1


def test_unknown_stock_is_404(client):
    response = client.get("/stocks/9999")
    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "error": {"code": "STOCK_NOT_FOUND", "message": "查無股票代號 9999"},
    }


@pytest.mark.parametrize("bad", ["abc", "23", "1234567", "2330a", "2330%20", "2330%0A"])
@pytest.mark.parametrize("suffix", ["", "/price", "/history", "/institutional-flow"])
def test_malformed_stock_id_is_422(client, upstream, bad, suffix):
    response = client.get(f"/stocks/{bad}{suffix}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INPUT"
    assert upstream.total_calls() == 0  # 格式錯誤不該打到資料來源


def test_securities_are_cached(client, upstream):
    for stock_id in ("2330", "6488", "0050", "9999"):
        client.get(f"/stocks/{stock_id}")
    client.get("/stocks/2330/price")
    assert upstream.calls == {
        twse.QUOTES_URL: 1,
        twse.PROFILES_URL: 1,
        tpex.QUOTES_URL: 1,
        tpex.PROFILES_URL: 1,
    }


def test_transient_failure_is_retried(client, upstream):
    attempts = {"n": 0}

    def flaky(_request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=DEFAULT_ROUTES[twse.QUOTES_URL])

    upstream.routes[twse.QUOTES_URL] = flaky
    assert client.get("/stocks/2330").status_code == 200
    assert attempts["n"] == 3


def test_timeout_exhausts_retries_then_502(client, upstream):
    upstream.routes[twse.QUOTES_URL] = httpx.ReadTimeout("timeout")
    upstream.routes[tpex.QUOTES_URL] = httpx.ConnectError("refused")
    response = client.get("/stocks/2330")
    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "UPSTREAM_ERROR"
    assert "TWSE OpenAPI" in error["message"]
    assert upstream.calls[twse.QUOTES_URL] == 3  # 1 次 + 重試 2 次


def test_one_source_down_still_serves_the_other(client, upstream):
    upstream.routes[tpex.QUOTES_URL] = httpx.ConnectError("refused")
    assert client.get("/stocks/2330").status_code == 200


def test_not_found_is_not_claimed_when_a_source_is_down(client, upstream):
    upstream.routes[tpex.QUOTES_URL] = httpx.ConnectError("refused")
    response = client.get("/stocks/6488")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_failed_fetch_is_not_cached(client, upstream):
    upstream.routes[tpex.QUOTES_URL] = httpx.ConnectError("refused")
    assert client.get("/stocks/6488").status_code == 502
    upstream.routes[tpex.QUOTES_URL] = DEFAULT_ROUTES[tpex.QUOTES_URL]
    assert client.get("/stocks/6488").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [{"stat": "error"}, ["not-an-object"], []],
    ids=["object", "list-of-strings", "empty"],
)
def test_unexpected_payload_shape_is_upstream_error(client, upstream, payload):
    upstream.routes[twse.QUOTES_URL] = payload
    upstream.routes[twse.PROFILES_URL] = payload
    response = client.get("/stocks/2330")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"


def test_non_json_response_is_upstream_error(client, upstream):
    upstream.routes[twse.QUOTES_URL] = lambda _r: httpx.Response(200, text="<html>維護中</html>")
    assert client.get("/stocks/2330").status_code == 502


@pytest.mark.parametrize("status", [302, 404])
def test_redirect_or_client_error_from_source_is_not_retried(client, upstream, status):
    upstream.routes[twse.QUOTES_URL] = lambda _r: httpx.Response(status)
    assert client.get("/stocks/2330").status_code == 502
    assert upstream.calls[twse.QUOTES_URL] == 1
