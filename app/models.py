from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


ProductSource = Literal["local", "fake_store"]


class ProductBase(BaseModel):
    title: str = Field(min_length=2, max_length=160)
    description: str = Field(min_length=2, max_length=1200)
    price: float = Field(gt=0)
    category: str = Field(min_length=2, max_length=80)
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
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
    category_id: Optional[int] = None
    subcategory_id: Optional[int] = None
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
    source: str = "Catálogo externo"


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class CategoryUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)


class Category(BaseModel):
    id: int
    name: str
    slug: str
    product_count: int = 0
    subcategory_count: int = 0
    created_at: datetime


class SubcategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    category_id: int


class SubcategoryUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    category_id: Optional[int] = None


class Subcategory(BaseModel):
    id: int
    name: str
    slug: str
    category_id: int
    category_name: str
    product_count: int = 0
    created_at: datetime


PaymentMethod = Literal["card", "pix", "boleto"]


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    customer_email: str = Field(min_length=5, max_length=160)
    payment_method: PaymentMethod
    shipping_address: str = Field(min_length=8, max_length=500)
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItem(BaseModel):
    product_id: Optional[int] = None
    product_title: str
    unit_price: float
    quantity: int
    total: float


class Order(BaseModel):
    id: int
    order_number: str
    customer_name: str
    customer_email: str
    payment_method: PaymentMethod
    status: str
    total: float
    shipping_address: str
    created_at: datetime
    items: list[OrderItem] = Field(default_factory=list)


class ExpenseCreate(BaseModel):
    description: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    amount: float = Field(gt=0)
    expense_date: date


class Expense(BaseModel):
    id: int
    description: str
    category: str
    amount: float
    expense_date: date
    created_at: datetime


class SalesReport(BaseModel):
    days: int
    total_revenue: float
    total_expenses: float
    net_balance: float
    orders_count: int
    average_ticket: float
    items_sold: int
    sales_by_day: list[dict]
    payment_methods: list[dict]
    top_products: list[dict]
    recent_orders: list[dict]
    expenses: list[Expense]
