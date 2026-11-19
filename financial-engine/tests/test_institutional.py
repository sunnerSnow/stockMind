import dataclasses

import httpx
import pytest

from app.data_providers import tpex, twse
from tests.conftest import FAST, NO_DATA, T86_FIELDS


def flow(client, stock_id="2330", **params):
    return client.get(f"/stocks/{stock_id}/institutional-flow", params=params)


def test_default_range_covers_last_14_days(client):
    data = flow(client).json()["data"]
    assert data["start_date"] == "2026-11-04"
    assert data["end_date"] == "2026-11-18"
    # 11/18 有行情但法人資料尚未公布，不列入
    assert [d["date"] for d in data["days"]] == [
        "2026-11-12",
        "2026-11-13",
        "2026-11-16",
        "2026-11-17",
    ]


def test_foreign_includes_foreign_dealers_and_dealer_sums_self_and_hedge(client):
    day = flow(client, start_date="2026-11-17", end_date="2026-11-17").json()["data"]["days"][0]
    assert day == {
        "date": "2026-11-17",
        "reported": True,
        # 外陸資 -250 加外資自營商 -50
        "foreign": {"buy": 2_000_000, "sell": 2_000_300, "net": -300},
        "investment_trust": {"buy": 1_000_000, "sell": 1_000_005, "net": -5},
        # 自行買賣 +4 加避險 -5
        "dealer": {"buy": 2_000_000, "sell": 2_000_001, "net": -1},
        "total_net": -306,
    }


def test_net_always_equals_buy_minus_sell(client):
    for day in flow(client).json()["data"]["days"]:
        if not day["reported"]:
            continue
        for who in ("foreign", "investment_trust", "dealer"):
            assert day[who]["net"] == day[who]["buy"] - day[who]["sell"]
        assert day["total_net"] == sum(
            day[w]["net"] for w in ("foreign", "investment_trust", "dealer")
        )


def test_day_missing_from_report_is_null_not_zero(client):
    body = flow(client).json()
    missing = next(d for d in body["data"]["days"] if d["date"] == "2026-11-13")
    assert missing == {
        "date": "2026-11-13",
        "reported": False,
        "foreign": None,
        "investment_trust": None,
        "dealer": None,
        "total_net": None,
    }
    assert any("2026-11-13" in w and "未列此證券" in w for w in body["warnings"])


def test_unpublished_day_is_reported_in_warnings(client):
    body = flow(client).json()
    assert any("2026-11-18" in w and "尚未公布" in w for w in body["warnings"])


def test_summary_is_computed_by_program(client):
    summary = flow(client).json()["data"]["summary"]
    assert summary["trading_days"] == 4
    assert summary["days_with_data"] == 3
    assert summary["cumulative_net"] == {
        "foreign": 100 - 200 - 300,
        "investment_trust": -10 - 20 - 5,
        "dealer": 5 - 30 - 1,
        "total": 95 - 250 - 306,
    }
    # 11/16、11/17 連兩日賣超；11/13 沒資料，連續天數到此為止
    assert summary["streaks"] == {
        "foreign": {"direction": "sell", "days": 2},
        "investment_trust": {"direction": "sell", "days": 2},
        "dealer": {"direction": "sell", "days": 2},
        "total": {"direction": "sell", "days": 2},
    }
    assert summary["latest_alignment"] == "all_sell"


def test_mixed_alignment_and_single_day_streak(client):
    summary = flow(client, start_date="2026-11-12", end_date="2026-11-12").json()["data"]["summary"]
    assert summary["latest_alignment"] == "mixed"  # 外資買、投信賣、自營商買
    assert summary["streaks"]["foreign"] == {"direction": "buy", "days": 1}
    assert summary["streaks"]["investment_trust"] == {"direction": "sell", "days": 1}


def test_streak_is_unknown_when_latest_day_has_no_data(client):
    summary = flow(client, start_date="2026-11-12", end_date="2026-11-13").json()["data"]["summary"]
    assert summary["streaks"]["foreign"] == {"direction": None, "days": 0}
    assert summary["latest_alignment"] is None
    assert summary["cumulative_net"]["foreign"] == 100


def test_metadata_states_unit_and_source(client):
    body = flow(client).json()
    assert body["metadata"]["unit"] == "股"
    assert body["metadata"]["source"] == "TWSE 盤後資訊"
    assert body["metadata"]["data_date"] == "2026-11-17"
    assert body["metadata"]["data_type"] == "historical"
    assert any("不代表未來股價方向" in w for w in body["warnings"])


def test_otc_report_is_read_by_column_position(client):
    body = flow(client, "6488", start_date="2026-11-16", end_date="2026-11-17").json()
    first, second = body["data"]["days"]
    assert first["foreign"] == {"buy": 4_022_901, "sell": 3_508_193, "net": 514_708}
    assert first["investment_trust"] == {"buy": 12_577, "sell": 125_000, "net": -112_423}
    assert first["dealer"] == {"buy": 218_937, "sell": 312_956, "net": -94_019}
    assert first["total_net"] == 308_266
    assert second["total_net"] == -2_600
    assert body["data"]["summary"]["cumulative_net"]["total"] == 308_266 - 2_600
    assert body["metadata"]["source"] == "TPEx 盤後資訊"


def test_only_trading_days_are_requested(client, upstream):
    flow(client)
    requested = sorted(r.split("date=")[1][:8] for r in upstream.requests if "T86" in r)
    assert requested == ["20261112", "20261113", "20261116", "20261117", "20261118"]


def test_no_trading_days_in_range(client, upstream):
    body = flow(client, start_date="2026-11-14", end_date="2026-11-15").json()
    assert body["data"]["days"] == []
    assert body["data"]["summary"]["trading_days"] == 0
    assert body["data"]["summary"]["latest_alignment"] is None
    assert twse.T86_URL not in upstream.calls


@pytest.mark.parametrize(
    ("params", "hint"),
    [
        ({"start_date": "2026-10-01", "end_date": "2026-11-18"}, "最多 31 天"),
        ({"start_date": "2026-11-17", "end_date": "2026-11-01"}, "晚於"),
        ({"end_date": "2026-11-17"}, "start_date"),
    ],
)
def test_invalid_ranges_are_422(client, upstream, params, hint):
    response = flow(client, **params)
    assert response.status_code == 422
    assert hint in response.json()["error"]["message"]
    assert upstream.total_calls() == 0


def test_missing_column_is_rejected_instead_of_guessed(client, upstream):
    fields = [f for f in T86_FIELDS if f != "投信買賣超股數"]
    upstream.routes[twse.T86_URL] = {"stat": "OK", "fields": fields, "data": []}
    response = flow(client)
    assert response.status_code == 502
    assert "投信買賣超股數" in response.json()["error"]["message"]


def test_non_numeric_cell_is_rejected_instead_of_treated_as_zero(client, upstream):
    row = ["2330", "台積電", *["--"] * 17]
    upstream.routes[twse.T86_URL] = {"stat": "OK", "fields": T86_FIELDS, "data": [row]}
    assert flow(client).status_code == 502


def test_otc_wrong_column_count_is_rejected(client, upstream):
    table = {"fields": ["代號", "名稱", "買進股數"], "data": []}
    upstream.routes[tpex.INSTI_URL] = {"stat": "ok", "tables": [table]}
    assert flow(client, "6488", start_date="2026-11-16", end_date="2026-11-17").status_code == 502


def test_gap_in_the_middle_stops_the_streak(client, upstream):
    # 11/16 來源沒有報表：連續天數不能從 11/17 跨過 11/16 接到更早的日子
    original = upstream.routes[twse.T86_URL]

    def without_1116(request):
        if request.url.params["date"] == "20261116":
            return httpx.Response(200, json=NO_DATA)
        return original(request)

    upstream.routes[twse.T86_URL] = without_1116
    body = flow(client).json()
    days = {d["date"]: d for d in body["data"]["days"]}
    assert days["2026-11-16"]["reported"] is False
    assert days["2026-11-16"]["foreign"] is None
    assert "2026-11-18" not in days  # 最後一天尚未公布，仍然不列入
    summary = body["data"]["summary"]
    assert summary["streaks"]["foreign"] == {"direction": "sell", "days": 1}
    assert summary["cumulative_net"]["foreign"] == 100 - 300
    assert summary["trading_days"] == 4 and summary["days_with_data"] == 2
    assert any("2026-11-16" in w and "來源沒有" in w for w in body["warnings"])
    assert any("2026-11-18" in w and "尚未公布" in w for w in body["warnings"])


def test_no_data_for_a_past_day_is_not_cached_to_disk(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    original = upstream.routes[twse.T86_URL]
    upstream.routes[twse.T86_URL] = lambda _r: httpx.Response(200, json=NO_DATA)
    params = {"start_date": "2026-11-17", "end_date": "2026-11-17"}
    assert flow(make_client(settings), **params).json()["data"]["days"] == []

    upstream.routes[twse.T86_URL] = original  # 來源恢復後，重啟就要能查到
    day = flow(make_client(settings), **params).json()["data"]["days"][0]
    assert day["reported"] is True
    assert day["total_net"] == -306


def test_published_past_day_is_cached_to_disk(make_client, upstream, tmp_path):
    settings = dataclasses.replace(FAST, cache_dir=str(tmp_path))
    params = {"start_date": "2026-11-17", "end_date": "2026-11-17"}
    flow(make_client(settings), **params)
    upstream.requests.clear()
    flow(make_client(settings), **params)
    assert [r for r in upstream.requests if "fund/T86" in r] == []
