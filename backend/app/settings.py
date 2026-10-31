import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
AGENT_PASSWORD = os.getenv("AGENT_PASSWORD", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "fra+eng")
HANDLE_MINUTES = float(os.getenv("HANDLE_MINUTES", "6"))
SECURE_COOKIES = os.getenv("SECURE_COOKIES", "0") == "1"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Fictional values for the demo. Replace them with the client's real data.
BANK_NAME = "Banque Démo"
CARD_HOTLINE = "01 99 00 01 00"
CREDIT_PRODUCTS = {
    "conso": {"label": "Crédit consommation", "rate": 6.9, "min_amount": 1000, "max_amount": 50000, "min_months": 6, "max_months": 84},
    "auto": {"label": "Crédit auto", "rate": 5.2, "min_amount": 3000, "max_amount": 75000, "min_months": 12, "max_months": 84},
    "immo": {"label": "Crédit immobilier", "rate": 3.6, "min_amount": 30000, "max_amount": 500000, "min_months": 60, "max_months": 300},
}
