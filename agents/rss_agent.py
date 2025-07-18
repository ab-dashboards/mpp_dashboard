# File: mpp_dashboard/agents/rss_agent.py
"""
rss_agent.py – pull RSS/Atom feeds, queue press-releases for download
"""

import csv, logging, datetime as dt, time
from pathlib import Path
import re, requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import feedparser, pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────
ROOT        = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config" / "feeds_config.xlsx"
QUEUE_CSV   = ROOT / "data"   / "rss_queue.csv"
LOG_DIR     = ROOT / "logs"; LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    filename=LOG_DIR / f"rss_{dt.date.today():%Y-%m-%d}.log",
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

# ── Default feed list (only first run) ─────────────────────────────────
DEFAULT_FEEDS = [
    ("BLS","CPI","https://www.bls.gov/feed/cpi.rss","bls_html_cpi",True),
    ("BLS","PPI","https://www.bls.gov/feed/ppi.rss","bls_html_ppi",True),
    ("BLS","EMP_SIT","https://www.bls.gov/feed/empsit.rss","bls_html_empl",True),
    ("Eurostat","EURO_INDICATORS",
     "https://ec.europa.eu/eurostat/api/rss/press-releases?lang=en",
     "eurostat_html_generic",True),
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# ── Helpers ────────────────────────────────────────────────────────────
def bootstrap_config() -> pd.DataFrame:
    if CONFIG_FILE.exists():
        return pd.read_excel(CONFIG_FILE)

    CONFIG_FILE.parent.mkdir(exist_ok=True)
    df = pd.DataFrame(
        DEFAULT_FEEDS, columns=["source","dataset","url","parser","active"]
    )
    df.to_excel(CONFIG_FILE, index=False)
    logging.warning("Created default feeds_config.xlsx")
    return df

def load_existing_queue() -> list[dict]:
    if not QUEUE_CSV.exists():
        return []
    with QUEUE_CSV.open(newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))
def sort_key(r):
    pub = r["published"]
    try:
        # DD-MM-YYYY → 20250619   or   YYYY-MM-DD → 20250619
        if "-" in pub:
            parts = pub.split("-")
            if len(parts[0]) == 4:               # ISO
                y, m, d = parts
            else:                                # DD-MM-YYYY
                d, m, y = parts
            return f"{y}{m}{d}"
    except Exception:
        pass
    return ""                                    # fallback

def write_queue(all_rows:list[dict]) -> None:
    cols=["release_id","source","dataset","parser",
          "url","published","status","error"]
    for r in all_rows:
        for c in cols:
            r.setdefault(c,"")
    all_rows.sort(key=sort_key, reverse=True)
    QUEUE_CSV.parent.mkdir(exist_ok=True)
    with QUEUE_CSV.open("w", newline='', encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=cols, quoting=csv.QUOTE_MINIMAL)
        w.writeheader(); w.writerows(all_rows)

# ── Main ───────────────────────────────────────────────────────────────
def main()->None:
    cfg      = bootstrap_config()
    active   = cfg[cfg["active"].astype(str).str.upper()=="TRUE"]

    existing = load_existing_queue()
    seen_ids = {r["release_id"] for r in existing}
    new_rows = []

    for _, row in active.iterrows():
        # ── Generic crawler: parser starts with "crawler:" ───────────────
        parser_spec = str(row.get("parser",""))
        if parser_spec.startswith("crawler:"):
            pattern = parser_spec.split(":",1)[1]
            logging.info("Crawler row – source=%s dataset=%s pattern=%s",
                         row["source"], row["dataset"], pattern)
            try:
                resp = requests.get(row["url"], headers=UA, timeout=15)
                logging.info("Fetcher HTTP %s for %s", resp.status_code, row["url"])
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text,"lxml")

                # ---- extract “Last updated:” date ------------------------
                published = ""
                page_text = soup.get_text(" ", strip=True)
                mdate = re.search(
                    r"Last updated:\s*([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})",
                    page_text, flags=re.I
                )
                if mdate:
                    mon_str, day, year = mdate.groups()
                    try:
                        mon_num = dt.datetime.strptime(mon_str,"%B").month
                        # NEW (YYYY-MM-DD)  ← ISO 8601 so scrape_agent can parse it
                        published = f"{year}-{mon_num:02d}-{int(day):02d}"
                    except ValueError:
                        pass
                # ----------------------------------------------------------

                regex = re.compile(pattern)
                link_tag = soup.find("a", href=regex) or soup.find(
                    "a", href=lambda h: h and regex.search(h)
                )
                logging.info("Matched tags: %d", 1 if link_tag else 0)
                if not link_tag:
                    logging.warning("Crawler: no href matched for %s", row["dataset"])
                    continue

                rel_url = urljoin(row["url"], link_tag["href"])
                logging.info("Selected release URL: %s", rel_url)

                # fallback if “Last updated” missing
                if not published:
                    m = regex.search(rel_url)
                    if m and len(m.groups())>=2:
                        year, month = m.group(1), m.group(2)
                        published   = f"{year}-{month}-01"

                rel_id = f"{row['source']}_{row['dataset']}_{rel_url}"
                if rel_id in seen_ids:
                    logging.info("Already queued: %s", rel_id)
                    continue

                new_rows.append(
                    dict(release_id=rel_id, source=row["source"],
                         dataset=row["dataset"], parser=row["parser"],
                         url=rel_url, published=published,
                         status="QUEUED", error="")
                )
                seen_ids.add(rel_id)
                logging.info("Crawler queued %s", rel_id)

            except Exception as e:
                logging.error("Crawler error for %s: %s", row["dataset"], e)
            continue  # skip RSS logic for this row
        # ────────────────────────────────────────────────────────────────

        fp = feedparser.parse(row["url"], request_headers=UA)
        if not fp.entries:
            logging.warning("No entries parsed from %s", row["url"]); continue

        for ent in fp.entries:
            title_lower = (ent.get("title") or "").lower()
            ds = row["dataset"]
            if ds=="EARN_PRE" and "pre-market earnings report" not in title_lower:
                continue
            if ds=="EARN_AH" and "after-hours earnings report" not in title_lower:
                continue
            if row["source"]=="StatsCan":
                if ds=="NHPI_CA" and "new housing price index" not in title_lower:
                    continue
                if ds=="PPI_CA" and "industrial product" not in title_lower:
                    continue

            guid = ent.get("id"); link = ent.get("link")
            if not link and ent.get("links"): link = ent.links[0].get("href")
            unique = guid or link
            if not unique: continue
            rel_id = f"{row['source']}_{row['dataset']}_{unique}"
            if rel_id in seen_ids: continue

            if ent.get("published_parsed") or ent.get("updated_parsed"):
                ts = ent.get("published_parsed") or ent.get("updated_parsed")
                published = dt.datetime.fromtimestamp(time.mktime(ts)).strftime("%Y-%m-%d")
            else:
                published = ent.get("published") or ent.get("updated") or ""

            new_rows.append(
                dict(release_id=rel_id, source=row["source"],
                     dataset=row["dataset"], parser=row["parser"],
                     url=link, published=published,
                     status="QUEUED", error="")
            )
            seen_ids.add(rel_id)

    if new_rows:
        write_queue(existing + new_rows)
        logging.info("Queued %d new releases", len(new_rows))
    else:
        write_queue(existing)
        logging.info("No new items found; queue refreshed")

if __name__ == "__main__":
    main()
