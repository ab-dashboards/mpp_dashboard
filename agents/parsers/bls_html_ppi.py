"""
BLS PPI release parser (HTML)
Grabs Final-Demand YoY % and MoM % from news.release/ppi.nr0.htm
"""

import re
from bs4 import BeautifulSoup
from pathlib import Path

def parse(html_path):
    html = Path(html_path).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    text = soup.get_text(" ", strip=True)

    # Example: "The Producer Price Index for final demand increased 2.2 percent
    # for the 12 months ended April ..."
    yoy = None; mom = None
    yoy_m = re.search(r"final demand.*?([0-9]+\.[0-9])\s*percent.*?12 months", text, re.I)
    if yoy_m: yoy = float(yoy_m.group(1))

    # Example: "... increased 0.5 percent in April ..."
    mom_m = re.search(r"final demand.*?([0-9]+\.[0-9])\s*percent[^.]*?April", text, re.I)
    if mom_m: mom = float(mom_m.group(1))

    if yoy is None and mom is None:
        raise ValueError("PPI headline numbers not found")

    rows = []
    if yoy is not None:
        rows.append({"series": "PPI_FD_YoY", "value": yoy, "unit": "percent"})
    if mom is not None:
        rows.append({"series": "PPI_FD_MoM", "value": mom, "unit": "percent"})
    return rows
