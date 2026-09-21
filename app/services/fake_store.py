import httpx

from ..config import FAKE_STORE_URL


class FakeStoreUnavailable(RuntimeError):
    pass


async def fetch_products() -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(f"{FAKE_STORE_URL}/products")
            response.raise_for_status()
            products = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise FakeStoreUnavailable("Não foi possível consultar a Fake Store API.") from error

    normalized = []
    for item in products:
        rating = item.get("rating") or {}
        normalized.append(
            {
                "external_id": item["id"],
                "title": item["title"],
                "description": item.get("description") or "Produto importado da Fake Store.",
                "price": float(item["price"]),
                "category": item.get("category") or "Outros",
                "image": item["image"],
                "stock": max(3, int(rating.get("count", 10)) % 31),
                "rating": float(rating.get("rate", 0)),
                "rating_count": int(rating.get("count", 0)),
            }
        )
    return normalized
