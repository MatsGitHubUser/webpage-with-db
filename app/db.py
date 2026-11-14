"""Comment storage in Postgres.

Connection settings come from the standard libpq environment variables
(PGHOST, PGUSER, PGPASSWORD, PGDATABASE, PGSSLMODE), so no connection string
has to be built or escaped here.
"""

from dataclasses import dataclass
from datetime import datetime

from psycopg.rows import class_row
from psycopg_pool import ConnectionPool

MAX_NAME = 50
MAX_BODY = 1000

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS comments (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author     text NOT NULL CHECK (char_length(author) BETWEEN 1 AND {MAX_NAME}),
    body       text NOT NULL CHECK (char_length(body) BETWEEN 1 AND {MAX_BODY}),
    created_at timestamptz NOT NULL DEFAULT now()
)
"""


@dataclass(frozen=True)
class Comment:
    id: int
    author: str
    body: str
    created_at: datetime


def open_pool(conninfo: str = "") -> ConnectionPool:
    """Open a connection pool and make sure the table exists."""
    pool = ConnectionPool(
        conninfo,
        min_size=1,
        max_size=5,
        timeout=10,
        # Drops connections that died while idle, e.g. after the Azure
        # database was stopped and started again.
        check=ConnectionPool.check_connection,
        open=True,
    )
    try:
        with pool.connection() as conn:
            conn.execute(SCHEMA)
    except Exception:
        pool.close()
        raise
    return pool


def clean(value: str, limit: int, what: str) -> str:
    """Trim user input and check it fits the table constraints."""
    value = (value or "").replace("\x00", "").strip()
    if not value:
        raise ValueError(f"{what} cannot be empty.")
    if len(value) > limit:
        raise ValueError(f"{what} can be at most {limit} characters.")
    return value


def add_comment(pool: ConnectionPool, author: str, body: str) -> Comment:
    author = clean(author, MAX_NAME, "Name")
    body = clean(body, MAX_BODY, "Comment")
    with pool.connection() as conn, conn.cursor(row_factory=class_row(Comment)) as cur:
        cur.execute(
            "INSERT INTO comments (author, body) VALUES (%s, %s)"
            " RETURNING id, author, body, created_at",
            (author, body),
        )
        return cur.fetchone()


def list_comments(pool: ConnectionPool, limit: int = 100) -> list[Comment]:
    """Newest first."""
    with pool.connection() as conn, conn.cursor(row_factory=class_row(Comment)) as cur:
        cur.execute(
            "SELECT id, author, body, created_at FROM comments"
            " ORDER BY created_at DESC, id DESC LIMIT %s",
            (limit,),
        )
        return cur.fetchall()
