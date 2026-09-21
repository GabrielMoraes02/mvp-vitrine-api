from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .config import FRONTEND_ORIGINS
from .models import (
    DashboardSummary,
    Product,
    ProductCreate,
    ProductList,
    ProductUpdate,
    SyncResult,
)
from .services.fake_store import FakeStoreUnavailable, fetch_products


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_database()
    yield


app = FastAPI(
    title="Vitrine API",
    version="1.0.0",
    description=(
        "API do MVP Vitrine. Gerencia o catálogo local em SQLite e integra produtos "
        "da Fake Store API."
    ),
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products", response_model=ProductList, tags=["Produtos"])
def get_products(
    search: Optional[str] = None,
    category: Optional[str] = None,
    active: Optional[bool] = None,
    source: Optional[Literal["local", "fake_store"]] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    sort: Literal["newest", "price_asc", "price_desc", "rating", "title"] = "newest",
) -> ProductList:
    items, total = database.list_products(
        search=search,
        category=category,
        active=active,
        source=source,
        page=page,
        page_size=page_size,
        sort=sort,
    )
    return ProductList(items=items, total=total, page=page, page_size=page_size)


@app.get("/api/products/{product_id}", response_model=Product, tags=["Produtos"])
def get_product(product_id: int) -> Product:
    product = database.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return Product(**product)


@app.post(
    "/api/products",
    response_model=Product,
    status_code=status.HTTP_201_CREATED,
    tags=["Produtos"],
)
def create_product(payload: ProductCreate) -> Product:
    return Product(**database.create_product(payload.model_dump()))


@app.patch("/api/products/{product_id}", response_model=Product, tags=["Produtos"])
def patch_product(product_id: int, payload: ProductUpdate) -> Product:
    product = database.update_product(product_id, payload.model_dump(exclude_unset=True))
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return Product(**product)


@app.delete(
    "/api/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Produtos"],
)
def remove_product(product_id: int) -> Response:
    if not database.delete_product(product_id):
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/products/sync", response_model=SyncResult, tags=["Integrações"])
async def sync_fake_store() -> SyncResult:
    try:
        products = await fetch_products()
    except FakeStoreUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    imported = 0
    updated = 0
    for product in products:
        operation = database.upsert_external_product(product)
        imported += operation == "imported"
        updated += operation == "updated"
    return SyncResult(imported=imported, updated=updated, total_received=len(products))


@app.get("/api/dashboard", response_model=DashboardSummary, tags=["Administração"])
def get_dashboard() -> DashboardSummary:
    return DashboardSummary(**database.dashboard_summary())
