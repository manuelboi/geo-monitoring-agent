from app import tools


def test_find_brands_matches_how_assistants_wrote_the_name():
    result = tools.find_brands("brand alpha")
    assert [m["brand_name"] for m in result["matches"]] == ["Brand Alpha"]


def test_find_brands_suggests_names_for_typos():
    result = tools.find_brands("Brand Alpa")
    assert result["matches"] == []
    assert "Brand Alpha" in result["similar_names"]


def test_find_brands_reports_brands_that_are_not_in_the_data():
    assert tools.find_brands("Unknown Example") == {"matches": [], "similar_names": []}


def test_execute_returns_errors_as_data():
    assert "error" in tools.execute("compute_metric", {"metric": "visibility", "country": "IT"})
    assert "error" in tools.execute("run_sql", {"query": "DELETE FROM api.v_prompts"})
    assert "error" in tools.execute("send_email", {})


def test_declarations_offer_only_values_present_in_the_data():
    compute = next(d for d in tools.declarations() if d["name"] == "compute_metric")
    filters = compute["parameters"]["properties"]["filters"]["properties"]
    assert filters["ai_system"]["items"]["enum"] == ["ChatGPT", "Claude", "Gemini", "Perplexity"]
    assert "scorecard" in compute["parameters"]["properties"]["metric"]["enum"]
