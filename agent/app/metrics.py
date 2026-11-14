"""Computes every metric of kpi_definitions with parameterised SQL over the api views.

The agent chooses the parameters; the formulas, denominators and SQL live here and are tested
against the catalog values. Column names in the SQL come only from the whitelists below, and
every value is a bound parameter.
"""

import functools

import psycopg

from app import db

ANSWER_DIMENSIONS = ("ai_system", "prompt_id", "theme", "buyer_type", "wave_date")
CITATION_DIMENSIONS = ("source_type", "content_ownership", "content_format", "source_domain")
MENTION_METRICS = (
    "mentions",
    "visibility",
    "share_of_voice",
    "sentiment",
    "average_position",
    "top3_rate",
    "prominence",
    "scorecard",
)
CITATION_METRICS = ("citations", "source_mix", "earned_gap_domains")
METRICS = MENTION_METRICS + CITATION_METRICS
DEFAULT_RANKING_LIMIT = 10
NO_SOURCE_LABEL = "(no source: model internal knowledge)"

# Rates and shares are returned as percentages with one decimal, as in the catalog, so the model only copies them.
# numerator, denominator, denominator unit and value (None: the percentage), over the brand_stats (s),
# group_totals (t), answer_counts (g) CTEs
MENTION_FORMULAS = {
    "mentions": ("coalesce(s.mentions, 0)", "NULL", None, "coalesce(s.mentions, 0)"),
    "visibility": ("coalesce(s.answers_with_brand, 0)", "g.answers", "answers", None),
    "share_of_voice": ("coalesce(s.mentions, 0)", "coalesce(t.all_mentions, 0)", "mentions of all brands", None),
    "sentiment": ("coalesce(s.positive, 0)", "coalesce(s.mentions, 0)", "mentions of the brand", None),
    "average_position": ("NULL", "coalesce(s.mentions, 0)", "mentions of the brand", "round(s.average_position, 2)"),
    "top3_rate": ("coalesce(s.top3, 0)", "coalesce(s.mentions, 0)", "mentions of the brand", None),
    "prominence": ("round(coalesce(s.prominence_weight, 0), 2)", "g.answers", "answers", None),
}

# Every mention metric in one row; rankings use prominence, which weighs both reach and position
SCORECARD_COLUMNS = """g.answers AS answers_in_scope,
           coalesce(s.answers_with_brand, 0) AS answers_with_brand,
           coalesce(s.mentions, 0) AS mentions,
           coalesce(t.all_mentions, 0) AS mentions_of_all_brands,
           round(100.0 * coalesce(s.answers_with_brand, 0) / nullif(g.answers, 0), 1) AS visibility,
           round(100.0 * coalesce(s.mentions, 0) / nullif(t.all_mentions, 0), 1) AS share_of_voice,
           round(100.0 * s.positive / nullif(s.mentions, 0), 1) AS sentiment,
           round(s.average_position, 2) AS average_position,
           round(100.0 * s.top3 / nullif(s.mentions, 0), 1) AS top3_rate,
           round(100.0 * coalesce(s.prominence_weight, 0) / nullif(g.answers, 0), 1) AS prominence"""
SCORECARD_OUTPUT = (
    "answers_in_scope, answers_with_brand, mentions, mentions_of_all_brands, "
    "visibility, share_of_voice, sentiment, average_position, top3_rate, prominence"
)


class MetricError(ValueError):
    """Invalid request. The message is written for the model, so it can correct its call."""


@functools.cache
def dimension_values() -> dict[str, list[str]]:
    """Values present in the data for every dimension except source_domain, which is free text."""
    values = {}
    with db.readonly_connection() as conn:
        for key in ANSWER_DIMENSIONS:
            rows = conn.execute(f"SELECT DISTINCT {key}::text FROM api.v_answers ORDER BY 1").fetchall()
            values[key] = [r[0] for r in rows]
        for key in CITATION_DIMENSIONS[:-1]:
            rows = conn.execute(f"SELECT DISTINCT {key} FROM api.v_citations ORDER BY 1").fetchall()
            values[key] = [r[0] for r in rows]
    return values


def _canonical_filters(filters: dict[str, list[str]]) -> dict[str, list[str]]:
    known = dimension_values()
    canonical = {}
    for key, values in filters.items():
        if key not in known:
            canonical[key] = values
            continue
        by_folded = {v.casefold(): v for v in known[key]}
        unknown = [v for v in values if v.casefold() not in by_folded]
        if unknown:
            raise MetricError(f"Unknown {key} {unknown}. Values in the data: {', '.join(known[key])}.")
        canonical[key] = [by_folded[v.casefold()] for v in values]
    return canonical


@functools.cache
def brand_names() -> list[str]:
    with db.readonly_connection() as conn:
        return [r[0] for r in conn.execute("SELECT DISTINCT brand_name FROM api.v_mentions ORDER BY 1").fetchall()]


def _canonical_brands(brands: list[str]) -> list[str]:
    by_folded = {b.casefold(): b for b in brand_names()}
    unknown = [b for b in brands if b.casefold() not in by_folded]
    if unknown:
        raise MetricError(
            f"Unknown brand {unknown}: resolve it with find_brands. "
            "If find_brands finds nothing, no answer in the data names it."
        )
    return [by_folded[b.casefold()] for b in brands]


def compute_metric(
    metric: str,
    brands: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
    group_by: list[str] | None = None,
    limit: int | None = None,
) -> dict:
    brands = list(brands or [])
    filters = {k: [v] if isinstance(v, str) else list(v) for k, v in (filters or {}).items()}
    group_by = list(group_by or [])
    _validate(metric, brands, filters, group_by, limit)
    filters = _canonical_filters(filters)
    brands = _canonical_brands(brands)

    if metric in MENTION_METRICS:
        query, params = _mention_query(metric, brands, filters, group_by, limit)
    elif metric == "earned_gap_domains":
        query, params = _earned_gap_query(brands, filters, limit)
    else:
        query, params = _citation_query(metric, brands, filters, group_by, limit)
    return _run(query, params)


def _validate(metric, brands, filters, group_by, limit) -> None:
    if metric not in METRICS:
        raise MetricError(f"Unknown metric {metric!r}. Valid metrics: {', '.join(METRICS)}.")
    dimensions = ANSWER_DIMENSIONS + CITATION_DIMENSIONS
    for key, values in filters.items():
        if key not in dimensions:
            raise MetricError(f"Cannot filter by {key!r}. Valid filters: {', '.join(dimensions)}.")
        if not values:
            raise MetricError(f"Filter {key!r} has no values.")
    for key in group_by:
        if key not in dimensions + ("brand_name",):
            raise MetricError(f"Cannot group by {key!r}. Valid groupings: brand_name, {', '.join(dimensions)}.")
    if metric in MENTION_METRICS:
        if any(key in CITATION_DIMENSIONS for key in group_by):
            raise MetricError(f"{metric} can be filtered by {', '.join(CITATION_DIMENSIONS)} but not grouped by them.")
        if metric != "mentions" and not brands and "brand_name" not in group_by:
            raise MetricError(f"{metric} needs a brand: pass brands, or group_by brand_name for a ranking.")
    if metric == "earned_gap_domains" and group_by:
        raise MetricError("earned_gap_domains does not support group_by; use filters instead.")
    if limit is not None and not 1 <= limit <= 100:
        raise MetricError("limit must be between 1 and 100.")


def _conditions(filters: dict, dimensions: tuple, params: dict, alias: str = "") -> list[str]:
    conditions = []
    for key in dimensions:
        if key in filters:
            params[f"filter_{key}"] = filters[key]
            # Compared as text so dates and strings take the same path
            conditions.append(f"{alias}{key}::text = ANY(%(filter_{key})s)")
    return conditions


def _join(left: str, right: str, keys: list[str]) -> str:
    return " AND ".join(f"{left}.{k} = {right}.{k}" for k in keys) or "TRUE"


def _mention_query(metric, brands, filters, group_by, limit) -> tuple[str, dict]:
    params: dict = {}
    keys = [k for k in group_by if k in ANSWER_DIMENSIONS]
    select_keys = "".join(f"{k}, " for k in keys)
    group_keys = f"GROUP BY {', '.join(keys)}" if keys else ""

    answer_conditions = _conditions(filters, ANSWER_DIMENSIONS, params)
    mention_conditions = list(answer_conditions)
    citation_conditions = _conditions(filters, CITATION_DIMENSIONS, params, alias="c.")
    if citation_conditions:
        # A mention counts when at least one of its citations matches the source filters
        mention_conditions.append(
            "EXISTS (SELECT 1 FROM api.v_citations c WHERE c.mention_id = vm.mention_id AND "
            + " AND ".join(citation_conditions)
            + ")"
        )

    if brands:
        params["brands"] = brands
        brand_list = "SELECT unnest(%(brands)s::text[]) AS brand_name"
    elif "brand_name" in group_by:
        # Rankings always include the client, so "who beats us" shows where it stands
        brand_list = "SELECT DISTINCT brand_name FROM mentions_in_scope UNION SELECT brand_name FROM clients"
    else:
        brand_list = "SELECT NULL::text AS brand_name"

    if metric == "scorecard":
        result_columns, output = SCORECARD_COLUMNS, SCORECARD_OUTPUT
        order = "prominence DESC NULLS LAST, brand_name"
    else:
        numerator, denominator, unit, value = MENTION_FORMULAS[metric]
        if metric == "mentions" and not brands and "brand_name" not in group_by:
            numerator = value = "coalesce(t.all_mentions, 0)"
        if value is None:
            value = f"round(100.0 * ({numerator}) / nullif({denominator}, 0), 1)"
        params["unit"] = unit
        result_columns = (
            f"{numerator} AS numerator, {denominator} AS denominator, "
            f"%(unit)s::text AS denominator_unit, {value} AS value"
        )
        output = "numerator, denominator, denominator_unit, value"
        order = f"value {'ASC' if metric == 'average_position' else 'DESC'} NULLS LAST, brand_name"

    ranking = brands == [] and "brand_name" in group_by
    if ranking and limit is None:
        limit = DEFAULT_RANKING_LIMIT

    query = f"""
WITH clients AS (
    SELECT DISTINCT brand_name FROM api.v_mentions WHERE is_target
), answers_in_scope AS (
    SELECT {select_keys}answer_id FROM api.v_answers
    WHERE {" AND ".join(answer_conditions) or "TRUE"}
), mentions_in_scope AS (
    SELECT {select_keys}mention_id, answer_id, brand_name, position, sentiment FROM api.v_mentions vm
    WHERE {" AND ".join(mention_conditions) or "TRUE"}
), answer_counts AS (
    SELECT {select_keys}count(*) AS answers FROM answers_in_scope {group_keys}
), group_totals AS (
    SELECT {select_keys}count(*) AS all_mentions FROM mentions_in_scope {group_keys}
), brand_list AS (
    {brand_list}
), brand_stats AS (
    SELECT {select_keys}brand_name,
           count(*) AS mentions,
           count(DISTINCT answer_id) AS answers_with_brand,
           count(*) FILTER (WHERE sentiment = 'positive') AS positive,
           avg(position) AS average_position,
           count(*) FILTER (WHERE position <= 3) AS top3,
           sum(greatest(0, 11 - position) / 10.0) AS prominence_weight
    FROM mentions_in_scope GROUP BY {select_keys}brand_name
), results AS (
    SELECT {"".join(f"g.{k}, " for k in keys)}b.brand_name,
           {result_columns}
    FROM answer_counts g
    CROSS JOIN brand_list b
    LEFT JOIN group_totals t ON {_join("g", "t", keys)}
    LEFT JOIN brand_stats s ON {_join("g", "s", keys)} AND s.brand_name = b.brand_name
), ranked AS (
    SELECT *, row_number() OVER ({f"PARTITION BY {", ".join(keys)} " if keys else ""}ORDER BY {order}) AS rank
    FROM results
)
SELECT {"*" if ranking else select_keys + "brand_name, " + output} FROM ranked
{"WHERE rank <= %(limit)s OR brand_name IN (SELECT brand_name FROM clients)" if limit else ""}
ORDER BY {select_keys}rank"""
    if limit:
        params["limit"] = limit
    return query, params


def _citation_query(metric, brands, filters, group_by, limit) -> tuple[str, dict]:
    params: dict = {}
    keys = list(group_by)
    if metric == "source_mix" and not any(k in CITATION_DIMENSIONS for k in keys):
        keys.append("content_ownership")
    # Shares are computed within each combination of the non-source groupings (e.g. per assistant)
    partition = [k for k in keys if k not in CITATION_DIMENSIONS]
    over = f"PARTITION BY {', '.join(partition)}" if partition else ""

    conditions = _conditions(filters, ANSWER_DIMENSIONS + CITATION_DIMENSIONS, params)
    if brands:
        params["brands"] = brands
        conditions.append("brand_name = ANY(%(brands)s)")
    columns = ", ".join(
        f"coalesce(source_domain, '{NO_SOURCE_LABEL}') AS source_domain" if k == "source_domain" else k for k in keys
    )

    query = f"""
WITH citations_in_scope AS (
    SELECT {columns + ", " if columns else ""}citation_id FROM api.v_citations
    WHERE {" AND ".join(conditions) or "TRUE"}
), counted AS (
    SELECT {"".join(f"{k}, " for k in keys)}count(*) AS numerator,
           sum(count(*)) OVER ({over})::bigint AS denominator,
           'citation rows'::text AS denominator_unit
    FROM citations_in_scope {f"GROUP BY {', '.join(keys)}" if keys else ""}
), ranked AS (
    SELECT *, round(100.0 * numerator / denominator, 1) AS value,
           row_number() OVER ({over} ORDER BY numerator DESC{"".join(f", {k}" for k in keys)}) AS rank
    FROM counted
)
SELECT * FROM ranked
{"WHERE rank <= %(limit)s" if limit else ""}
ORDER BY {"".join(f"{k}, " for k in partition)}rank"""
    if limit:
        params["limit"] = limit
    return query, params


def _earned_gap_query(brands, filters, limit) -> tuple[str, dict]:
    params: dict = {}
    conditions = _conditions(filters, ANSWER_DIMENSIONS, params)
    competitor_condition = ""
    if brands:
        params["brands"] = brands
        competitor_condition = "AND brand_name = ANY(%(brands)s)"
    if limit:
        params["limit"] = limit

    query = f"""
WITH cited AS (
    SELECT source_domain, brand_name, is_target, content_ownership, source_also_cites_target FROM api.v_citations
    WHERE source_domain IS NOT NULL AND {" AND ".join(conditions) or "TRUE"}
), touches_target AS (
    SELECT source_domain FROM cited WHERE is_target OR source_also_cites_target
)
SELECT source_domain,
       count(*) AS competitor_citations,
       string_agg(DISTINCT brand_name, ', ' ORDER BY brand_name) AS competitors,
       count(*) OVER () AS total_gap_domains
FROM cited
WHERE content_ownership = 'Earned' AND NOT is_target {competitor_condition}
  AND source_domain NOT IN (SELECT source_domain FROM touches_target)
GROUP BY source_domain
ORDER BY competitor_citations DESC, source_domain
{"LIMIT %(limit)s" if limit else ""}"""
    return query, params


def _run(query: str, params: dict) -> dict:
    with db.readonly_connection() as conn:
        cur = conn.execute(query, params)
        columns = [d.name for d in cur.description]
        rows = [{c: db.json_value(v) for c, v in zip(columns, row)} for row in cur.fetchall()]
        rendered = psycopg.ClientCursor(conn).mogrify(query, params)
    return {"sql": rendered.strip(), "rows": rows}
