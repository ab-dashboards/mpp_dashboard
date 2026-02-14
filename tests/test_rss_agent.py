from agents.rss_agent import sort_key


def test_sort_key_iso_date():
    assert sort_key({"published": "2025-06-19"}) == "20250619"


def test_sort_key_dd_mm_yyyy():
    assert sort_key({"published": "19-06-2025"}) == "20250619"
