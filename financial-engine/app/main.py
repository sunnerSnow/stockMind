"""StockMind Financial Engine：資料來源介接與金融計算的 HTTP API。不依賴 MCP。"""

import logging
from collections.abc import Sequence
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import market, stocks
from app.core.config import Settings, load_settings
from app.core.errors import EngineError
from app.data_providers.base import MarketProvider
from app.data_providers.http import Fetcher
from app.data_providers.tpex import TpexProvider
from app.data_providers.twse import TwseProvider
from app.services.history import HistoryService
from app.services.institutional import InstitutionalService
from app.services.market import MarketService
from app.services.securities import SecuritiesService

logger = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"success": False, "error": {"code": code, "message": message}},
    )


def create_app(
    *,
    settings: Settings | None = None,
    providers: Sequence[MarketProvider] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """providers 與 transport 可注入，測試時不需連到真實來源。"""
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(
            headers={"User-Agent": settings.user_agent, "Accept": "application/json"},
            transport=transport,
            follow_redirects=False,
        ) as client:
            fetcher = Fetcher(client, settings)
            securities = SecuritiesService(fetcher, providers or [TwseProvider(), TpexProvider()])
            history = HistoryService(fetcher, securities)
            app.state.securities = securities
            app.state.history = history
            app.state.institutional = InstitutionalService(fetcher, securities, history)
            app.state.market = MarketService(fetcher, securities)
            yield

    app = FastAPI(title="StockMind Financial Engine", version="0.1.0", lifespan=lifespan)
    app.include_router(stocks.router)
    app.include_router(market.router)

    @app.get("/health", tags=["system"], summary="健康檢查")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "stockmind-engine", "version": app.version}

    @app.exception_handler(EngineError)
    async def handle_engine_error(_: Request, exc: EngineError) -> JSONResponse:
        return _error(exc.http_status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = "、".join(str(e["loc"][-1]) for e in exc.errors()) or "參數"
        return _error(422, "INVALID_INPUT", f"參數格式錯誤：{fields}")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("未預期的錯誤", exc_info=exc)
        return _error(500, "INTERNAL_ERROR", "伺服器發生未預期的錯誤")

    return app


app = create_app()
