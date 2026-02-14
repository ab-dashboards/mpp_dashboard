from agents.scrape_agent import best_stamp, derive_indicator


def test_best_stamp_prefers_published_iso():
    row = {"published": "2025-06-20", "release_id": "foo_010120"}
    assert best_stamp(row) == "20250620"


def test_derive_indicator_from_source_dataset():
    row = {"source": "BLS", "dataset": "CPI"}
    assert derive_indicator(row) == "BLS_CPI"
