from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.connectors.amazon import AmazonSPAPIClient
from app.connectors.qoo10 import Qoo10Client
from app.connectors.shopee import ShopeeClient
from app.db import Database
from app.models import ListingRequest
from app.services import CatalogService, DuplicateListingError, MarketplaceService


class Container:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_url)
        self.amazon = AmazonSPAPIClient(settings)
        self.shopee = ShopeeClient(settings)
        self.qoo10 = Qoo10Client(settings)
        self.catalog = CatalogService(settings, self.db, self.amazon)
        self.marketplaces = MarketplaceService(
            settings, self.db, self.catalog, self.shopee, self.qoo10
        )
        self.stop = asyncio.Event()
        self.scheduler_task: asyncio.Task[None] | None = None

    async def close(self) -> None:
        self.stop.set()
        if self.scheduler_task:
            await self.scheduler_task
        await self.amazon.close()
        await self.shopee.close()
        await self.qoo10.close()


async def run_preflight(
    container: Container, settings: Settings, asin: str | None = None
) -> dict[str, Any]:
    issues = settings.production_configuration_issues(include_api_token=False)
    result: dict[str, Any] = {
        "status": "ready" if not issues else "blocked",
        "missing_config": issues,
        "checks": {},
    }
    if issues:
        return result
    result["checks"]["amazon"] = await container.amazon.check_connection(asin)
    if "shopee" in settings.enabled_channels:
        result["checks"]["shopee"] = await container.shopee.check_connection()
    return result


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or get_settings()
    container = Container(selected)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if selected.enable_background_sync:
            container.scheduler_task = asyncio.create_task(
                container.marketplaces.scheduler(container.stop)
            )
        yield
        await container.close()

    docs_url = "/docs" if not selected.is_production or selected.enable_docs else None
    app = FastAPI(
        title=selected.app_name,
        version="0.2.0",
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
    )
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=selected.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    async def require_api_access(
        authorization: str | None = Header(default=None),
        x_api_key: str | None = Header(default=None),
    ) -> None:
        if not selected.is_production:
            return
        if len(selected.app_api_token) < 32:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="APP_API_TOKEN must contain at least 32 characters",
            )
        bearer = ""
        if authorization and authorization.lower().startswith("bearer "):
            bearer = authorization[7:].strip()
        provided = x_api_key or bearer
        if not provided or not secrets.compare_digest(provided, selected.app_api_token):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="A valid API token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        issues = selected.production_configuration_issues(include_api_token=True)
        return {
            "status": "ready" if not issues else "degraded",
            "mode": selected.app_mode,
            "live_api_enabled": selected.api_live_enabled,
            "amazon_source": "SP-API",
            "exact_amazon_stock_quantity": False,
            "enabled_channels": selected.enabled_channels,
            "missing_config": issues,
        }

    @app.post("/api/preflight", dependencies=[Depends(require_api_access)])
    async def preflight(asin: str | None = Query(default=None)) -> dict[str, Any]:
        try:
            return await run_preflight(container, selected, asin)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/api/products/{asin}/fetch", dependencies=[Depends(require_api_access)]
    )
    async def fetch_product(
        asin: str, force: bool = Query(default=False)
    ) -> dict[str, Any]:
        try:
            return (await container.catalog.fetch(asin, force=force)).model_dump()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/products", dependencies=[Depends(require_api_access)])
    async def products() -> list[dict[str, Any]]:
        return [item.model_dump() for item in container.db.list_products()]

    @app.post("/api/listings", dependencies=[Depends(require_api_access)])
    async def create_listing(request: ListingRequest) -> dict[str, Any]:
        try:
            return {"results": await container.marketplaces.create_listings(request)}
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except DuplicateListingError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/listings", dependencies=[Depends(require_api_access)])
    async def listings() -> list[dict[str, Any]]:
        return container.db.list_listings()

    @app.post("/api/sync/run", dependencies=[Depends(require_api_access)])
    async def sync_run() -> dict[str, Any]:
        return await container.marketplaces.sync_all()

    static_index = Path(__file__).parent / "static" / "index.html"

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static_index)

    return app


app = create_app()
