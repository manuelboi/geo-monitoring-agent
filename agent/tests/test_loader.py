from app.data.loader import load


def test_loading_twice_gives_the_same_rows():
    first = load()
    second = load()
    assert first == second
    assert (first["answers"], first["mentions"], first["mention_citations"]) == (32, 64, 64)
