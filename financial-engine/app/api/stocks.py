from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path, Query, Request
from pydantic import StringConstraints

from app.schemas.common import STOCK_ID_PATTERN, Envelope, ErrorEnvelope
from app.schemas.stock import (
    InstitutionalFlow,
    StockHistory,
    StockInfo,
    StockPrice,
    TechnicalIndicators,
)

router = APIRouter(prefix="/stocks", tags=["stocks"])

StockId = Annotated[
    str, Path(pattern=STOCK_ID_PATTERN, description="台股證券代號，例如 2330", examples=["2330"])
]
ERRORS = {
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    502: {"model": ErrorEnvelope},
}


@router.get("/{stock_id}", response_model=Envelope[StockInfo], responses=ERRORS, summary="基本資料")
async def get_stock_info(stock_id: StockId, request: Request) -> Envelope[StockInfo]:
    return await request.app.state.securities.get_stock_info(stock_id)


@router.get(
    "/{stock_id}/price",
    response_model=Envelope[StockPrice],
    responses=ERRORS,
    summary="最新可用行情（盤後）",
)
async def get_stock_price(stock_id: StockId, request: Request) -> Envelope[StockPrice]:
    return await request.app.state.securities.get_stock_price(stock_id)


@router.get(
    "/{stock_id}/history",
    response_model=Envelope[StockHistory],
    responses=ERRORS,
    summary="歷史日行情",
)
async def get_stock_history(
    stock_id: StockId,
    request: Request,
    period: Annotated[
        str | None, Query(description="5d、1mo、3mo、6mo、1y；與起訖日期擇一，都不給時為 1mo")
    ] = None,
    start_date: Annotated[date | None, Query(description="起始日 YYYY-MM-DD")] = None,
    end_date: Annotated[date | None, Query(description="結束日 YYYY-MM-DD，預設今天")] = None,
) -> Envelope[StockHistory]:
    return await request.app.state.history.get_history(
        stock_id, period=period, start_date=start_date, end_date=end_date
    )


@router.get(
    "/{stock_id}/institutional-flow",
    response_model=Envelope[InstitutionalFlow],
    responses=ERRORS,
    summary="三大法人買賣超",
)
async def get_institutional_flow(
    stock_id: StockId,
    request: Request,
    start_date: Annotated[date | None, Query(description="起始日，預設 14 天前")] = None,
    end_date: Annotated[date | None, Query(description="結束日，預設今天")] = None,
) -> Envelope[InstitutionalFlow]:
    return await request.app.state.institutional.get_flow(
        stock_id, start_date=start_date, end_date=end_date
    )


@router.get(
    "/{stock_id}/indicators",
    response_model=Envelope[TechnicalIndicators],
    responses=ERRORS,
    summary="技術指標",
)
async def get_technical_indicators(
    stock_id: StockId,
    request: Request,
    indicators: Annotated[
        list[Annotated[str, StringConstraints(max_length=64)]] | None,
        Query(
            description="指標名稱，可重複或以逗號分隔：MA2–MA120、RSI2–RSI30、MACD；"
            "不給時為 MA5、MA20、RSI14、MACD",
            max_length=16,
        ),
    ] = None,
    period: Annotated[
        str | None, Query(description="5d、1mo、3mo、6mo、1y；與起訖日期擇一，都不給時為 3mo")
    ] = None,
    start_date: Annotated[date | None, Query(description="起始日 YYYY-MM-DD")] = None,
    end_date: Annotated[date | None, Query(description="結束日 YYYY-MM-DD，預設今天")] = None,
) -> Envelope[TechnicalIndicators]:
    return await request.app.state.indicators.get_indicators(
        stock_id, indicators=indicators, period=period, start_date=start_date, end_date=end_date
    )
