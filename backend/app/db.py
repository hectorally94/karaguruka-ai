from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .settings import DATABASE_URL

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, kwargs={"row_factory": dict_row}, open=True)


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with pool.connection() as conn:
        cur = conn.execute(sql, params)
        return cur.fetchall() if cur.description else []


def one(sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, params)
    return rows[0] if rows else None
