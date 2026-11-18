"""臺灣證券交易所（上市）OpenAPI。"""

import asyncio
from typing import Any

import httpx

from app.core.config import Settings
from app.core.dates import parse_roc_compact, parse_western_compact
from app.data_providers.base import (
    SecuritiesSnapshot,
    SecurityRecord,
    clean,
    guess_type_without_profile,
    require_rows,
)
from app.data_providers.http import fetch_json

BASE_URL = "https://openapi.twse.com.tw/v1"
# 當日全部上市證券行情：含 ETF，用來取得完整代號與簡稱
QUOTES_URL = f"{BASE_URL}/exchangeReport/STOCK_DAY_ALL"
# 上市公司基本資料：只有公司，沒有 ETF
PROFILES_URL = f"{BASE_URL}/opendata/t187ap03_L"


def parse_securities(
    quotes: list[dict[str, Any]], profiles: list[dict[str, Any]], source: str
) -> SecuritiesSnapshot:
    records: dict[str, SecurityRecord] = {}
    data_date = None

    for row in quotes:
        stock_id, name = clean(row.get("Code")), clean(row.get("Name"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("Date"))
        records[stock_id] = SecurityRecord(
            stock_id=stock_id,
            name=name,
            market="TWSE",
            security_type=guess_type_without_profile(stock_id),
        )

    for row in profiles:
        stock_id = clean(row.get("公司代號"))
        name = clean(row.get("公司簡稱")) or clean(row.get("公司名稱"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("出表日期"))
        records[stock_id] = SecurityRecord(
            stock_id=stock_id,
            name=name,
            market="TWSE",
            security_type="stock",
            full_name=clean(row.get("公司名稱")),
            industry_code=clean(row.get("產業別")),
            listing_date=parse_western_compact(row.get("上市日期")),
        )

    return SecuritiesSnapshot(source=source, records=records, data_date=data_date)


class TwseProvider:
    source = "TWSE OpenAPI"

    async def fetch_securities(
        self, client: httpx.AsyncClient, settings: Settings
    ) -> SecuritiesSnapshot:
        quotes, profiles = await asyncio.gather(
            fetch_json(client, QUOTES_URL, source=self.source, settings=settings),
            fetch_json(client, PROFILES_URL, source=self.source, settings=settings),
        )
        return parse_securities(
            require_rows(quotes, self.source), require_rows(profiles, self.source), self.source
        )
