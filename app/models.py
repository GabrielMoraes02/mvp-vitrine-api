from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


ProductSource = Literal["local", "fake_store"]


class ProductBase(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=2, max_length=1200)
    price: float = Field(gt=0)
    category: str = Field(min_length=2, max_length=80)
    image: HttpUrl
    stock: int = Field(default=10, ge=0, le=100_000)
    active: bool = True
    rating: float = Field(default=0, ge=0, le=5)
    rating_count: int = Field(default=0, ge=0)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    description: Optional[str] = Field(default=None, min_length=2, max_length=1200)
    price: Optional[float] = Field(default=None, gt=0)
    category: Optional[str] = Field(default=None, min_length=2, max_length=80)
    image: Optional[HttpUrl] = None
    stock: Optional[int] = Field(default=None, ge=0, le=100_000)
    active: Optional[bool] = None


class Product(ProductBase):
    id: int
    external_id: Optional[int] = None
    source: ProductSource
    created_at: datetime
    updated_at: datetime


class ProductList(BaseModel):
    items: list[Product]
    total: int
    page: int
    page_size: int


class DashboardSummary(BaseModel):
    total_products: int
    active_products: int
    low_stock_products: int
    average_price: float
    products_by_category: dict[str, int]


class SyncResult(BaseModel):
    imported: int
    updated: int
    total_received: int
    source: str = "Fake Store API"
