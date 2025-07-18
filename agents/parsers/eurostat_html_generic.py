"""
Generic Eurostat press-release parser.
Looks for the first number followed by % or points inside the
<span class="eurostat-indicator-value"> tag (common pattern).
"""

import re, requests
from bs4 import BeautifulSoup
from pathlib import Path

def parse(html_path):
    html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    val_tag = soup.select_one(".eurostat-indicator-value")
    if not val_tag:
        raise ValueError("Indicator value tag not found – layout changed?")
    txt = val_tag.get_text(" ", strip=True)

    number_m = re.search(r"([-+]?[0-9]+(?:\.[0-9]+)?)", txt)
    if not number_m:
        raise ValueError("Numeric value not found in indicator tag")
    value = float(number_m.group(1))
    unit = "percent" if "%" in txt else "points"

    rows = [{"series": "EUROSTAT_HEADLINE", "value": value, "unit": unit}]
    return rows
