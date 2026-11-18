"""證券櫃檯買賣中心（上櫃）OpenAPI。"""

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

BASE_URL = "https://www.tpex.org.tw/openapi/v1"
# 當日上櫃證券收盤行情：含 ETF，用來取得完整代號與簡稱
QUOTES_URL = f"{BASE_URL}/tpex_mainboard_daily_close_quotes"
# 上櫃公司基本資料：只有公司，沒有 ETF
PROFILES_URL = f"{BASE_URL}/mopsfin_t187ap03_O"


def parse_securities(
    quotes: list[dict[str, Any]], profiles: list[dict[str, Any]], source: str
) -> SecuritiesSnapshot:
    records: dict[str, SecurityRecord] = {}
    data_date = None

    for row in quotes:
        stock_id, name = clean(row.get("SecuritiesCompanyCode")), clean(row.get("CompanyName"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("Date"))
        records[stock_id] = SecurityRecord(
            stock_id=stock_id,
            name=name,
            market="TPEx",
            security_type=guess_type_without_profile(stock_id),
        )

    for row in profiles:
        stock_id = clean(row.get("SecuritiesCompanyCode"))
        name = clean(row.get("CompanyAbbreviation")) or clean(row.get("CompanyName"))
        if not stock_id or not name:
            continue
        data_date = data_date or parse_roc_compact(row.get("Date"))
        records[stock_id] = SecurityRecord(
            stock_id=stock_id,
            name=name,
            market="TPEx",
            security_type="stock",
            full_name=clean(row.get("CompanyName")),
            industry_code=clean(row.get("SecuritiesIndustryCode")),
            listing_date=parse_western_compact(row.get("DateOfListing")),
        )

    return SecuritiesSnapshot(source=source, records=records, data_date=data_date)


class TpexProvider:
    source = "TPEx OpenAPI"

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
