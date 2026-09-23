from __future__ import annotations

import sqlite3
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

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
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                payment_method TEXT NOT NULL CHECK(payment_method IN ('card', 'pix', 'boleto')),
                status TEXT NOT NULL DEFAULT 'paid' CHECK(status IN ('paid', 'cancelled')),
                total REAL NOT NULL CHECK(total >= 0),
                shipping_address TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_title TEXT NOT NULL,
                unit_price REAL NOT NULL CHECK(unit_price > 0),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                total REAL NOT NULL CHECK(total > 0)
            );
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                expense_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
            CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
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
    cleaned_name = name.strip()
    with connect() as connection:
        if connection.execute(
            "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE", (cleaned_name,)
        ).fetchone():
            raise sqlite3.IntegrityError("category name already exists")
        base_slug = slugify(cleaned_name) or "categoria"
        slug = base_slug
        counter = 2
        while connection.execute("SELECT 1 FROM categories WHERE slug = ?", (slug,)).fetchone():
            slug = f"{base_slug}-{counter}"
            counter += 1
        cursor = connection.execute(
            "INSERT INTO categories (name, slug, created_at) VALUES (?, ?, ?)",
            (cleaned_name, slug, utc_now()),
        )
        category_id = cursor.lastrowid
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


def get_order(order_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        order = connection.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not order:
            return None
        items = connection.execute(
            """
            SELECT product_id, product_title, unit_price, quantity, total
            FROM order_items WHERE order_id = ? ORDER BY id
            """,
            (order_id,),
        ).fetchall()
    result = dict(order)
    result["items"] = [dict(item) for item in items]
    return result


def create_order(data: dict[str, Any]) -> dict[str, Any]:
    now = utc_now()
    order_number = f"VTR{datetime.now(timezone.utc).strftime('%y%m%d')}{uuid4().hex[:6].upper()}"
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        prepared_items: list[dict[str, Any]] = []
        total = 0.0
        for requested in data["items"]:
            product = connection.execute(
                "SELECT id, title, price, stock, active FROM products WHERE id = ?",
                (requested["product_id"],),
            ).fetchone()
            if not product or not product["active"]:
                raise ValueError("Um dos produtos não está mais disponível.")
            quantity = requested["quantity"]
            if product["stock"] < quantity:
                raise ValueError(f"Estoque insuficiente para {product['title']}.")
            item_total = round(product["price"] * quantity, 2)
            total += item_total
            prepared_items.append(
                {
                    "product_id": product["id"],
                    "product_title": product["title"],
                    "unit_price": product["price"],
                    "quantity": quantity,
                    "total": item_total,
                }
            )

        cursor = connection.execute(
            """
            INSERT INTO orders (
                order_number, customer_name, customer_email, payment_method,
                status, total, shipping_address, created_at
            ) VALUES (?, ?, ?, ?, 'paid', ?, ?, ?)
            """,
            (
                order_number,
                data["customer_name"],
                data["customer_email"],
                data["payment_method"],
                round(total, 2),
                data["shipping_address"],
                now,
            ),
        )
        order_id = cursor.lastrowid
        for item in prepared_items:
            connection.execute(
                """
                INSERT INTO order_items (
                    order_id, product_id, product_title, unit_price, quantity, total
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    item["product_id"],
                    item["product_title"],
                    item["unit_price"],
                    item["quantity"],
                    item["total"],
                ),
            )
            connection.execute(
                "UPDATE products SET stock = stock - ?, updated_at = ? WHERE id = ?",
                (item["quantity"], now, item["product_id"]),
            )
    return get_order(order_id)  # type: ignore[return-value]


def list_orders(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{**dict(row), "items": []} for row in rows]


def create_expense(data: dict[str, Any]) -> dict[str, Any]:
    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO expenses (description, category, amount, expense_date, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                data["description"].strip(),
                data["category"].strip(),
                data["amount"],
                str(data["expense_date"]),
                utc_now(),
            ),
        )
        expense_id = cursor.lastrowid
        row = connection.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return dict(row)


def delete_expense(expense_id: int) -> bool:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    return cursor.rowcount > 0


def sales_report(days: int) -> dict[str, Any]:
    start = (datetime.now(timezone.utc) - timedelta(days=days - 1)).date().isoformat()
    with connect() as connection:
        summary = connection.execute(
            """
            SELECT COUNT(*) AS orders_count, COALESCE(SUM(total), 0) AS total_revenue
            FROM orders WHERE status = 'paid' AND date(created_at) >= date(?)
            """,
            (start,),
        ).fetchone()
        items_sold = connection.execute(
            """
            SELECT COALESCE(SUM(oi.quantity), 0)
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.status = 'paid' AND date(o.created_at) >= date(?)
            """,
            (start,),
        ).fetchone()[0]
        total_expenses = connection.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date(expense_date) >= date(?)",
            (start,),
        ).fetchone()[0]
        sales_by_day = connection.execute(
            """
            SELECT date(created_at) AS date, COUNT(*) AS orders, ROUND(SUM(total), 2) AS revenue
            FROM orders WHERE status = 'paid' AND date(created_at) >= date(?)
            GROUP BY date(created_at) ORDER BY date(created_at)
            """,
            (start,),
        ).fetchall()
        payment_methods = connection.execute(
            """
            SELECT payment_method AS method, COUNT(*) AS orders, ROUND(SUM(total), 2) AS revenue
            FROM orders WHERE status = 'paid' AND date(created_at) >= date(?)
            GROUP BY payment_method ORDER BY revenue DESC
            """,
            (start,),
        ).fetchall()
        top_products = connection.execute(
            """
            SELECT oi.product_title AS title, SUM(oi.quantity) AS quantity,
                ROUND(SUM(oi.total), 2) AS revenue
            FROM order_items oi JOIN orders o ON o.id = oi.order_id
            WHERE o.status = 'paid' AND date(o.created_at) >= date(?)
            GROUP BY oi.product_title ORDER BY quantity DESC, revenue DESC LIMIT 5
            """,
            (start,),
        ).fetchall()
        recent_orders = connection.execute(
            """
            SELECT order_number, customer_name, payment_method, status, total, created_at
            FROM orders WHERE date(created_at) >= date(?)
            ORDER BY created_at DESC LIMIT 8
            """,
            (start,),
        ).fetchall()
        expenses = connection.execute(
            """
            SELECT * FROM expenses WHERE date(expense_date) >= date(?)
            ORDER BY expense_date DESC, id DESC
            """,
            (start,),
        ).fetchall()

    revenue = round(summary["total_revenue"], 2)
    expense_total = round(total_expenses, 2)
    order_count = summary["orders_count"]
    return {
        "days": days,
        "total_revenue": revenue,
        "total_expenses": expense_total,
        "net_balance": round(revenue - expense_total, 2),
        "orders_count": order_count,
        "average_ticket": round(revenue / order_count, 2) if order_count else 0,
        "items_sold": items_sold,
        "sales_by_day": [dict(row) for row in sales_by_day],
        "payment_methods": [dict(row) for row in payment_methods],
        "top_products": [dict(row) for row in top_products],
        "recent_orders": [dict(row) for row in recent_orders],
        "expenses": [dict(row) for row in expenses],
    }
