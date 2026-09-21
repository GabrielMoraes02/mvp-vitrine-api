from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", BASE_DIR / "data" / "vitrine.db"))
FAKE_STORE_URL = os.getenv("FAKE_STORE_URL", "https://fakestoreapi.com")
FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:4173,http://127.0.0.1:4173",
    ).split(",")
    if origin.strip()
]
