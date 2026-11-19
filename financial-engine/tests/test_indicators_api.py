import pytest

from app.data_providers import twse
from app.indicators import core
from app.indicators.spec import parse_indicator, parse_indicators, warmup_calendar_days
from tests.conftest import ETF_CLOSES


def indicators(client, stock_id="0050", **params):
    return client.get(f"/stocks/{stock_id}/indicators", params=params)


def by_name(body):
    return {item["name"]: item for item in body["data"]["indicators"]}


ALL_DAYS = sorted(ETF_CLOSES)
ALL_CLOSES = [ETF_CLOSES[d] for d in ALL_DAYS]


def test_defaults_are_ma5_ma20_rsi14_macd_over_three_months(client):
    body = indicators(client).json()
    data = body["data"]
    assert [i["name"] for i in data["indicators"]] == ["MA5", "MA20", "RSI14", "MACD"]
    assert data["start_date"] == "2026-08-18"  # 今天往回 92 天
    assert data["end_date"] == "2026-11-18"
    assert data["latest_date"] == "2026-11-17"
    assert data["latest_close"] == ALL_CLOSES[-1]
    assert all(i["status"] == "ok" for i in data["indicators"])


def test_values_match_the_formulas_on_full_history(client):
    items = by_name(indicators(client).json())
    dif, signal, histogram = core.macd(ALL_CLOSES, fast=12, slow=26, signal=9)
    expected = {
        "MA5": core.sma(ALL_CLOSES, 5)[-1],
        "MA20": core.sma(ALL_CLOSES, 20)[-1],
        "RSI14": core.rsi(ALL_CLOSES, 14)[-1],
        "MACD": dif[-1],
    }
    for name, value in expected.items():
        # 服務只取了規定的暖機期，和用全部歷史算的結果應該一致到小數第二位
        assert items[name]["latest"]["value"] == pytest.approx(value, abs=0.01), name
        assert items[name]["latest"]["date"] == "2026-11-17"
    assert items["MACD"]["latest"]["signal"] == pytest.approx(signal[-1], abs=0.01)
    assert items["MACD"]["latest"]["histogram"] == pytest.approx(histogram[-1], abs=0.01)
    assert items["MA5"]["latest"]["signal"] is None
    assert items["MA5"]["latest"]["histogram"] is None


def test_ma_is_exact_and_rounded_to_four_decimals(client):
    item = by_name(indicators(client, indicators="MA5").json())["MA5"]
    assert item["latest"]["value"] == round(sum(ALL_CLOSES[-5:]) / 5, 4)


def test_values_cover_only_the_requested_range_and_start_with_a_value(client):
    body = indicators(client, start_date="2026-11-02", end_date="2026-11-13").json()
    for item in body["data"]["indicators"]:
        dates = [p["date"] for p in item["values"]]
        assert dates[0] == "2026-11-02" and dates[-1] == "2026-11-13", item["name"]
        assert len(dates) == 10  # 兩週的平日
        # 因為往前取了暖機期，區間第一天就有值
        assert item["values"][0]["value"] is not None, item["name"]
        assert item["latest"]["date"] == "2026-11-13"
    assert body["metadata"]["data_date"] == "2026-11-13"


def test_each_indicator_states_its_definition_and_parameters(client):
    items = by_name(indicators(client).json())
    assert items["MA20"]["kind"] == "SMA"
    assert items["MA20"]["params"] == {"window": 20}
    assert items["MA20"]["required_bars"] == 20
    assert items["RSI14"]["params"] == {"period": 14}
    assert items["RSI14"]["required_bars"] == 15
    assert "Wilder" in items["RSI14"]["definition"]
    assert items["MACD"]["params"] == {"fast": 12, "slow": 26, "signal": 9}
    assert items["MACD"]["required_bars"] == 34
    assert "不乘以 2" in items["MACD"]["definition"]
    assert all(i["available_bars"] > i["required_bars"] for i in items.values())


def test_metadata_and_warnings(client):
    body = indicators(client).json()
    assert body["metadata"]["source"] == "TWSE 盤後資訊"
    assert body["metadata"]["data_type"] == "historical"
    assert "RSI" in body["metadata"]["unit"]
    assert any("未還原" in w for w in body["warnings"])
    assert any("不代表未來股價方向" in w for w in body["warnings"])


def test_short_history_reports_insufficient_data_without_guessing(client):
    # 2330 的樣本只有 7 個交易日
    body = indicators(client, "2330").json()
    items = by_name(body)
    assert items["MA5"]["status"] == "ok"
    assert items["MA5"]["latest"]["value"] == round((2360 + 2350 + 2215 + 2170 + 2200) / 5, 4)
    for name in ("MA20", "RSI14", "MACD"):
        assert items[name]["status"] == "insufficient_data", name
        assert items[name]["latest"] is None
        assert items[name]["available_bars"] == 7
        assert all(p["value"] is None for p in items[name]["values"])
    warning = next(w for w in body["warnings"] if "不足" in w)
    assert "MA20（需 20 筆）" in warning and "MACD（需 34 筆）" in warning
    assert "MA5" not in warning


def test_custom_indicators_as_repeated_or_comma_separated(client):
    repeated = client.get("/stocks/0050/indicators?indicators=ma10&indicators=RSI6").json()
    comma = indicators(client, indicators="MA10, rsi6,MA10").json()
    assert [i["name"] for i in repeated["data"]["indicators"]] == ["MA10", "RSI6"]
    assert [i["name"] for i in comma["data"]["indicators"]] == ["MA10", "RSI6"]  # 去重複
    assert by_name(comma)["RSI6"]["latest"]["value"] == pytest.approx(
        core.rsi(ALL_CLOSES, 6)[-1], abs=0.01
    )


def test_flat_prices_make_rsi_undefined_not_zero(client, upstream):
    def flat(request):
        from httpx import Response

        month = request.url.params["date"]
        rows = [
            [
                f"115/{month[4:6]}/{day:02d}",
                "1",
                "1",
                "50.00",
                "50.00",
                "50.00",
                "50.00",
                "0.00",
                "1",
                "",
            ]
            for day in range(1, 29)
        ]
        return Response(200, json={"stat": "OK", "fields": upstream_fields(), "data": rows})

    upstream.routes[twse.STOCK_DAY_URL] = flat
    body = indicators(client, indicators="RSI14,MA5").json()
    items = by_name(body)
    assert items["RSI14"]["status"] == "undefined"
    assert items["RSI14"]["latest"] is None
    assert items["MA5"]["status"] == "ok" and items["MA5"]["latest"]["value"] == 50.0
    assert any("無定義" in w and "RSI14" in w for w in body["warnings"])


def upstream_fields():
    from tests.conftest import TWSE_BAR_FIELDS

    return TWSE_BAR_FIELDS


def test_days_without_trades_are_skipped_and_reported(client, upstream):
    original = upstream.routes[twse.STOCK_DAY_URL]

    def with_gap(request):
        response = original(request)
        payload = response.json()
        if request.url.params["date"] == "20261101":
            payload["data"][-1][3:7] = ["--", "--", "--", "--"]  # 11/17 無成交
        from httpx import Response

        return Response(200, json=payload)

    upstream.routes[twse.STOCK_DAY_URL] = with_gap
    body = indicators(client, indicators="MA5").json()
    assert body["data"]["latest_date"] == "2026-11-16"
    assert by_name(body)["MA5"]["latest"]["value"] == round(sum(ALL_CLOSES[-6:-1]) / 5, 4)
    assert any("沒有成交" in w for w in body["warnings"])


def test_only_needed_months_are_requested(client, upstream):
    indicators(client, indicators="MA5", start_date="2026-11-16", end_date="2026-11-17")
    months = sorted(
        r.split("date=")[1][:6] for r in upstream.requests if "afterTrading/STOCK_DAY" in r
    )
    assert months == ["202610", "202611"]  # MA5 只需往前多取約三週


@pytest.mark.parametrize(
    ("value", "hint"),
    [
        ("KD9", "不支援"),
        ("MA", "不支援"),
        ("MA1", "2 到 120"),
        ("MA121", "2 到 120"),
        ("RSI31", "2 到 30"),
        ("MACD12", "不支援"),
        ("MA5;DROP", "不支援"),
        ("MA2,MA3,MA4,MA5,MA6,MA7,MA8,MA9,MA10", "最多"),
    ],
)
def test_invalid_indicators_are_422_before_any_upstream_call(client, upstream, value, hint):
    response = indicators(client, indicators=value)
    assert response.status_code == 422
    assert hint in response.json()["error"]["message"]
    assert upstream.total_calls() == 0


def test_error_message_echoes_only_a_short_prefix_of_bad_input(client):
    message = indicators(client, indicators="Z" * 60).json()["error"]["message"]
    assert "Z" * 20 in message and "Z" * 21 not in message


def test_invalid_range_and_unknown_stock(client):
    assert indicators(client, period="1mo", start_date="2026-11-01").status_code == 422
    assert indicators(client, start_date="2025-01-01", end_date="2026-11-01").status_code == 422
    assert indicators(client, "9999").status_code == 404


def test_spec_parsing_and_warmup():
    assert parse_indicator(" ma20 ").name == "MA20"
    assert [s.name for s in parse_indicators(None)] == ["MA5", "MA20", "RSI14", "MACD"]
    assert [s.name for s in parse_indicators(["", " , "])] == ["MA5", "MA20", "RSI14", "MACD"]
    # MA5：5 筆 → 8 個日曆天，加 30 天緩衝
    assert warmup_calendar_days([parse_indicator("MA5")]) == 38
    # 取各指標中最長的：MACD 需 34 + 100 筆
    both = [parse_indicator("MA5"), parse_indicator("MACD")]
    assert warmup_calendar_days(both) == warmup_calendar_days([parse_indicator("MACD")]) == 230


def test_unsettled_smoothing_is_flagged_when_history_is_short(client):
    # 樣本的行情從 2026-01-02 開始；查 2 月時，區間之前只有約 20 筆資料
    body = indicators(client, start_date="2026-02-02", end_date="2026-02-27").json()
    items = by_name(body)
    assert items["RSI14"]["status"] == "ok"  # 算得出數值
    warning = next(w for w in body["warnings"] if "收斂" in w)
    assert "RSI14" in warning and "MACD" in warning
    assert "MA5" not in warning and "MA20" not in warning  # 移動平均沒有收斂問題


def test_no_convergence_warning_with_enough_history(client):
    body = indicators(client).json()
    assert not any("收斂" in w for w in body["warnings"])
