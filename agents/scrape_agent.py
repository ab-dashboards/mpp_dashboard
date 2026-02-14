#!/usr/bin/env python3
"""
Markets Policy Partners – Pipeline · Scrape-Agent.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
QUEUE_CSV = ROOT / "data" / "rss_queue.csv"

SAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
DATE_RE = re.compile(r"(\d{6,8})")


def safe_filename(txt: str) -> str:
    return SAFE_RE.sub("_", txt)


def best_stamp(row: dict) -> str:
    pub = (row.get("published") or row.get("pub_date") or "").strip()
    if pub:
        for parser in (
            lambda s: datetime.fromisoformat(s.rstrip("Z")),
            lambda s: datetime.strptime(s, "%d-%m-%Y"),
            lambda s: datetime.strptime(s, "%Y/%m/%d"),
            lambda s: datetime.strptime(s, "%d/%m/%Y"),
        ):
            try:
                return parser(pub).strftime("%Y%m%d")
            except Exception:
                continue

    for field in (row.get("release_id", ""), row.get("url", "")):
        m = DATE_RE.search(field)
        if not m:
            continue
        s = m.group(1)
        if len(s) == 8:
            return s
        if len(s) == 6:
            mo, dy, yy = s[:2], s[2:4], s[4:]
            yy = ("20" if int(yy) < 80 else "19") + yy
            return f"{yy}{mo}{dy}"

    return datetime.utcnow().strftime("%Y%m%d")


def derive_indicator(row: dict) -> str:
    if row.get("indicator"):
        return row["indicator"].strip()
    src = (row.get("source") or "").strip()
    dts = (row.get("dataset") or "").strip()
    if src and dts:
        return f"{src}_{dts}"
    rid = (row.get("release_id") or "").split("_")
    if len(rid) >= 2 and not rid[1].startswith("http"):
        return "_".join(rid[:2])
    return rid[0] or "UNKNOWN"


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
    patterns = [
        safe_filename(row.get("release_id", "")) + "*",
        safe_filename(row.get("url", "")) + "*",
    ]
    for pat in patterns:
        matches = list(RAW_DIR.glob(pat))
        if matches:
            return matches[0]
    return None


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Scrape plain text from latest releases")
    ap.add_argument("--excel", help="Excel file with indicator/url columns (optional)")
    ap.add_argument("--output_dir", default=str(ROOT / "releases"))
    return ap.parse_args()


def load_records(excel: str | None) -> list[dict]:
    if excel:
        df = pd.read_excel(excel)
        if "url" not in df.columns:
            raise SystemExit("--excel file must contain at least a 'url' column.")
        return df.to_dict("records")
    if not QUEUE_CSV.exists():
        raise SystemExit("rss_queue.csv not found and no --excel given.")
    with QUEUE_CSV.open(encoding="utf-8", newline="") as f:
        records = [r for r in csv.DictReader(f) if r.get("status") == "DOWNLOADED"]
    if not records:
        raise SystemExit("No DOWNLOADED rows in rss_queue.csv – run download_agent first.")
    return records


def run(excel: str | None, output_dir: str) -> None:
    out_root = Path(output_dir).expanduser()
    out_root.mkdir(parents=True, exist_ok=True)
    records = load_records(excel)

    latest: dict[str, dict] = {}
    for r in records:
        ind = derive_indicator(r)
        if ind not in latest:
            latest[ind] = r

    for ind, row in latest.items():
        if row.get("dataset", "").startswith("EARN_"):
            continue
        url = (row.get("url") or "").strip()
        stamp = best_stamp(row)

        out_dir = out_root / ind
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


def main() -> None:
    args = parse_args()
    run(args.excel, args.output_dir)


if __name__ == "__main__":
    main()
