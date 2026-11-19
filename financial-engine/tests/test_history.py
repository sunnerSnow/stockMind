import dataclasses

import httpx
import pytest

from app.data_providers import tpex, twse
from tests.conftest import FAST, TWSE_BAR_FIELDS


def history(client, stock_id="2330", **params):
    return client.get(f"/stocks/{stock_id}/history", params=params)


def test_default_range_is_one_month_back_from_today(client, upstream):
    body = history(client).json()
    data = body["data"]
    assert data["start_date"] == "2026-10-18"
    assert data["end_date"] == "2026-11-18"
    assert [b["date"] for b in data["bars"]] == [
        "2026-10-29",
        "2026-10-30",
        "2026-11-12",
        "2026-11-13",
        "2026-11-16",
        "2026-11-17",
        "2026-11-18",
    ]
    assert data["count"] == 7
    assert upstream.calls[twse.STOCK_DAY_URL] == 2  # 十月、十一月各一次


def test_bar_values_are_parsed_from_roc_dates_and_thousands_separators(client):
    bars = history(client, start_date="2026-11-16", end_date="2026-11-16").json()["data"]["bars"]
    assert bars == [
        {
            "date": "2026-11-16",
            "open": 2340.0,
            "high": 2350.0,
            "low": 2215.0,
            "close": 2215.0,
            "change": -135.0,
            "volume": 52604545,
            "value": 119305254268,
            "transactions": 408529,
        }
    ]


def test_metadata_and_adjustment_warning(client):
    body = history(client, start_date="2026-11-12", end_date="2026-11-17").json()
    meta = body["metadata"]
    assert meta["source"] == "TWSE 盤後資訊"
    assert meta["data_type"] == "historical"
    assert meta["data_date"] == "2026-11-17"  # 範圍內最後一個交易日
    assert any("未還原" in w for w in body["warnings"])


def test_uncomparable_change_is_null(client):
    bars = history(client, start_date="2026-11-13", end_date="2026-11-13").json()["data"]["bars"]
    assert bars[0]["change"] is None  # 來源為 X0.00
    assert bars[0]["close"] == 2350.0


def test_otc_volume_converted_from_lots_and_thousands(client):
    body = history(client, "6488", start_date="2026-11-16", end_date="2026-11-17").json()
    first = body["data"]["bars"][0]
    assert first["volume"] == 7_729_000  # 7,729 張
    assert first["value"] == 4_607_056_000  # 4,607,056 仟元
    assert first["close"] == 577.0
    assert body["metadata"]["source"] == "TPEx 盤後資訊"
    assert any("1,000 股" in w for w in body["warnings"])


def test_period_parameter(client):
    data = history(client, period="5d").json()["data"]
    assert data["start_date"] == "2026-11-11"
    assert [b["date"] for b in data["bars"]][0] == "2026-11-12"


def test_end_date_in_future_is_clamped_to_today(client):
    data = history(client, start_date="2026-11-17", end_date="2027-01-01").json()["data"]
    assert data["end_date"] == "2026-11-18"


def test_range_without_trading_days(client):
    body = history(client, start_date="2026-11-14", end_date="2026-11-15").json()
    assert body["data"]["count"] == 0
    assert body["metadata"]["data_date"] is None
    assert any("沒有交易資料" in w for w in body["warnings"])


@pytest.mark.parametrize(
    ("params", "hint"),
    [
        ({"period": "1mo", "start_date": "2026-11-01"}, "擇一"),
        ({"period": "10y"}, "period"),
        ({"end_date": "2026-11-01"}, "start_date"),
        ({"start_date": "2026-11-10", "end_date": "2026-11-01"}, "晚於"),
        ({"start_date": "2026-12-01"}, "未來"),
        ({"start_date": "2025-01-01", "end_date": "2026-11-01"}, "最多"),
        ({"start_date": "2026/11/01"}, "start_date"),
    ],
)
def test_invalid_ranges_are_422_before_any_upstream_call(client, upstream, params, hint):
    response = history(client, **params)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_INPUT"
    assert hint in error["message"]
    assert upstream.total_calls() == 0


def test_unknown_stock_is_404_without_history_calls(client, upstream):
    assert history(client, "9999").status_code == 404
    assert twse.STOCK_DAY_URL not in upstream.calls


def test_changed_columns_are_rejected_instead_of_misread(client, upstream):
    swapped = [TWSE_BAR_FIELDS[0], "成交張數", *TWSE_BAR_FIELDS[2:]]
    upstream.routes[twse.STOCK_DAY_URL] = {"stat": "OK", "fields": swapped, "data": []}
    response = history(client)
    assert response.status_code == 502
    assert "欄位" in response.json()["error"]["message"]


def test_tpex_changed_unit_column_is_rejected(client, upstream):
    table = {
        "fields": ["日 期", "成交股數", "成交仟元", "開盤", "最高", "最低", "收盤", "漲跌", "筆數"],
        "data": [],
    }
    upstream.routes[tpex.STOCK_URL] = {"stat": "ok", "tables": [table]}
    assert history(client, "6488").status_code == 502


def test_unexpected_stat_is_upstream_error(client, upstream):
    upstream.routes[twse.STOCK_DAY_URL] = {"stat": "查詢日期大於今日，請重新查詢!"}
    assert history(client).status_code == 502


def test_same_month_is_fetched_once_within_ttl(client, upstream):
    history(client, start_date="2026-11-12", end_date="2026-11-13")
    history(client, start_date="2026-11-16", end_date="2026-11-17")
    assert upstream.calls[twse.STOCK_DAY_URL] == 1


def test_finished_months_survive_restart_via_disk_cache(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    first = history(make_client(settings)).json()
    assert upstream.calls[twse.STOCK_DAY_URL] == 2

    upstream.requests.clear()
    second = history(make_client(settings)).json()  # 新的 app：記憶體快取是空的

    months = [r for r in upstream.requests if "afterTrading/STOCK_DAY" in r]
    assert len(months) == 1 and "date=20261101" in months[0]  # 只重抓還沒結束的當月
    assert second["data"] == first["data"]


def test_disk_cache_keeps_original_retrieval_time(make_client, tmp_path, monkeypatch):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    params = {"start_date": "2026-10-29", "end_date": "2026-10-30"}
    monkeypatch.setattr(
        "app.data_providers.http.taipei_timestamp", lambda: "2026-11-01T09:00:00+08:00"
    )
    first = history(make_client(settings), **params).json()
    monkeypatch.setattr(
        "app.data_providers.http.taipei_timestamp", lambda: "2026-11-18T09:00:00+08:00"
    )
    second = history(make_client(settings), **params).json()
    assert first["metadata"]["retrieved_at"] == "2026-11-01T09:00:00+08:00"
    assert second["metadata"]["retrieved_at"] == "2026-11-01T09:00:00+08:00"


def test_corrupt_disk_cache_is_ignored(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    params = {"start_date": "2026-10-29", "end_date": "2026-10-30"}
    history(make_client(settings), **params)
    for file in tmp_path.glob("*.json"):
        file.write_text("{not json", encoding="utf-8")
    response = history(make_client(settings), **params)
    assert response.status_code == 200
    assert response.json()["data"]["count"] == 2
    assert upstream.calls[twse.STOCK_DAY_URL] == 2


def test_invalid_response_is_not_written_to_disk(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    upstream.routes[twse.STOCK_DAY_URL] = lambda _r: httpx.Response(200, json={"stat": "系統忙碌"})
    assert (
        history(make_client(settings), start_date="2026-10-29", end_date="2026-10-30").status_code
        == 502
    )
    assert list(tmp_path.glob("*.json")) == []


def test_empty_past_month_is_not_cached_to_disk(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    params = {"start_date": "2026-09-01", "end_date": "2026-09-30"}  # 樣本沒有九月的資料
    assert history(make_client(settings), **params).json()["data"]["count"] == 0
    assert list(tmp_path.glob("*.json")) == []
