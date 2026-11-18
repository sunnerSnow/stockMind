from datetime import UTC, date, datetime

import pytest

from app.core.dates import parse_roc_compact, parse_western_compact, taipei_timestamp


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
    [("19620209", date(1962, 2, 9)), ("1962029", None), ("abcdefgh", None), (None, None)],
)
def test_parse_western_compact(raw, expected):
    assert parse_western_compact(raw) == expected


def test_taipei_timestamp_crosses_date_boundary():
    # UTC 16:30 已是台灣隔日 00:30
    assert (
        taipei_timestamp(datetime(2026, 11, 17, 16, 30, 5, tzinfo=UTC))
        == "2026-11-18T00:30:05+08:00"
    )
