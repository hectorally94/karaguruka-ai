from .db import pool
from .settings import ROOT


def main() -> None:
    with pool.connection() as conn:
        conn.execute((ROOT / "db" / "schema.sql").read_text())
    print("Database schema is ready.")


if __name__ == "__main__":
    main()
