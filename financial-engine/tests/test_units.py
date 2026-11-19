"""不經 HTTP 的單元測試：計算、解析、設定、節流。"""

import asyncio
import time
from datetime import UTC, date, datetime

import httpx
import pytest

from app.core.config import Settings, load_settings
from app.core.dates import (
    parse_roc_compact,
    parse_roc_slash,
    parse_western_compact,
    taipei_timestamp,
)
from app.data_providers.base import parse_change, parse_float, parse_int
from app.data_providers.http import Fetcher
from app.services import calc
from app.services.history import months_between


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1151117", date(2026, 11, 17)),
        (" 1151117 ", date(2026, 11, 17)),
        ("990105", date(2010, 1, 5)),  # 民國 99 年只有六碼
        ("1150229", None),  # 2026 年沒有 2/29
        ("115/11/17", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_roc_compact(raw, expected):
    assert parse_roc_compact(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("115/11/16", date(2026, 11, 16)),
        (" 99/01/05 ", date(2010, 1, 5)),
        ("115/13/01", None),
        ("2026/11/16", date(3937, 11, 16)),  # 來源一律是民國年，不猜測格式
        ("115-11-16", None),
        (None, None),
    ],
)
def test_parse_roc_slash(raw, expected):
    assert parse_roc_slash(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("19620209", date(1962, 2, 9)), ("1962029", None), ("abcdefgh", None), (None, None)],
)
def test_parse_western_compact(raw, expected):
    assert parse_western_compact(raw) == expected


def test_taipei_timestamp_crosses_date_boundary():
    # UTC 16:30 已是台灣隔日 00:30
    moment = datetime(2026, 11, 17, 16, 30, 5, tzinfo=UTC)
    assert taipei_timestamp(moment) == "2026-11-18T00:30:05+08:00"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2,340.00", 2340.0), ("95.10", 95.1), ("--", None), ("", None), (None, None), ("除息", None)],
)
def test_parse_float(raw, expected):
    assert parse_float(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("52,604,545", 52604545), ("-8,466,493", -8466493), ("0", 0), ("1.5", None), ("--", None)],
)
def test_parse_int(raw, expected):
    assert parse_int(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+30.00", 30.0),
        ("-135.00", -135.0),
        ("-0.24 ", -0.24),
        ("X0.00", None),
        ("除權", None),
        ("0.0000", 0.0),
    ],
)
def test_parse_change(raw, expected):
    assert parse_change(raw) == expected


@pytest.mark.parametrize(
    ("close", "change", "prev", "pct"),
    [
        (2170.0, -45.0, 2215.0, -2.03),
        (110.0, 10.0, 100.0, 10.0),
        (95.1, 0.0, 95.1, 0.0),
        (None, 1.0, None, None),
        (100.0, None, None, None),
        (5.0, 5.0, 0.0, None),  # 前一日收盤為 0 時不計算
    ],
)
def test_change_percent(close, change, prev, pct):
    assert calc.previous_close(close, change) == prev
    assert calc.change_percent(close, change) == pct


@pytest.mark.parametrize(
    ("nets", "expected"),
    [
        ([], (None, 0)),
        ([5], ("buy", 1)),
        ([-1, 2, 3, 4], ("buy", 3)),
        ([1, 2, -3, -4], ("sell", 2)),
        ([1, 0], ("flat", 1)),
        ([1, 0, 2], ("buy", 1)),  # 持平會中斷連續
        ([1, None, 2, 3], ("buy", 2)),  # 缺資料處停止
        ([1, 2, None], (None, 0)),
    ],
)
def test_streak(nets, expected):
    assert calc.streak(nets) == expected


@pytest.mark.parametrize(
    ("nets", "expected"),
    [
        ([1, 2, 3], "all_buy"),
        ([-1, -2, -3], "all_sell"),
        ([1, -2, 3], "mixed"),
        ([1, 0, 3], "mixed"),
    ],
)
def test_alignment(nets, expected):
    assert calc.alignment(nets) == expected


def test_months_between_crosses_year():
    assert months_between(date(2025, 11, 20), date(2026, 2, 3)) == [
        (2025, 11),
        (2025, 12),
        (2026, 1),
        (2026, 2),
    ]


def test_settings_defaults_and_overrides():
    assert load_settings({}) == Settings()
    loaded = load_settings({"STOCKMIND_HTTP_RETRIES": "0", "STOCKMIND_CACHE_DIR": ""})
    assert loaded.http_retries == 0
    assert loaded.cache_dir == ""
    # 空字串的數值設定視為未設定
    assert load_settings({"STOCKMIND_HTTP_TIMEOUT": " "}).http_timeout == Settings().http_timeout


@pytest.mark.parametrize(
    "env",
    [
        {"STOCKMIND_HTTP_TIMEOUT": "fast"},
        {"STOCKMIND_HTTP_TIMEOUT": "0"},
        {"STOCKMIND_HTTP_RETRIES": "-1"},
        {"STOCKMIND_HTTP_RETRIES": "1.5"},
        {"STOCKMIND_THROTTLE_INTERVAL": "-2"},
    ],
)
def test_bad_settings_name_the_variable(env):
    with pytest.raises(ValueError, match=next(iter(env))):
        load_settings(env)


def _fetcher(handler, **overrides) -> Fetcher:
    settings = Settings(http_backoff=0.0, cache_dir="", **overrides)
    return Fetcher(httpx.AsyncClient(transport=httpx.MockTransport(handler)), settings)


def test_throttled_requests_to_one_host_keep_minimum_interval():
    stamps: list[float] = []

    def handler(_request):
        stamps.append(time.monotonic())
        return httpx.Response(200, json=[])

    async def run():
        fetcher = _fetcher(handler, throttle_interval=0.05)
        await asyncio.gather(
            *(
                fetcher.get_json(f"https://example.test/a?i={i}", source="t", ttl=0, throttle=True)
                for i in range(4)
            )
        )

    asyncio.run(run())
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    assert len(stamps) == 4
    assert all(gap >= 0.045 for gap in gaps)


def test_concurrent_requests_for_same_key_fetch_once():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(200, json={"ok": True})

    async def run():
        fetcher = _fetcher(handler)
        results = await asyncio.gather(
            *(fetcher.get_json("https://example.test/x", source="t", ttl=60) for _ in range(5))
        )
        return results

    results = asyncio.run(run())
    assert calls["n"] == 1
    assert all(r.value == {"ok": True} for r in results)


def test_zero_ttl_is_not_cached():
    calls = {"n": 0}

    def handler(_request):
        calls["n"] += 1
        return httpx.Response(200, json=[])

    async def run():
        fetcher = _fetcher(handler)
        await fetcher.get_json("https://example.test/x", source="t", ttl=0)
        await fetcher.get_json("https://example.test/x", source="t", ttl=0)

    asyncio.run(run())
    assert calls["n"] == 2
