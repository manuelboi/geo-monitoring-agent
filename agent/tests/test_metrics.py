import pytest

from app.metrics import MetricError, compute_metric

TARGET = "Sample Client"


def single_row(metric: str, **kwargs) -> dict:
    rows = compute_metric(metric, **kwargs)["rows"]
    assert len(rows) == 1
    return rows[0]


def test_synthetic_target_metrics():
    row = single_row("visibility", brands=[TARGET])
    assert (row["numerator"], row["denominator"], row["value"]) == (16, 32, 50.0)

    row = single_row("share_of_voice", brands=[TARGET])
    assert (row["numerator"], row["denominator"], row["value"]) == (16, 64, 25.0)

    row = single_row("average_position", brands=[TARGET])
    assert (row["denominator"], row["value"]) == (16, 1.5)

    row = single_row("top3_rate", brands=[TARGET])
    assert (row["numerator"], row["denominator"], row["value"]) == (16, 16, 100.0)

    row = single_row("prominence", brands=[TARGET])
    assert (row["numerator"], row["denominator"], row["value"]) == (15.2, 32, 47.5)


def test_scorecard_uses_the_same_synthetic_values():
    row = single_row("scorecard", brands=[TARGET])
    assert (row["mentions"], row["answers_in_scope"]) == (16, 32)
    assert (row["visibility"], row["share_of_voice"], row["sentiment"]) == (50.0, 25.0, 31.3)
    assert (row["average_position"], row["top3_rate"], row["prominence"]) == (1.5, 100.0, 47.5)


def test_rankings_are_ordered_by_prominence_and_include_the_target():
    rows = compute_metric("scorecard", group_by=["brand_name"], limit=3)["rows"]
    assert [row["rank"] for row in rows] == sorted(row["rank"] for row in rows)
    assert [row["prominence"] for row in rows] == sorted(
        (row["prominence"] for row in rows), reverse=True
    )
    assert TARGET in {row["brand_name"] for row in rows}


def test_theme_scope_uses_its_answers_as_denominator():
    row = single_row("prominence", brands=["Brand Alpha"], filters={"theme": ["Theme 1"]})
    assert row["denominator"] == 16


def test_grouping_keeps_every_assistant_when_a_brand_is_absent():
    rows = compute_metric(
        "visibility", brands=[TARGET], filters={"prompt_id": ["P01"]}, group_by=["ai_system"]
    )["rows"]
    assert sorted(row["ai_system"] for row in rows) == ["ChatGPT", "Claude", "Gemini", "Perplexity"]
    assert all(row["denominator"] == 1 for row in rows)
    assert "rank" not in rows[0]


def test_split_by_assistant_adds_up_to_the_total():
    rows = compute_metric("visibility", brands=[TARGET], group_by=["ai_system"])["rows"]
    assert sum(row["numerator"] for row in rows) == 16


def test_brand_names_are_matched_case_insensitively():
    assert single_row("mentions", brands=["sample client"])["brand_name"] == TARGET


def test_ranking_is_ordered_and_limited():
    rows = compute_metric("visibility", group_by=["brand_name"], limit=3)["rows"]
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert rows[0]["value"] >= rows[1]["value"] >= rows[2]["value"]


def test_source_mix_covers_every_citation_row():
    rows = compute_metric("source_mix")["rows"]
    assert sum(row["numerator"] for row in rows) == 64
    assert abs(sum(row["value"] for row in rows) - 100) <= 0.05 * len(rows)


def test_domains_include_citations_without_a_source():
    rows = compute_metric("citations", brands=[TARGET], group_by=["source_domain"])["rows"]
    assert sum(row["numerator"] for row in rows) == rows[0]["denominator"]
    assert abs(sum(row["value"] for row in rows) - 100) <= 0.05 * len(rows)


def test_source_filter_keeps_mentions_with_a_matching_citation():
    owned = single_row("mentions", brands=[TARGET], filters={"content_ownership": ["Owned"]})
    assert 0 < owned["numerator"] <= 16


@pytest.mark.parametrize(
    "kwargs",
    [
        {"metric": "revenue"},
        {"metric": "visibility"},
        {"metric": "visibility", "brands": [TARGET], "filters": {"country": ["IT"]}},
        {"metric": "visibility", "brands": [TARGET], "group_by": ["source_type"]},
        {"metric": "visibility", "brands": [TARGET], "filters": {"ai_system": ["Copilot"]}},
        {"metric": "visibility", "brands": [TARGET], "filters": {"theme": ["unknown"]}},
        {"metric": "visibility", "brands": ["Unknown Example"]},
    ],
)
def test_invalid_requests_are_rejected_with_a_message(kwargs):
    with pytest.raises(MetricError):
        compute_metric(**kwargs)


def test_filter_values_are_matched_case_insensitively():
    row = single_row(
        "visibility",
        brands=[TARGET],
        filters={"ai_system": ["gemini"], "theme": ["theme 1"]},
    )
    assert row["denominator"] == 4
