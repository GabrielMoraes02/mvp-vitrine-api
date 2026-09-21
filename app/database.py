from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DATABASE_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(database_path: Path | None = None) -> sqlite3.Connection:
    path = database_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(database_path: Path | None = None) -> None:
    with connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id INTEGER UNIQUE,
                source TEXT NOT NULL CHECK(source IN ('local', 'fake_store')),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL CHECK(price > 0),
                category TEXT NOT NULL,
                image TEXT NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
                active INTEGER NOT NULL DEFAULT 1,
                rating REAL NOT NULL DEFAULT 0,
                rating_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
            CREATE INDEX IF NOT EXISTS idx_products_active ON products(active);
            """
        )


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    product = dict(row)
    product["active"] = bool(product["active"])
    return product


def list_products(
    *,
    search: str | None,
    category: str | None,
    active: bool | None,
    source: str | None,
    page: int,
    page_size: int,
    sort: str,
) -> tuple[list[dict[str, Any]], int]:
    conditions: list[str] = []
    parameters: list[Any] = []

    if search:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
        term = f"%{search.lower()}%"
        parameters.extend([term, term])
    if category:
        conditions.append("category = ?")
        parameters.append(category)
    if active is not None:
        conditions.append("active = ?")
        parameters.append(int(active))
    if source:
        conditions.append("source = ?")
        parameters.append(source)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order_by = {
        "newest": "created_at DESC",
        "price_asc": "price ASC",
        "price_desc": "price DESC",
        "rating": "rating DESC",
        "title": "title COLLATE NOCASE ASC",
    }.get(sort, "created_at DESC")

    with connect() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) FROM products {where_clause}", parameters
        ).fetchone()[0]
        rows = connection.execute(
            f"SELECT * FROM products {where_clause} ORDER BY {order_by} LIMIT ? OFFSET ?",
            [*parameters, page_size, (page - 1) * page_size],
        ).fetchall()
    return [row_to_dict(row) for row in rows], total


def get_product(product_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    return row_to_dict(row) if row else None


def create_product(data: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    values = {
        **data,
        "image": str(data["image"]),
        "source": "local",
        "external_id": None,
        "created_at": now,
        "updated_at": now,
    }
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    with connect() as connection:
        cursor = connection.execute(
            f"INSERT INTO products ({columns}) VALUES ({placeholders})", tuple(values.values())
        )
        product_id = cursor.lastrowid
    return get_product(product_id)  # type: ignore[return-value]


def update_product(product_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    if not data:
        return get_product(product_id)
    normalized = {key: (str(value) if key == "image" else value) for key, value in data.items()}
    normalized["updated_at"] = utc_now()
    assignments = ", ".join(f"{key} = ?" for key in normalized)
    with connect() as connection:
        cursor = connection.execute(
            f"UPDATE products SET {assignments} WHERE id = ?",
            (*normalized.values(), product_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_product(product_id)


def delete_product(product_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
    return cursor.rowcount > 0


def upsert_external_product(data: dict[str, Any]) -> str:
    now = utc_now()
    external_id = int(data["external_id"])
    with connect() as connection:
        existing = connection.execute(
            "SELECT id FROM products WHERE external_id = ?", (external_id,)
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE products SET title = ?, description = ?, price = ?, category = ?, image = ?,
                    rating = ?, rating_count = ?, updated_at = ?
                WHERE external_id = ?
                """,
                (
                    data["title"], data["description"], data["price"], data["category"],
                    data["image"], data["rating"], data["rating_count"], now, external_id,
                ),
            )
            return "updated"
        connection.execute(
            """
            INSERT INTO products (
                external_id, source, title, description, price, category, image, stock,
                active, rating, rating_count, created_at, updated_at
            ) VALUES (?, 'fake_store', ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                external_id, data["title"], data["description"], data["price"], data["category"],
                data["image"], data["stock"], data["rating"], data["rating_count"], now, now,
            ),
        )
        return "imported"


def dashboard_summary() -> dict[str, Any]:
    with connect() as connection:
        totals = connection.execute(
            """
            SELECT COUNT(*) AS total_products,
                SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) AS active_products,
                SUM(CASE WHEN stock <= 5 THEN 1 ELSE 0 END) AS low_stock_products,
                COALESCE(AVG(price), 0) AS average_price
            FROM products
            """
        ).fetchone()
        categories = connection.execute(
            "SELECT category, COUNT(*) AS count FROM products GROUP BY category ORDER BY count DESC"
        ).fetchall()
    return {
        "total_products": totals["total_products"],
        "active_products": totals["active_products"] or 0,
        "low_stock_products": totals["low_stock_products"] or 0,
        "average_price": round(totals["average_price"], 2),
        "products_by_category": {row["category"]: row["count"] for row in categories},
    }
