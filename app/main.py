from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import database
from .config import FRONTEND_ORIGINS
from .models import (
    Category,
    CategoryCreate,
    CategoryUpdate,
    DashboardSummary,
    Expense,
    ExpenseCreate,
    Order,
    OrderCreate,
    Product,
    ProductCreate,
    ProductList,
    ProductUpdate,
    SyncResult,
    SalesReport,
    Subcategory,
    SubcategoryCreate,
    SubcategoryUpdate,
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
        "de um catálogo público externo."
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


def validate_product_classification(
    data: dict, current: Optional[dict] = None
) -> dict:
    """Keep product category and subcategory references consistent."""
    merged = {**(current or {}), **data}
    category_id = merged.get("category_id")
    subcategory_id = merged.get("subcategory_id")

    if category_id is None:
        if subcategory_id is not None:
            raise HTTPException(
                status_code=422,
                detail="Selecione uma categoria para usar esta subcategoria.",
            )
        return data

    category = database.get_category(category_id)
    if not category:
        raise HTTPException(status_code=422, detail="Categoria inválida.")

    if subcategory_id is not None:
        subcategory = database.get_subcategory(subcategory_id)
        if not subcategory:
            raise HTTPException(status_code=422, detail="Subcategoria inválida.")
        if subcategory["category_id"] != category_id:
            raise HTTPException(
                status_code=422,
                detail="A subcategoria não pertence à categoria selecionada.",
            )

    data["category"] = category["name"]
    return data


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
    data = validate_product_classification(payload.model_dump())
    return Product(**database.create_product(data))


@app.patch("/api/products/{product_id}", response_model=Product, tags=["Produtos"])
def patch_product(product_id: int, payload: ProductUpdate) -> Product:
    current = database.get_product(product_id)
    if not current:
        raise HTTPException(status_code=404, detail="Produto não encontrado.")
    data = validate_product_classification(
        payload.model_dump(exclude_unset=True), current=current
    )
    product = database.update_product(product_id, data)
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
async def sync_external_catalog() -> SyncResult:
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


@app.get("/api/categories", response_model=list[Category], tags=["Categorias"])
def get_categories() -> list[Category]:
    return [Category(**item) for item in database.list_categories()]


@app.post("/api/categories", response_model=Category, status_code=201, tags=["Categorias"])
def post_category(payload: CategoryCreate) -> Category:
    try:
        return Category(**database.create_category(payload.name))
    except Exception as error:
        raise HTTPException(status_code=409, detail="Já existe uma categoria com esse nome.") from error


@app.patch("/api/categories/{category_id}", response_model=Category, tags=["Categorias"])
def patch_category(category_id: int, payload: CategoryUpdate) -> Category:
    try:
        category = database.update_category(category_id, payload.name)
    except Exception as error:
        raise HTTPException(status_code=409, detail="Nome de categoria já utilizado.") from error
    if not category:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return Category(**category)


@app.delete("/api/categories/{category_id}", status_code=204, tags=["Categorias"])
def remove_category(category_id: int) -> Response:
    deleted, reason = database.delete_category(category_id)
    if not deleted:
        if reason == "in_use":
            raise HTTPException(status_code=409, detail="A categoria possui produtos ou subcategorias vinculados.")
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return Response(status_code=204)


@app.get("/api/subcategories", response_model=list[Subcategory], tags=["Subcategorias"])
def get_subcategories(category_id: Optional[int] = None) -> list[Subcategory]:
    return [Subcategory(**item) for item in database.list_subcategories(category_id)]


@app.post("/api/subcategories", response_model=Subcategory, status_code=201, tags=["Subcategorias"])
def post_subcategory(payload: SubcategoryCreate) -> Subcategory:
    try:
        subcategory = database.create_subcategory(payload.name, payload.category_id)
    except Exception as error:
        raise HTTPException(status_code=409, detail="Já existe uma subcategoria com esse nome.") from error
    if not subcategory:
        raise HTTPException(status_code=404, detail="Categoria não encontrada.")
    return Subcategory(**subcategory)


@app.patch("/api/subcategories/{subcategory_id}", response_model=Subcategory, tags=["Subcategorias"])
def patch_subcategory(subcategory_id: int, payload: SubcategoryUpdate) -> Subcategory:
    try:
        subcategory = database.update_subcategory(
            subcategory_id, payload.model_dump(exclude_unset=True)
        )
    except Exception as error:
        raise HTTPException(status_code=409, detail="Nome de subcategoria já utilizado.") from error
    if not subcategory:
        raise HTTPException(status_code=404, detail="Subcategoria ou categoria não encontrada.")
    return Subcategory(**subcategory)


@app.delete("/api/subcategories/{subcategory_id}", status_code=204, tags=["Subcategorias"])
def remove_subcategory(subcategory_id: int) -> Response:
    deleted, reason = database.delete_subcategory(subcategory_id)
    if not deleted:
        if reason == "in_use":
            raise HTTPException(status_code=409, detail="A subcategoria possui produtos vinculados.")
        raise HTTPException(status_code=404, detail="Subcategoria não encontrada.")
    return Response(status_code=204)


@app.post("/api/orders", response_model=Order, status_code=201, tags=["Vendas"])
def post_order(payload: OrderCreate) -> Order:
    try:
        return Order(**database.create_order(payload.model_dump()))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/orders", response_model=list[Order], tags=["Vendas"])
def get_orders(limit: int = Query(default=50, ge=1, le=100)) -> list[Order]:
    return [Order(**item) for item in database.list_orders(limit)]


@app.get("/api/reports/sales", response_model=SalesReport, tags=["Relatórios"])
def get_sales_report(
    days: int = Query(default=30, ge=1, le=365)
) -> SalesReport:
    return SalesReport(**database.sales_report(days))


@app.post("/api/expenses", response_model=Expense, status_code=201, tags=["Financeiro"])
def post_expense(payload: ExpenseCreate) -> Expense:
    return Expense(**database.create_expense(payload.model_dump()))


@app.delete("/api/expenses/{expense_id}", status_code=204, tags=["Financeiro"])
def remove_expense(expense_id: int) -> Response:
    if not database.delete_expense(expense_id):
        raise HTTPException(status_code=404, detail="Despesa não encontrada.")
    return Response(status_code=204)
