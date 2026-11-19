import pytest

from app.data_providers import tpex, twse


def test_price_of_listed_stock(client):
    body = client.get("/stocks/2330/price").json()
    assert body["data"] == {
        "stock_id": "2330",
        "name": "台積電",
        "market": "TWSE",
        "trade_date": "2026-11-17",
        "open": 2195.0,
        "high": 2270.0,
        "low": 2155.0,
        "close": 2170.0,
        "change": -45.0,
        "previous_close": 2215.0,
        "change_percent": -2.03,  # -45 / 2215
        "volume": 61610981,
        "value": 135465361736,
        "transactions": 371462,
    }
    meta = body["metadata"]
    assert meta["data_type"] == "after_market"  # 盤後資料不得標成即時
    assert meta["data_date"] == "2026-11-17"
    assert meta["source"] == "TWSE OpenAPI"
    assert "股" in meta["unit"]
    assert any("不是即時" in w for w in body["warnings"])


def test_price_of_otc_stock_uses_shares_and_dollars(client):
    data = client.get("/stocks/6488/price").json()["data"]
    assert data["market"] == "TPEx"
    assert data["close"] == 546.0
    assert data["change"] == -31.0
    assert data["previous_close"] == 577.0
    assert data["change_percent"] == -5.37
    assert data["volume"] == 10450123
    assert data["value"] == 5735050000


def test_price_without_trades_is_null_not_zero(client):
    body = client.get("/stocks/911608/price").json()
    data = body["data"]
    assert data["close"] is None
    assert data["open"] is None
    assert data["change_percent"] is None
    assert data["volume"] == 0
    assert any("沒有成交" in w for w in body["warnings"])


def test_price_with_non_numeric_change_leaves_change_null(client):
    body = client.get("/stocks/5483/price").json()
    data = body["data"]
    assert data["close"] == 120.0
    assert data["change"] is None
    assert data["previous_close"] is None
    assert data["change_percent"] is None
    assert any("漲跌" in w for w in body["warnings"])


def test_price_of_stock_missing_from_daily_quotes(client):
    body = client.get("/stocks/1101/price").json()
    assert body["data"]["name"] == "台泥"
    assert body["data"]["close"] is None
    assert body["data"]["volume"] is None
    assert any("沒有這檔證券" in w for w in body["warnings"])


def test_price_unknown_stock_is_404(client):
    assert client.get("/stocks/9999/price").status_code == 404


def test_twse_market_summary(client):
    body = client.get("/market/TWSE/summary").json()
    data = body["data"]
    assert data["index_name"] == "發行量加權股價指數"
    assert data["trade_date"] == "2026-11-17"
    assert data["close"] == 40092.11
    assert data["change"] == -947.97
    assert data["previous_close"] == 41040.08
    assert data["change_percent"] == -2.31
    assert data["volume"] == 15218510001
    assert data["value"] == 1002035660990
    assert data["open"] is None
    assert data["recent"] == [
        {"date": "2026-11-16", "close": 41040.08, "change": -512.3},
        {"date": "2026-11-17", "close": 40092.11, "change": -947.97},
    ]
    assert body["metadata"]["data_type"] == "after_market"
    assert any("開盤" in w for w in body["warnings"])


def test_tpex_market_summary_has_ohlc_but_no_volume(client):
    body = client.get("/market/TPEx/summary").json()
    data = body["data"]
    assert data["index_name"] == "櫃買指數"
    assert data["trade_date"] == "2026-11-17"
    assert (data["open"], data["high"], data["low"], data["close"]) == (301.0, 303.0, 290.1, 292.42)
    assert data["change_percent"] == -3.33  # -10.08 / 302.50
    assert data["volume"] is None
    assert any("成交量" in w for w in body["warnings"])


def test_market_summary_sorts_by_date(client, upstream):
    upstream.routes[twse.INDEX_URL] = list(reversed(upstream.routes[twse.INDEX_URL]))
    assert client.get("/market/TWSE/summary").json()["data"]["trade_date"] == "2026-11-17"


@pytest.mark.parametrize("market", ["NYSE", "twse", "TWSE%2F.."])
def test_unknown_market_is_422(client, upstream, market):
    response = client.get(f"/market/{market}/summary")
    assert response.status_code in (404, 422)
    assert upstream.total_calls() == 0


def test_empty_index_is_upstream_error(client, upstream):
    upstream.routes[tpex.INDEX_URL] = []
    response = client.get("/market/TPEx/summary")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_ERROR"
