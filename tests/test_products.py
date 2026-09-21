from pathlib import Path

from fastapi.testclient import TestClient

from app import database
from app.main import app


def test_product_crud(tmp_path: Path, monkeypatch) -> None:
    test_database = tmp_path / "test.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_database)

    with TestClient(app) as client:
        created = client.post(
            "/api/products",
            json={
                "title": "Produto de teste",
                "description": "Produto usado para validar o fluxo completo.",
                "price": 99.9,
                "category": "Testes",
                "image": "https://example.com/product.png",
                "stock": 8,
                "active": True,
                "rating": 4.5,
                "rating_count": 10,
            },
        )
        assert created.status_code == 201
        product_id = created.json()["id"]

        listed = client.get("/api/products?search=produto")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1

        updated = client.patch(
            f"/api/products/{product_id}", json={"price": 119.9, "stock": 3}
        )
        assert updated.status_code == 200
        assert updated.json()["price"] == 119.9
        assert updated.json()["stock"] == 3

        summary = client.get("/api/dashboard")
        assert summary.status_code == 200
        assert summary.json()["low_stock_products"] == 1

        deleted = client.delete(f"/api/products/{product_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/products/{product_id}").status_code == 404


def test_sync_fake_store(tmp_path: Path, monkeypatch) -> None:
    test_database = tmp_path / "sync.db"
    monkeypatch.setattr(database, "DATABASE_PATH", test_database)

    async def fake_products() -> list[dict]:
        return [
            {
                "external_id": 42,
                "title": "Produto externo",
                "description": "Importado para o teste.",
                "price": 49.9,
                "category": "Externa",
                "image": "https://example.com/external.png",
                "stock": 12,
                "rating": 4.2,
                "rating_count": 30,
            }
        ]

    monkeypatch.setattr("app.main.fetch_products", fake_products)
    with TestClient(app) as client:
        response = client.post("/api/products/sync")
        assert response.status_code == 200
        assert response.json()["imported"] == 1
        product = client.get("/api/products").json()["items"][0]
        assert product["source"] == "fake_store"
        assert product["external_id"] == 42
