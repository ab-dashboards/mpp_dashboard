# File: mpp_dashboard/agents/earnings_agent.py
"""
earnings_agent.py – scrape Nasdaq “preview” earnings posts
(EARN_PRE / EARN_AH), save the HTML→text and the extracted tickers.

Output
──────
releases/
  └─ Nasdaq_EARN_PRE/
       ├─ Nasdaq_EARN_PRE_YYYYMMDD.txt
       └─ Nasdaq_EARN_PRE_YYYYMMDD.tickers
"""

from __future__ import annotations
import csv, datetime as dt, re, sys
from pathlib import Path
from bs4 import BeautifulSoup

# ── CONSTANT LOCATIONS ──────────────────────────────────────────────────
ROOT      = Path(__file__).resolve().parent.parent
RAW_DIR   = ROOT / "data" / "raw"
REL_DIR   = ROOT / "releases"
QUEUE_CSV = ROOT / "data" / "rss_queue.csv"
LOG       = lambda *a, **k: print(*a, file=sys.stderr, **k)

# ── REGEXES ─────────────────────────────────────────────────────────────
YEAR_SLUG = re.compile(r"-(19|20)\d{2}-")          # for ticker extraction
TICK_PAT  = re.compile(r"^[A-Z]{1,5}(?:\.[A-Z])?$")
MONTHS    = {"JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG",
             "SEP","SEPT","OCT","NOV","DEC","DECEMBER"}

# earnings day inside slug: …-june-20-2025-…
SLUG_DATE_RE = re.compile(
    r"-(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*-(\d{1,2})-(\d{4})",
    re.I,
)

# ── HELPERS ─────────────────────────────────────────────────────────────
def newest_by_tag(rows: list[dict]) -> dict[str, dict]:
    """
    Pick the latest EARN_PRE / EARN_AH row.

    Priority for determining the date stamp:
        1. Earnings day parsed from the URL slug (…-june-20-2025-…)
        2. ISO published (YYYY-MM-DD or YYYY-MM-DDTHH:MM…)
        3. DD-MM-YYYY published
        4. date.min if all else fails
    """
    latest: dict[str, dict] = {}

    for r in rows:
        tag = r["dataset"]            # EARN_PRE or EARN_AH

        # 1. try slug → earnings day
        d: dt.date
        m = SLUG_DATE_RE.search(r["url"])
        if m:
            mon_txt, day_txt, year_txt = m.groups()
            mon_num = dt.datetime.strptime(mon_txt[:3], "%b").month
            d = dt.date(int(year_txt), mon_num, int(day_txt))
        else:
            pub = r.get("published", "").strip()

            # 2. ISO yyyy-mm-dd (optionally with time)
            try:
                d = dt.datetime.fromisoformat(pub[:10]).date()
            except ValueError:
                # 3. DD-MM-YYYY
                try:
                    d = dt.datetime.strptime(pub, "%d-%m-%Y").date()
                except ValueError:
                    d = dt.date.min          # 4. fallback

        if tag not in latest or d > latest[tag]["_ts"]:
            r["_ts"] = d
            latest[tag] = r

    return latest


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_tickers(url: str) -> list[str]:
    """Tokens after the year slug; skip month names."""
    m = YEAR_SLUG.search(url.lower())
    if not m:
        return []
    slug = url[m.end():].split("?", 1)[0]
    tickers: list[str] = []
    for tok in slug.split("-"):
        up = tok.upper()
        if up in MONTHS:
            continue
        if TICK_PAT.match(up):
            tickers.append(up)
    return tickers


def sidecar_path(txt: Path) -> Path:
    return txt.with_suffix(".tickers")


# ── MAIN ────────────────────────────────────────────────────────────────
def main() -> None:
    if not QUEUE_CSV.exists():
        LOG("rss_queue.csv not found – aborting.")
        return

    with QUEUE_CSV.open(encoding="utf-8", newline="") as f:
        rows = [
            r for r in csv.DictReader(f)
            if r["source"] == "Nasdaq"
            and r["dataset"] in ("EARN_PRE", "EARN_AH")
            and r["status"] == "DOWNLOADED"
        ]

    if not rows:
        LOG("No downloaded Nasdaq earnings rows.")
        return

    for tag, r in newest_by_tag(rows).items():
        ind_dir = f"Nasdaq_{tag}"
        rel_dir = REL_DIR / ind_dir
        rel_dir.mkdir(parents=True, exist_ok=True)

        stamp    = r["_ts"].strftime("%Y%m%d")
        txt_path = rel_dir / f"{ind_dir}_{stamp}.txt"

        # locate raw HTML
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", r["release_id"])
        raw  = next((p for p in RAW_DIR.glob(f"{safe}*.html")), None)
        if not raw:
            LOG(f"[WARN] raw HTML for {tag} not found → {r['url']}")
            continue

        body = html_to_text(raw.read_text(encoding="utf-8", errors="ignore"))
        txt_path.write_text(body, encoding="utf-8")
        LOG(f"[OK]    wrote {txt_path.relative_to(ROOT)}")

        tix = extract_tickers(r["url"])
        if not tix:
            LOG(f"[WARN] could not parse tickers from URL → {r['url']}")
            continue

        sidecar_path(txt_path).write_text(",".join(tix), encoding="utf-8")
        LOG(f"[OK]    {tag}  {txt_path.name}  → {len(tix)} tickers")


if __name__ == "__main__":
    main()
