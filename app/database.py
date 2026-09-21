from __future__ import annotations

import sqlite3
import re
import unicodedata
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
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS subcategories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(category_id, name COLLATE NOCASE),
                UNIQUE(category_id, slug)
            );
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                external_id INTEGER UNIQUE,
                source TEXT NOT NULL CHECK(source IN ('local', 'fake_store')),
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                price REAL NOT NULL CHECK(price > 0),
                category TEXT NOT NULL,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL,
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
        product_columns = {row["name"] for row in connection.execute("PRAGMA table_info(products)")}
        if "category_id" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL")
        if "subcategory_id" not in product_columns:
            connection.execute("ALTER TABLE products ADD COLUMN subcategory_id INTEGER REFERENCES subcategories(id) ON DELETE SET NULL")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_products_category_id ON products(category_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_products_subcategory_id ON products(subcategory_id)")
        existing_categories = connection.execute("SELECT DISTINCT category FROM products").fetchall()
        for row in existing_categories:
            category_id = _ensure_category(connection, row["category"])
            connection.execute(
                "UPDATE products SET category_id = ? WHERE category = ? AND category_id IS NULL",
                (category_id, row["category"]),
            )


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def _ensure_category(connection: sqlite3.Connection, name: str) -> int:
    existing = connection.execute("SELECT id FROM categories WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if existing:
        return existing["id"]
    base_slug = slugify(name) or "categoria"
    slug = base_slug
    counter = 2
    while connection.execute("SELECT 1 FROM categories WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base_slug}-{counter}"
        counter += 1
    cursor = connection.execute(
        "INSERT INTO categories (name, slug, created_at) VALUES (?, ?, ?)",
        (name.strip(), slug, utc_now()),
    )
    return cursor.lastrowid


def ensure_category(name: str) -> int:
    with connect() as connection:
        return _ensure_category(connection, name)


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
    if not data.get("category_id"):
        data["category_id"] = ensure_category(data["category"])
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
        category_id = _ensure_category(connection, data["category"])
        existing = connection.execute(
            "SELECT id FROM products WHERE external_id = ?", (external_id,)
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE products SET title = ?, description = ?, price = ?, category = ?, category_id = ?, image = ?,
                    rating = ?, rating_count = ?, updated_at = ?
                WHERE external_id = ?
                """,
                (
                    data["title"], data["description"], data["price"], data["category"], category_id,
                    data["image"], data["rating"], data["rating_count"], now, external_id,
                ),
            )
            return "updated"
        connection.execute(
            """
            INSERT INTO products (
                external_id, source, title, description, price, category, category_id, image, stock,
                active, rating, rating_count, created_at, updated_at
            ) VALUES (?, 'fake_store', ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
            """,
            (
                external_id, data["title"], data["description"], data["price"], data["category"], category_id,
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


def list_categories() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT c.*, COUNT(DISTINCT p.id) AS product_count,
                COUNT(DISTINCT s.id) AS subcategory_count
            FROM categories c
            LEFT JOIN products p ON p.category_id = c.id
            LEFT JOIN subcategories s ON s.category_id = c.id
            GROUP BY c.id
            ORDER BY c.name COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_category(category_id: int) -> dict[str, Any] | None:
    return next((item for item in list_categories() if item["id"] == category_id), None)


def create_category(name: str) -> dict[str, Any]:
    with connect() as connection:
        category_id = _ensure_category(connection, name.strip())
    return get_category(category_id)  # type: ignore[return-value]


def update_category(category_id: int, name: str) -> dict[str, Any] | None:
    category = get_category(category_id)
    if not category:
        return None
    new_slug = slugify(name) or f"categoria-{category_id}"
    with connect() as connection:
        connection.execute(
            "UPDATE categories SET name = ?, slug = ? WHERE id = ?",
            (name.strip(), new_slug, category_id),
        )
        connection.execute(
            "UPDATE products SET category = ? WHERE category_id = ?",
            (name.strip(), category_id),
        )
    return get_category(category_id)


def delete_category(category_id: int) -> tuple[bool, str | None]:
    category = get_category(category_id)
    if not category:
        return False, "not_found"
    if category["product_count"] or category["subcategory_count"]:
        return False, "in_use"
    with connect() as connection:
        connection.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    return True, None


def list_subcategories(category_id: int | None = None) -> list[dict[str, Any]]:
    where = "WHERE s.category_id = ?" if category_id else ""
    parameters = (category_id,) if category_id else ()
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT s.*, c.name AS category_name, COUNT(p.id) AS product_count
            FROM subcategories s
            JOIN categories c ON c.id = s.category_id
            LEFT JOIN products p ON p.subcategory_id = s.id
            {where}
            GROUP BY s.id
            ORDER BY c.name COLLATE NOCASE, s.name COLLATE NOCASE
            """,
            parameters,
        ).fetchall()
    return [dict(row) for row in rows]


def get_subcategory(subcategory_id: int) -> dict[str, Any] | None:
    return next((item for item in list_subcategories() if item["id"] == subcategory_id), None)


def create_subcategory(name: str, category_id: int) -> dict[str, Any] | None:
    if not get_category(category_id):
        return None
    with connect() as connection:
        base_slug = slugify(name) or "subcategoria"
        slug = base_slug
        counter = 2
        while connection.execute(
            "SELECT 1 FROM subcategories WHERE category_id = ? AND slug = ?", (category_id, slug)
        ).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1
        cursor = connection.execute(
            "INSERT INTO subcategories (category_id, name, slug, created_at) VALUES (?, ?, ?, ?)",
            (category_id, name.strip(), slug, utc_now()),
        )
        subcategory_id = cursor.lastrowid
    return get_subcategory(subcategory_id)


def update_subcategory(subcategory_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
    current = get_subcategory(subcategory_id)
    if not current:
        return None
    category_id = data.get("category_id", current["category_id"])
    name = data.get("name", current["name"])
    if not get_category(category_id):
        return None
    with connect() as connection:
        connection.execute(
            "UPDATE subcategories SET category_id = ?, name = ?, slug = ? WHERE id = ?",
            (category_id, name.strip(), slugify(name), subcategory_id),
        )
    return get_subcategory(subcategory_id)


def delete_subcategory(subcategory_id: int) -> tuple[bool, str | None]:
    subcategory = get_subcategory(subcategory_id)
    if not subcategory:
        return False, "not_found"
    if subcategory["product_count"]:
        return False, "in_use"
    with connect() as connection:
        connection.execute("DELETE FROM subcategories WHERE id = ?", (subcategory_id,))
    return True, None
