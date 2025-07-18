#!/usr/bin/env python3
"""
Markets Policy Partners – Pipeline · Scrape-Agent  (v4)
────────────────────────────────────────────────────────
* Works directly off data/rss_queue.csv   or   an Excel passed via --excel.
* Keeps ONLY the newest row per indicator (where indicator is derived from
  source+dataset or, failing that, the release_id prefix).
* If an HTML copy already exists in data/raw/ it is converted to plain text;
  if only a PDF exists it is skipped; otherwise the URL is fetched live.
* Writes plain-text dumps to   releases/<indicator>/<indicator>_YYYYMMDD.txt
"""
import argparse, csv, re, sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

# ── CONSTANT PATHS ───────────────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
RAW_DIR   = ROOT / "data" / "raw"
QUEUE_CSV = ROOT / "data" / "rss_queue.csv"

# ── CLI ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser(description="Scrape plain text from latest releases")
ap.add_argument("--excel", help="Excel file with indicator / url columns (optional)")
ap.add_argument("--output_dir", default=str(ROOT / "releases"))
args = ap.parse_args()

OUT_ROOT = Path(args.output_dir).expanduser()
OUT_ROOT.mkdir(parents=True, exist_ok=True)

# ── REGEX & HELPERS ──────────────────────────────────────────────────────────
SAFE_RE  = re.compile(r"[^A-Za-z0-9._-]")
DATE_RE  = re.compile(r"(\d{6,8})")        # 20250513 or 051325

def safe_filename(txt: str) -> str:
    return SAFE_RE.sub("_", txt)

def best_stamp(row: dict) -> str:
    """
    Return an 8-digit YYYYMMDD stamp for naming scraped files.

    Priority
    --------
    1. ISO timestamp in `published` / `pub_date` (YYYY-MM-DD[,THH:MM…])
    1-bis. DD-MM-YYYY       (Eurostat, StatsCan, Philly Fed)
    1-ter. YYYY/MM/DD or DD/MM/YYYY
    2. 8- or 6-digit block inside release_id or url
    3. Today's UTC date
    """
    pub = (row.get("published") or row.get("pub_date") or "").strip()
    if pub:
        # 1. ISO (YYYY-MM-DD…)
        try:
            return datetime.fromisoformat(pub.rstrip("Z")).strftime("%Y%m%d")
        except Exception:
            pass

        # 1-bis. DD-MM-YYYY
        try:
            return datetime.strptime(pub, "%d-%m-%Y").strftime("%Y%m%d")
        except Exception:
            pass

        # 1-ter. YYYY/MM/DD  or  DD/MM/YYYY
        for fmt in ("%Y/%m/%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(pub, fmt).strftime("%Y%m%d")
            except Exception:
                pass

    # 2. look for digits in release_id or url
    for field in (row.get("release_id", ""), row.get("url", "")):
        m = DATE_RE.search(field)
        if m:
            s = m.group(1)
            if len(s) == 8:                 # e.g. 20250513
                return s
            if len(s) == 6:                 # e.g. 051325 → 20250513
                mo, dy, yy = s[:2], s[2:4], s[4:]
                yy = ("20" if int(yy) < 80 else "19") + yy
                return f"{yy}{mo}{dy}"

    # 3. fallback → today
    return datetime.utcnow().strftime("%Y%m%d")

def derive_indicator(row: dict) -> str:
    """Return something like 'BLS_CPI'."""
    if row.get("indicator"):
        return row["indicator"].strip()
    src = (row.get("source")  or "").strip()
    dts = (row.get("dataset") or "").strip()
    if src and dts:
        return f"{src}_{dts}"
    rid = (row.get("release_id") or "").split("_")
    if len(rid) >= 2 and not rid[1].startswith("http"):
        return "_".join(rid[:2])
    return (rid[0] or "UNKNOWN")

def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            rows.append("\t".join(cells))
        table.replace_with("\n".join(rows) + "\n")
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()

def scrape_from_url(url: str) -> str:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return html_to_text(r.text)

def scrape_from_file(path: Path) -> str:
    return html_to_text(path.read_text(encoding="utf-8", errors="ignore"))

def lookup_raw(row: dict) -> Path | None:
    """Find the raw HTML/PDF file corresponding to this row."""
    patterns = [
        safe_filename(row.get("release_id", "")) + "*",
        safe_filename(row.get("url", ""))        + "*",
    ]
    for pat in patterns:
        matches = list(RAW_DIR.glob(pat))
        if matches:
            return matches[0]
    return None

# ── LOAD INPUT TABLE ─────────────────────────────────────────────────────────
if args.excel:
    df = pd.read_excel(args.excel)
    if "url" not in df.columns:
        sys.exit("--excel file must contain at least a 'url' column.")
    records = df.to_dict("records")
else:
    if not QUEUE_CSV.exists():
        sys.exit("rss_queue.csv not found and no --excel given.")
    with QUEUE_CSV.open(encoding="utf-8", newline="") as f:
        records = [r for r in csv.DictReader(f) if r.get("status") == "DOWNLOADED"]
    if not records:
        sys.exit("No DOWNLOADED rows in rss_queue.csv – run download_agent first.")

# ── KEEP ONLY LATEST PER INDICATOR ───────────────────────────────────────────
latest = {}
for r in records:                      # rss_agent writes newest first
    ind = derive_indicator(r)
    if ind not in latest:
        latest[ind] = r                # first encountered → newest

# ── SCRAPE LOOP ──────────────────────────────────────────────────────────────
for ind, row in latest.items():
    # ── SKIP Nasdaq earnings (they are handled by earnings_agent) ──
    if row.get("dataset", "").startswith("EARN_"):
        continue
    url   = (row.get("url") or "").strip()
    stamp = best_stamp(row)

    out_dir  = OUT_ROOT / ind
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{ind}_{stamp}.txt"

    raw_path = lookup_raw(row)
    try:
        if raw_path and raw_path.suffix.lower().endswith(".html"):
            text = scrape_from_file(raw_path)
        elif raw_path and raw_path.suffix.lower().endswith(".pdf"):
            sys.stderr.write(f"[WARN]  {ind}: PDF found ({raw_path.name}) – skipped\n")
            continue
        else:
            if not url:
                sys.stderr.write(f"[WARN]  {ind}: no URL & no raw file – skipping\n")
                continue
            text = scrape_from_url(url)
    except Exception as e:
        sys.stderr.write(f"[WARN]  {ind}: scrape failed → {e}\n")
        continue

    out_file.write_text(text, encoding="utf-8")
    print(f"[OK]   {ind}  {out_file}")

print("Scrape-agent complete.")
