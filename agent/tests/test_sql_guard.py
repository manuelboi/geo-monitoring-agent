import pytest

from app.sql_guard import MAX_ROWS, SqlError, run_readonly_sql


def test_select_on_the_views_works():
    result = run_readonly_sql("SELECT prompt_id FROM api.v_prompts ORDER BY prompt_id;")
    assert len(result["rows"]) == 8
    assert not result["truncated"]


def test_large_results_are_truncated():
    result = run_readonly_sql(
        "SELECT a.mention_id FROM api.v_mentions a CROSS JOIN api.v_mentions b"
    )
    assert len(result["rows"]) == MAX_ROWS
    assert result["truncated"]


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM api.v_prompts",
        "DROP VIEW api.v_prompts",
        "SELECT * FROM geo.mentions",
        "WITH d AS (DELETE FROM geo.prompts RETURNING *) SELECT * FROM d",
        "SELECT 1) AS a; SET statement_timeout = 0; SELECT * FROM (SELECT 1",
        "SELECT set_config('default_transaction_read_only', 'off', false)) AS a; DELETE FROM api.v_prompts; SELECT (1",
    ],
)
def test_writes_and_stacked_statements_are_rejected(query):
    with pytest.raises(SqlError):
        run_readonly_sql(query)


def test_long_queries_hit_the_timeout():
    with pytest.raises(SqlError, match="timeout"):
        run_readonly_sql("SELECT pg_sleep(10)")
