import json
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

# The default profile is a fictional bank. BANK_PROFILE points to a JSON file that replaces these values for a client.
# A relative path is read from the backend folder, wherever the server was started.
PROFILE_PATH = (ROOT / "backend" / os.environ["BANK_PROFILE"]).resolve() if os.getenv("BANK_PROFILE") else None
_profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8")) if PROFILE_PATH else {}

BANK_NAME = _profile.get("bank_name", "Banque Démo")
BANK_NOTICE = _profile.get("notice", "Banque fictive : toutes les données sont des exemples. Ne saisissez aucune vraie donnée bancaire.")
CURRENCY = _profile.get("currency", "€")
URGENT_CONTACT = _profile.get("urgent_contact", "le service d'opposition est joignable 24h/24 au 01 99 00 01 00")
RATE_LABEL = _profile.get("rate_label", "indicatif")
CREDIT_PRODUCTS = _profile.get("credit_products") or {
    "conso": {"label": "Crédit consommation", "keywords": ["conso", "personnel"], "rate": 6.9, "min_amount": 1000, "max_amount": 50000, "min_months": 6, "max_months": 84},
    "auto": {"label": "Crédit auto", "keywords": ["auto", "voiture"], "rate": 5.2, "min_amount": 3000, "max_amount": 75000, "min_months": 12, "max_months": 84},
    "immo": {"label": "Crédit immobilier", "keywords": ["immo"], "rate": 3.6, "min_amount": 30000, "max_amount": 500000, "min_months": 60, "max_months": 300},
}
