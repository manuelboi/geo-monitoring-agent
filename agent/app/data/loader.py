"""Loads the CSV data pack into PostgreSQL. Safe to run on every start: it rebuilds everything
in one transaction, so a second run never duplicates rows and a failed run leaves the old data.

Usage: python -m app.data.loader
"""

import csv
from datetime import date
from pathlib import Path

from psycopg import Cursor, sql

from app import config, db

SCHEMA_SQL = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
READONLY_STATEMENT_TIMEOUT = "5s"


def read_csv(name: str) -> list[dict]:
    # newline="" lets the csv module handle line breaks inside quoted answer texts
    with open(config.DATA_DIR / "csv" / name, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def boolean(value: str) -> bool:
    return {"TRUE": True, "FALSE": False}[value]


def optional(value: str) -> str | None:
    return value or None


def optional_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def insert(cur: Cursor, table: str, columns: list[str], rows: list[tuple]) -> None:
    query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
        sql.Identifier("geo", table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join(sql.Placeholder() * len(columns)),
    )
    cur.executemany(query, rows)


def create_readonly_role(cur: Cursor) -> None:
    role = sql.Identifier(config.DB_READONLY_USER)
    if not cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (config.DB_READONLY_USER,)).fetchone():
        cur.execute(sql.SQL("CREATE ROLE {} LOGIN").format(role))
    # Role statements do not accept bind parameters, hence the client-side quoted literals
    cur.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(role, sql.Literal(config.DB_READONLY_PASSWORD)))
    cur.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(role))
    cur.execute(
        sql.SQL("ALTER ROLE {} SET statement_timeout = {}").format(role, sql.Literal(READONLY_STATEMENT_TIMEOUT))
    )
    cur.execute(sql.SQL("GRANT USAGE ON SCHEMA api TO {}").format(role))
    cur.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA api TO {}").format(role))


def load() -> dict[str, int]:
    prompts = read_csv("04_prompts.csv")
    answers = read_csv("05_answers.csv")
    mentions = read_csv("06_mentions.csv")
    citations = read_csv("07_citations.csv")
    kpis = read_csv("02_kpi_definitions.csv")
    context = read_csv("01_context.csv")

    # profile.py verified these attributes are constant per brand and per citation_id
    brands = {
        m["brand_name"]: (m["brand_name"], optional(m["brand_website"]), boolean(m["is_target"])) for m in mentions
    }
    sources = {
        c["citation_id"]: (
            c["citation_id"],
            optional(c["source_domain"]),
            c["source_type"],
            c["content_format"],
            c["content_ownership"],
            optional(c["content_url"]),
            optional(c["author"]),
            optional_date(c["publication_date"]),
            boolean(c["source_also_cites_target"]),
        )
        for c in citations
    }

    expected = {
        "prompts": len(prompts),
        "answers": len(answers),
        "brands": len(brands),
        "mentions": len(mentions),
        "citations": len(sources),
        "mention_citations": len(citations),
        "kpi_definitions": len(kpis),
        "context": len(context),
    }

    # The connection block commits on success and rolls back everything on any error
    with db.owner_connection() as conn, conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS api CASCADE")
        cur.execute("DROP SCHEMA IF EXISTS geo CASCADE")
        cur.execute(SCHEMA_SQL)

        insert(
            cur,
            "prompts",
            ["prompt_id", "query_it", "label_en", "theme", "buyer_type"],
            [(p["prompt_id"], p["query_it"], p["label_en"], p["theme"], p["buyer_type"]) for p in prompts],
        )
        insert(
            cur,
            "answers",
            ["answer_id", "wave_date", "ai_system", "prompt_id", "answer_text_it"],
            [
                (
                    a["answer_id"],
                    date.fromisoformat(a["wave_date"]),
                    a["ai_system"],
                    a["prompt_id"],
                    a["answer_text_it"],
                )
                for a in answers
            ],
        )
        insert(cur, "brands", ["brand_name", "brand_website", "is_target"], list(brands.values()))
        insert(
            cur,
            "mentions",
            ["mention_id", "answer_id", "brand_name", "brand_name_as_written", "position", "sentiment"],
            [
                (
                    m["mention_id"],
                    m["answer_id"],
                    m["brand_name"],
                    m["brand_name_as_written"],
                    int(m["position"]),
                    m["sentiment"],
                )
                for m in mentions
            ],
        )
        insert(
            cur,
            "citations",
            [
                "citation_id",
                "source_domain",
                "source_type",
                "content_format",
                "content_ownership",
                "content_url",
                "author",
                "publication_date",
                "source_also_cites_target",
            ],
            list(sources.values()),
        )
        insert(
            cur,
            "mention_citations",
            ["mention_id", "citation_id"],
            [(c["mention_id"], c["citation_id"]) for c in citations],
        )
        insert(
            cur,
            "kpi_definitions",
            ["kpi", "definition", "formula", "example"],
            [(k["kpi"], k["definition"], k["formula"], k["example"]) for k in kpis],
        )
        insert(cur, "context", ["item", "value"], [(c["item"], c["value"]) for c in context])

        create_readonly_role(cur)

        loaded = {
            table: cur.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("geo", table))).fetchone()[0]
            for table in expected
        }
        if loaded != expected:
            raise RuntimeError(f"Row counts differ from the files: loaded={loaded} expected={expected}")
    return loaded


if __name__ == "__main__":
    counts = load()
    print("Data loaded: " + ", ".join(f"{table}={n}" for table, n in counts.items()))
