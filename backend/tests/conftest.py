"""Runs the tests on their own database, so they never touch the demo data."""
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

main_url = urlsplit(os.environ["DATABASE_URL"])
os.environ["DATABASE_URL"] = urlunsplit(main_url._replace(path="/karaguruka_test"))
# The tests check the behavior without paid AI services.
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["VOYAGE_API_KEY"] = ""

with psycopg.connect(urlunsplit(main_url), autocommit=True) as conn:
    conn.execute("DROP DATABASE IF EXISTS karaguruka_test WITH (FORCE)")
    conn.execute("CREATE DATABASE karaguruka_test")

from app import init_db, seed  # noqa: E402

init_db.main()
seed.main()
