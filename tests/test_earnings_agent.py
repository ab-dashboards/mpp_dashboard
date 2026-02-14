import datetime as dt

from agents.earnings_agent import extract_tickers, newest_by_tag


def test_extract_tickers_from_slug():
    url = "https://example.com/post-june-20-2025-aapl-msft-goog"
    assert extract_tickers(url) == ["AAPL", "MSFT", "GOOG"]


def test_newest_by_tag_prefers_slug_date():
    rows = [
        {"dataset": "EARN_PRE", "url": "https://x-june-20-2025-aapl", "published": "2025-06-01"},
        {"dataset": "EARN_PRE", "url": "https://x-june-21-2025-aapl", "published": "2025-06-01"},
        {"dataset": "EARN_AH", "url": "https://x-june-19-2025-aapl", "published": "2025-06-30"},
    ]
    latest = newest_by_tag(rows)
    assert latest["EARN_PRE"]["_ts"] == dt.date(2025, 6, 21)
    assert latest["EARN_AH"]["_ts"] == dt.date(2025, 6, 19)
