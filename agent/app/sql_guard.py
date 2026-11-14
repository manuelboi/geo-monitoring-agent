"""Runs one SQL query written by the model, as safely as the database allows.

Protection comes from layers that do not depend on parsing the query:
- the read-only role (SELECT on the api views only, read-only transactions, statement timeout);
- a prepared statement, which PostgreSQL accepts only for a single statement, so the query
  cannot append e.g. `SET statement_timeout = 0` after a semicolon;
- a wrapping SELECT with a row limit.
"""

import psycopg

from app import db

MAX_ROWS = 100


class SqlError(ValueError):
    """The query failed. The message is the database error, returned to the model to fix its query."""


def run_readonly_sql(query: str) -> dict:
    query = query.strip().rstrip(";").strip()
    wrapped = f"SELECT * FROM (\n{query}\n) AS result LIMIT {MAX_ROWS + 1}"
    try:
        with db.readonly_connection() as conn:
            cur = conn.execute(wrapped, prepare=True)
            columns = [d.name for d in cur.description]
            rows = [{c: db.json_value(v) for c, v in zip(columns, row)} for row in cur.fetchall()]
    except psycopg.Error as e:
        raise SqlError(e.diag.message_primary or str(e)) from e
    return {"sql": query, "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS}
