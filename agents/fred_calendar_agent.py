# File: mpp_dashboard/agents/fred_calendar_agent.py
"""
Fetch upcoming FRED economic-release dates (next 4 weeks) and save them to
data/fred_calendar.json so the Streamlit dashboard can display them.

Run this once a day via cron / Task Scheduler or just manually:
    python fred_calendar_agent.py
"""

from __future__ import annotations
import json
import os
import pathlib
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

# ── PATHS ────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent   # …/mpp_dashboard
OUT_PATH = ROOT / "data" / "fred_calendar.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── ENV / API KEY ────────────────────────────────────────────────────────
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
if not FRED_API_KEY:
    raise SystemExit("FRED_API_KEY not found in your environment (.env)")

# ── WHICH RELEASES TO TRACK?  (edit as you like) ─────────────────────────
# See https://fred.stlouisfed.org/docs/api/fred/releases.html for IDs.
RELEASES: dict[int, str] = {
    10: "Personal Income & Outlays",           # PCE / Core PCE
    50: "Producer Price Index",
    51: "Retail Sales",
    52: "Consumer Price Index",
    53: "Employment Situation",
    54: "Industrial Production",
    55: "Advance Intl Trade in Goods",
    56: "Gross Domestic Product",
    60: "ISM Manufacturing Index",
}

# If you want *every* FRED release, fetch /releases first; but that’s 1000+ IDs
# and takes a long time.  A curated list is faster and keeps the widget useful.

# ── HELPERS ──────────────────────────────────────────────────────────────
BASE = "https://api.stlouisfed.org/fred"

def get_release_dates(rid: int) -> list[str]:
    """Return YYYY-MM-DD strings of upcoming dates for one release ID."""
    resp = requests.get(
        f"{BASE}/release/dates",
        params={
            "api_key": FRED_API_KEY,
            "release_id": rid,
            "include_release_dates_with_no_data": "true",   # ← string, not bool
            "file_type": "json",
        },
        timeout=10,
    )
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        print(f"[WARN] release_id {rid}: {e}")
        return []                 # graceful degradation → keep the agent running
    return [d["date"] for d in resp.json()["release_dates"]]

# ── BUILD UPCOMING EVENTS LIST ───────────────────────────────────────────
today = datetime.now(timezone.utc).date()
horizon = today + timedelta(days=28)      # 4-week look-ahead

events: list[dict] = []
for rid, title in RELEASES.items():
    for date_str in get_release_dates(rid):
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
        if today <= d <= horizon:
            # Most US macro releases drop at 08:30 ET; others vary.
            # We stick with 08:30 ET (13:30 UTC) unless you specify otherwise.
            dt_utc = datetime(d.year, d.month, d.day, 13, 30, tzinfo=timezone.utc)
            events.append(
                {
                    "release_id": rid,
                    "title": title,
                    "dt_utc": dt_utc.isoformat(),
                    "url": f"https://fred.stlouisfed.org/release?rid={rid}",
                }
            )

events.sort(key=lambda e: e["dt_utc"])

# ── WRITE JSON ───────────────────────────────────────────────────────────
with OUT_PATH.open("w", encoding="utf-8") as f:
    json.dump(events, f, indent=2)

print(f"✅  Wrote {len(events)} events to {OUT_PATH.relative_to(ROOT)}")
