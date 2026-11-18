from typing import Annotated

from fastapi import APIRouter, Path, Request

from app.schemas.common import STOCK_ID_PATTERN, Envelope, ErrorEnvelope
from app.schemas.stock import StockInfo
from app.services.stock_service import StockService

router = APIRouter(prefix="/stocks", tags=["stocks"])

StockId = Annotated[
    str, Path(pattern=STOCK_ID_PATTERN, description="台股證券代號，例如 2330", examples=["2330"])
]


@router.get(
    "/{stock_id}",
    response_model=Envelope[StockInfo],
    responses={404: {"model": ErrorEnvelope}, 502: {"model": ErrorEnvelope}},
    summary="股票基本資料",
)
async def get_stock_info(stock_id: StockId, request: Request) -> Envelope[StockInfo]:
    service: StockService = request.app.state.stock_service
    return await service.get_stock_info(stock_id)
