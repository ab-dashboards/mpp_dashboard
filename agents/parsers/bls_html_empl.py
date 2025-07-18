"""
Employment Situation (BLS) HTML parser
Extracts:
    UNRATE     – unemployment rate, percent
    NFP_CHANGE – change in nonfarm payrolls, thousands
"""

import re
from bs4 import BeautifulSoup
from pathlib import Path

def parse(html_path):
    html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(" ", strip=True)

    # Unemployment rate sentence
    u_match = re.search(r"unemployment rate (?:was|is) ([0-9]+\.[0-9]) percent", text, re.I)
    unrate = float(u_match.group(1)) if u_match else None

    # Non-farm payroll change e.g. "increased by 175,000"
    nfp_match = re.search(r"nonfarm payroll employment.*?([0-9,]+)\s+in", text, re.I)
    nfp = int(nfp_match.group(1).replace(",", "")) if nfp_match else None

    if unrate is None and nfp is None:
        raise ValueError("Employment Situation headline not found")

    rows = []
    if unrate is not None:
        rows.append({"series": "UNRATE", "value": unrate, "unit": "percent"})
    if nfp is not None:
        rows.append({"series": "NFP_CHANGE", "value": nfp, "unit": "thousands"})
    return rows
