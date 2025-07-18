# File: mpp_dashboard/agents/download_agent.py

"""
download_agent.py
──────────────────────────────────────────────────────
Reads data/rss_queue.csv for rows with status == QUEUED.
Downloads each release URL to data/raw/{safe_release_id}.html or .pdf.
• Success  → status = DOWNLOADED
• Any HTTP 4xx/5xx, timeout, or other error → status = FAILED_DL
Sends a browser User-Agent header so BLS pages aren’t blocked.
"""

import csv
import time
import logging
import datetime as dt
import re
from pathlib import Path

import requests

# ── Paths relative to mpp_dashboard root ─────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
QUEUE_CSV = ROOT / "data" / "rss_queue.csv"
RAW_DIR   = ROOT / "data" / "raw"
LOG_DIR   = ROOT / "logs"

RAW_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / f"download_{dt.date.today()}.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

# ── Helpers ──────────────────────────────────────────────────────
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"

def safe_filename(text: str) -> str:
    """Replace illegal filename chars with underscore."""
    return re.sub(r'[^A-Za-z0-9._-]', '_', text)

def file_extension(url: str) -> str:
    """Choose extension based on URL."""
    return ".pdf" if url.lower().endswith(".pdf") else ".html"

# ── Main ─────────────────────────────────────────────────────────
def main():
    if not QUEUE_CSV.exists():
        logging.warning("rss_queue.csv missing – nothing to download.")
        return

    rows = list(csv.DictReader(QUEUE_CSV.open(encoding="utf-8")))
    dirty = False

    for row in rows:
        if row.get("status") != "QUEUED":
            continue

        url = row["url"]
        ext = file_extension(url)

        # create a safe filename from the release_id
        fname = safe_filename(row["release_id"]) + ext
        outfile = RAW_DIR / fname

        # shorter timeout for Eurostat, longer for others
        timeout = 15 if "ec.europa.eu" in url else 60

        try:
            resp = requests.get(url,
                                timeout=timeout,
                                headers={"User-Agent": UA},
                                allow_redirects=True)
            if resp.status_code >= 400:
                raise requests.HTTPError(f"{resp.status_code} {resp.reason}")

            outfile.write_bytes(resp.content)
            row["status"] = "DOWNLOADED"
            row["error"]  = ""
            logging.info("DOWNLOADED  %s", row["release_id"])

        except Exception as e:
            row["status"] = "FAILED_DL"
            row["error"]  = str(e)
            logging.error("FAILED_DL   %s  –  %s", row["release_id"], e)

        # polite pause
        time.sleep(0.5)
        dirty = True

    if dirty:
        # write back updated statuses
        with open(QUEUE_CSV, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=rows[0].keys())
            w.writeheader()
            w.writerows(rows)
        logging.info("rss_queue.csv updated.")

    logging.info("Download agent finished.")


if __name__ == "__main__":
    main()
