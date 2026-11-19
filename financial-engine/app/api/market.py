from fastapi import APIRouter, Request

from app.schemas.common import Envelope, ErrorEnvelope, Market
from app.schemas.stock import MarketSummary

router = APIRouter(prefix="/market", tags=["market"])


@router.get(
    "/{market}/summary",
    response_model=Envelope[MarketSummary],
    responses={422: {"model": ErrorEnvelope}, 502: {"model": ErrorEnvelope}},
    summary="大盤概況（盤後）",
)
async def get_market_summary(market: Market, request: Request) -> Envelope[MarketSummary]:
    return await request.app.state.market.get_summary(market)
