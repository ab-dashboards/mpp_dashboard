"""
BLS CPI release parser (HTML version)
extracts: headline YoY (CPI_U_ALL_ITEMS, percent)
          headline MoM (CPI_MoM, percent)
Works with pages like https://www.bls.gov/news.release/cpi.nr0.htm
"""

import re, requests
from pathlib import Path
from bs4 import BeautifulSoup

PERCENT_RE = re.compile(r"([0-9]+\.[0-9])\s*percent")

def parse(html_path):
    html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    text = soup.get_text(" ", strip=True)

    # YoY headline: sentence ends with "over the last 12 months...X.X percent"
    yoy_match = re.search(r"over the last 12 months[^.]*?([0-9]+\.[0-9])\s*percent", text, re.I)
    yoy = float(yoy_match.group(1)) if yoy_match else None

    # MoM headline: sentence with "seasonally adjusted CPI ... X.X percent"
    mom_match = re.search(r"seasonally adjusted[^.]*?([0-9]+\.[0-9])\s*percent", text, re.I)
    mom = float(mom_match.group(1)) if mom_match else None

    if yoy is None and mom is None:
        raise ValueError("CPI headline numbers not found – pattern may have changed")

    rows = []
    if yoy is not None:
        rows.append({"series": "CPI_USA_YoY", "value": yoy, "unit": "percent"})
    if mom is not None:
        rows.append({"series": "CPI_USA_MoM", "value": mom, "unit": "percent"})
    return rows
