# File: mpp_dashboard/agents/summary_agent.py
"""
Markets Policy Partners – Flash-Brief Dashboard   v7.4-b
Adds Nasdaq corporate-earnings workflow (EARN_PRE / EARN_AH)
& in-card paragraph separation for each ticker.
"""

from __future__ import annotations
import glob, os, pathlib, re, json, base64               # ← base64 added
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd
import requests                                         # ← Constant-Contact API
import subprocess
import sys
from pathlib import Path

# ── PAGE CONFIG ────────────────────────────────────────────────────────────
st.set_page_config(layout="wide")
MPP_NAVY = "#0B1F3F"
LOGO_URL = "https://marketspolicy.com/wp-content/uploads/2019/11/logo_MPP.png"
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Merriweather:wght@700&family=Lato&display=swap');
html, body, [class*="css"]  {{ font-family:'Lato', sans-serif; }}
h1,h2,h3                    {{ font-family:'Merriweather', serif; color:{MPP_NAVY}; }}
.mpp-header                {{ background:#FFF; padding:24px 0; display:flex; justify-content:center; }}
.mpp-header img            {{ height:128px; }}
.mpp-card        {{ background:#F5F7FA; border-radius:0.75rem; padding:1.4rem;
                    box-shadow:0 2px 6px rgba(0,0,0,.05);
                    color:#0B1F3F; }}
/* ── NEW: tidy separation for each ticker paragraph ── */
.ticker-blurb              {{ margin:0 0 .8rem 0; line-height:1.45; }}
</style>
<div class="mpp-header"><img src="{LOGO_URL}" alt="MPP logo"></div>
""", unsafe_allow_html=True)
st.title("Flash-Brief Dashboard")
# ── UPDATE RELEASES BUTTON ─────────────────────────────────────────────
if st.sidebar.button("Update Releases"):
    with st.spinner("Updating all releases…"):
        script_dir = Path(__file__).resolve().parent
        for script in [
            "rss_agent.py",
            "download_agent.py",
            "scrape_agent.py",
            "earnings_agent.py",
        ]:
            subprocess.run(
                [sys.executable, str(script_dir / script)],
                check=True,
            )
    st.sidebar.success("✅ Releases pipeline complete!")

# ── ENV / OPENAI ───────────────────────────────────────────────────────────
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    st.error("🚫 OPENAI_API_KEY missing.")
    st.stop()
client = OpenAI(api_key=OPENAI_KEY)

# ── CONSTANTS & HELPERS ────────────────────────────────────────────────────
ROOT        = pathlib.Path(__file__).resolve().parent.parent
DATA_ROOT   = ROOT / "releases"
CONFIG_XLSX = ROOT / "config" / "feeds_config.xlsx"

REGION_MAP = {
    "BLS":       "United States",
    "Eurostat":  "Euro Area",
    "Nasdaq":    "United States",
    "PhillyFed": "United States",
    "StatsCan":  "Canada",          # ← new line
}

NY_TZ = ZoneInfo("America/New_York")

if CONFIG_XLSX.exists():
    cfg_df = pd.read_excel(CONFIG_XLSX, dtype=str)
    DISPLAY_MAP = dict(zip(cfg_df["dataset"],
                           cfg_df.get("display_name", cfg_df["dataset"])))
else:
    DISPLAY_MAP = {}

DATE_RE = re.compile(r"_(\d{6,8})")        # match 6 or 8 digits anywhere
DATE_WINDOWS = {
    "Last 24 hours": timedelta(days=1),
    "Last 7 days":   timedelta(days=7),
    "Last 30 days":  timedelta(days=30),
    "All dates":     None,
}

# ---- Constant-Contact creds from environment -------------------------------
CC_ACCESS_TOKEN = os.getenv("CC_ACCESS_TOKEN", "")
CC_REFRESH_TOKEN = os.getenv("CC_REFRESH_TOKEN", "")
CC_CLIENT_ID = os.getenv("CC_CLIENT_ID", "")
CC_CLIENT_SECRET = os.getenv("CC_CLIENT_SECRET", "")

CC_LIST_ID = os.getenv("CC_LIST_ID", "")
CC_FROM_EMAIL = os.getenv("CC_FROM_EMAIL", "")
CC_REPLY_TO_EMAIL = os.getenv("CC_REPLY_TO_EMAIL", "")

# ── Nasdaq ticker→company mapping ────────────────────────────────────────────
def load_nasdaq_names() -> dict[str, str]:
    url = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
    try:
        r = requests.get(url, timeout=10)
        lines = r.text.splitlines()
        mapping: dict[str, str] = {}
        for row in lines[1:]:
            if row.startswith("File"):       # footer line
                continue
            cols = row.split("|")
            if len(cols) < 2:
                continue
            mapping[cols[0]] = cols[1]
        return mapping
    except requests.exceptions.RequestException:
        return {}

TICKER_NAME_MAP = load_nasdaq_names()

# ── auto-refresh helper ----------------------------------------------------
def cc_request(method: str, url: str, **kwargs) -> requests.Response:
    """
    Make one Constant-Contact API call.
    • On 401, swap REFRESH_TOKEN → new access-/refresh-token pair and retry once.
    """
    hdrs = kwargs.pop("headers", {})
    hdrs["Authorization"] = f"Bearer {CC_ACCESS_TOKEN}"
    resp = requests.request(method, url, headers=hdrs, timeout=10, **kwargs)

    if resp.status_code == 401 and CC_REFRESH_TOKEN:
        basic = base64.b64encode(f"{CC_CLIENT_ID}:{CC_CLIENT_SECRET}".encode()).decode()
        r = requests.post(
            "https://authz.constantcontact.com/oauth2/default/v1/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data=f"grant_type=refresh_token&refresh_token={CC_REFRESH_TOKEN}",
            timeout=10,
        )
        if r.status_code == 200 and r.json().get("access_token"):
            globals()["CC_ACCESS_TOKEN"]  = r.json()["access_token"]
            globals()["CC_REFRESH_TOKEN"] = r.json()["refresh_token"]
            hdrs["Authorization"] = f"Bearer {CC_ACCESS_TOKEN}"
            resp = requests.request(method, url, headers=hdrs, timeout=10, **kwargs)

    return resp

def scheduled_dt(tag: str, file_dt: datetime) -> datetime:
    """
    Return the *scheduled* earnings-preview time in New-York tz.
    • EARN_PRE → 09:00 ET on the file’s date
    • EARN_AH  → 17:00 ET on the file’s date
    """
    hour = 9 if tag == "EARN_PRE" else 17
    return datetime(file_dt.year, file_dt.month, file_dt.day, hour, 0, tzinfo=NY_TZ)

def rel_date(path: pathlib.Path) -> datetime:
    """
    Return a datetime for sorting.
    • If name has _YYYYMMDD or _DDMMYY, parse it.
    • Otherwise use file-mod-time (UTC).
    """
    m = DATE_RE.search(path.name)
    if not m:
        return datetime.utcfromtimestamp(path.stat().st_mtime)

    digits = m.group(1)
    try:
        if len(digits) == 8:               # 20240618
            return datetime.strptime(digits, "%Y%m%d")
        elif len(digits) == 6:             # 250522 -> 2022-05-25
            return datetime.strptime(digits, "%d%m%y")
    except ValueError:
        pass

    return datetime.utcfromtimestamp(path.stat().st_mtime)

def split_dir(dir_name: str) -> tuple[str, str, str]:
    src, code = dir_name.split("_", 1)
    region  = REGION_MAP.get(src, src)
    pretty  = DISPLAY_MAP.get(code, code)
    return region, code, pretty

# ── ★ earnings-specific prompt --------------------------------------------
def earnings_prompt(tag: str, tickers: list[str], raw: str) -> tuple[str, str]:
    when   = "Tomorrow’s pre-market earnings" if tag == "EARN_PRE" else "Tonight’s after-hours earnings"
    plural = ", ".join(tickers)

    prompt = f"""
    You are a financial-markets analyst.

    Context
    ───────
    Preview type : {when}
    Tickers      : {plural}

    **Respond ONLY about these tickers. If the source mentions other symbols, ignore them completely.**

    Source article (trimmed)
    ------------------------
    {raw[:150_000]}

    Write *exactly* the following:

    1. First line: ≤10-word Oped style headline.
    2. Blank line.
    3. Opening sentence repeating timing (pre-market / after-hours).

    4. One paragraph per ticker **in alphabetical order**, using NASDAQ-style earnings-report format:
       • Line 1 – Briefly introduce the company (e.g., Broadcom Inc. (AVGO), a major semiconductor firm) and give its consensus EPS & revenue (or guidance).  
       • Line 2 – EPS & revenue for prior Q or YoY and % change, if available.  
       • Line 3 – One other salient fact (P/E, performance, guidance detail, etc.) that is present in the text.
    This is a sample format for your reference: 
    Analog Devices is set to report Q4 earnings, with consensus estimates for EPS of $1.64 and revenue of $2.4 billion, significantly lower than the 2.01 EPS and $2.72 billion revenue recorded in Q3. 

    Put a single blank line between paragraphs.
    Do **not** fabricate numbers; omit any figure not present in the text.
    No bullets, no sources.
    """

    res = client.chat.completions.create(
        model="o4-mini-2025-04-16",
        messages=[{"role": "user", "content": prompt}],
    )
    lines = res.choices[0].message.content.strip().splitlines()
    return (lines[0] if lines else "No headline.",
            "\n".join(lines[2:]).strip())

# ── ★ helper for saved tickers + fallback ----------------------------------
def read_saved_tickers(txt_path: pathlib.Path) -> list[str]:
    side = txt_path.with_suffix(".tickers")
    if side.exists():
        return [t.strip().upper() for t in side.read_text().split(",") if t.strip()]
    m = re.findall(r"-([a-z]{1,5})(?:-|$)", txt_path.stem, flags=re.I)
    return [s.upper() for s in m]

# ── macro prompt  (unchanged) ----------------------------------------------
def gpt_summary(ind_name: str, raw: str) -> tuple[str, str]:
    prompt = (
        "You are a macroeconomic analyst.\n\n"
        f"Indicator: {ind_name}\n\n"
        "Here is the raw press-release content (incl tables):\n"
        "----\n" + raw[:120_000] + "\n----\n\n"
        "Return only:\n"
        "• First line: ≤10-word Oped style headline.\n"
        "• Blank line.\n"
        "• Then a Bureau-of-Labor-Statistics-style brief (3 very short and crisp paragraphs, "
        "no source citations, maximum 150 words).\n"
        "  – Para1: MoM / YoY results, vs. previous month.\n"
        "  – Para2: Very briefly, discuss key Upward and downward drivers.\n"
        "  – Para3: Very briefly, discuss any other highly relevant or significant trends.\n"
        "Do **not** invent numbers. No bullets, no sources, no vague or generic statements or comments."
        "Use acronyms only after you have used the full name once before in your reference."
        "**If a statistic (YoY, MoM, etc.) is not included in the text below, "
        "say nothing about it—do not state that it was ‘not released’.**\n\n"
    )
    res = client.chat.completions.create(
        model="o4-mini-2025-04-16",
        messages=[{"role": "user", "content": prompt}],
    )
    lines = res.choices[0].message.content.strip().splitlines()
    return (lines[0] if lines else "No headline.",
            " ".join(l.strip() for l in lines[2:] if l.strip()))

# ── BUILD LATEST PATH PER INDICATOR ────────────────────────────────────────
paths = [pathlib.Path(p) for p in glob.glob(f"{DATA_ROOT}/*/*.txt")]
if not paths:
    st.warning("No .txt files in ./releases — run scrape_agent first.")
    st.stop()

latest_path: dict[str, pathlib.Path] = {}
for p in paths:
    d = p.parent.name
    if (d not in latest_path) or (rel_date(p) > rel_date(latest_path[d])):
        latest_path[d] = p

# ── newest earnings + ticker lists -----------------------------------------
def _latest(tag: str) -> tuple[pathlib.Path | None, list[str]]:
    cands = [p for d,p in latest_path.items() if d.endswith(tag)]
    if not cands:
        return None, []
    path = max(cands, key=rel_date)
    return path, read_saved_tickers(path)

pm_path, pm_tickers = _latest("EARN_PRE")
ah_path, ah_tickers = _latest("EARN_AH")

# ── SESSION STATE INIT ─────────────────────────────────────────────────────
def _init(k,v):  # tiny helper
    if k not in st.session_state:
        st.session_state[k] = v

_init("filtered_files", [])
_init("filters_applied", False)
_init("go_clicked", False)
_init("incl_pm", True)
_init("incl_ah", True)
_init("sel_pm", [])
_init("sel_ah", [])

# ── SIDEBAR FILTERS (region / indicator + earnings box) --------------------
with st.sidebar:
    st.header("Filters")

    regions = sorted({split_dir(d)[0] for d in latest_path})
    sel_regions = st.multiselect("Region / Country", regions, [])

    ind_opts = []
    for d in latest_path:
        reg, code, pretty = split_dir(d)
        if code.startswith("EARN"):
            continue
        if not sel_regions or reg in sel_regions:
            ind_opts.append(f"{reg} – {pretty}")
    sel_inds = st.multiselect("Indicator", sorted(ind_opts), [])

    with st.expander("Corporate Earnings (Nasdaq)", expanded=False):
        # ── Include / exclude the two earnings decks
        st.session_state.incl_pm = st.checkbox(
            "Include Pre-Market (next day)",
            value=st.session_state.incl_pm and bool(pm_path),
        )
        st.session_state.incl_ah = st.checkbox(
            "Include After-Hours (today)",
            value=st.session_state.incl_ah and bool(ah_path),
        )

        # ── Checkbox picker – Pre-Market tickers
        if st.session_state.incl_pm and pm_path:
            st.markdown("**Pre-Market tickers**")
            picked_pm: list[str] = []
            for tk in sorted(pm_tickers):
                name = TICKER_NAME_MAP.get(tk, "")
                label = f"{tk} – {name}" if name else tk
                if st.checkbox(label, key=f"pm_{tk}", value=tk in st.session_state.sel_pm):
                    picked_pm.append(tk)
            st.session_state.sel_pm = picked_pm  # update session state

        # ── Checkbox picker – After-Hours tickers
        if st.session_state.incl_ah and ah_path:
            st.markdown("**After-Hours tickers**")
            picked_ah: list[str] = []
            for tk in sorted(ah_tickers):
                name = TICKER_NAME_MAP.get(tk, "")
                label = f"{tk} – {name}" if name else tk
                if st.checkbox(label, key=f"ah_{tk}", value=tk in st.session_state.sel_ah):
                    picked_ah.append(tk)
            st.session_state.sel_ah = picked_ah

    date_choice  = st.selectbox("Show releases from…", list(DATE_WINDOWS), index=1)
    newest_first = st.checkbox("Newest first", value=True)

    # Apply
    if st.button("Apply Filters"):
        # ── 0️⃣ Guard-rail ────────────────────────────────────────────
        # If the user hasn’t picked *anything* (no region, no indicator,
        # and both earnings sections disabled) we return an empty result.
        if (
                not sel_regions
                and not sel_inds
                and not st.session_state.incl_pm
                and not st.session_state.incl_ah
        ):
            st.session_state.filtered_files = []
            st.session_state.filters_applied = True
            st.session_state.go_clicked = False
            st.info("Please select at least one region/indicator or earnings deck.")
            st.stop()

        # ── 1️⃣ Build filtered list – other filters first ────────────
        filtered: list[pathlib.Path] = []
        delta = DATE_WINDOWS[date_choice]

        for d, p in latest_path.items():
            reg, code, pretty = split_dir(d)

            # ---- MACRO INDICATORS -----------------------------------
            if not code.startswith("EARN"):
                # a. Region filter (if any)
                if sel_regions and reg not in sel_regions:
                    continue
                # b. Indicator filter (if any)
                if sel_inds and f"{reg} – {pretty}" not in sel_inds:
                    continue
                # c. If BOTH region & indicator lists are empty,
                #    we *skip* this macro — we don’t want the date
                #    filter to pull in random series.
                if not sel_regions and not sel_inds:
                    continue

            # ---- EARNINGS DECKS ------------------------------------
            else:
                if code == "EARN_PRE" and not st.session_state.incl_pm:
                    continue
                if code == "EARN_AH" and not st.session_state.incl_ah:
                    continue
                # If the corresponding ticker list is now empty,
                # skip the card entirely.
                if code == "EARN_PRE" and not st.session_state.sel_pm:
                    continue
                if code == "EARN_AH" and not st.session_state.sel_ah:
                    continue

            # ---- 2️⃣ Date-window filter (applied last) --------------
            if delta and (datetime.utcnow() - rel_date(p) > delta):
                continue

            filtered.append(p)

        # ---- 3️⃣ Sort & stash in session state ----------------------
        filtered.sort(key=rel_date, reverse=newest_first)
        st.session_state.filtered_files = filtered
        st.session_state.filters_applied = True
        st.session_state.go_clicked = False

    # Matches
    if st.session_state.filters_applied:
        if st.session_state.filtered_files:
            st.markdown("---")
            st.markdown("**Matching releases:**")
            for p in st.session_state.filtered_files:
                r, code, pr = split_dir(p.parent.name)
                label = (f"Nasdaq – {'Pre-Mkt' if code=='EARN_PRE' else 'After-Hrs'} Earnings"
                         if code.startswith("EARN") else f"{r} – {pr}")
                st.markdown(f"- {label} ({rel_date(p).strftime('%Y-%m-%d')})")
            if st.button("Go"):
                st.session_state.go_clicked = True
        else:
            st.info("No releases match the selection.")

# ── STOP if not ready ──────────────────────────────────────────────────────
if not (st.session_state.filters_applied and st.session_state.go_clicked):
    st.stop()
if not st.session_state.filtered_files:
    st.warning("Nothing to display.")
    st.stop()

# ── GENERATE & DISPLAY CARDS ───────────────────────────────────────────────
email_blocks: list[str] = []

for p in st.session_state.filtered_files:
    region, code, pretty = split_dir(p.parent.name)
    raw = p.read_text(encoding="utf-8", errors="ignore")

    # ── Earnings cards ────────────────────────────────────────────────────
    if code in ("EARN_PRE", "EARN_AH"):
        tag     = code
        tickers = (st.session_state.sel_pm if tag=="EARN_PRE"
                   else st.session_state.sel_ah)
        if not tickers:
            continue

        head, brief = earnings_prompt(tag, sorted(tickers), raw)
        title = f"Nasdaq – {'Pre-Market' if tag=='EARN_PRE' else 'After-Hours'} Earnings"
        tick_line = ", ".join(sorted(tickers))

        # ---- wrap each ticker paragraph for email-friendly spacing --------------
        paras = [p.strip() for p in brief.split("\n\n") if p.strip()]

        # new: inline-styled <p> tags instead of <div class="ticker-blurb">
        paras_html = "".join(
            f"<p style='margin:0 0 12px 0; line-height:1.45;'>{p}</p>"
            for p in paras
        )

        body = (
            f"<h3>{head}</h3>"
            f"<p><em>{tick_line}</em></p>"
            f"{paras_html}"
        )

    # ── Macro cards ───────────────────────────────────────────────────────
    else:
        ind_name = f"{region} – {pretty}"
        head, brief = gpt_summary(ind_name, raw)
        title = ind_name
        body  = f"<h3>{head}</h3><p>{brief}</p>"

    # ---- Display & e-mail collect
    st.markdown(f"#### {title}")
    st.markdown(f"<div class='mpp-card'>{body}</div>", unsafe_allow_html=True)
    email_blocks.append(f"<h2>{title}</h2>{body}")

st.success("Dashboard built ✔")

# ▼ Constant-Contact section remains line-for-line as before ▼

# ── SEND-TO-SUBSCRIBERS BUTTON ────────────────────────────────────────────
if st.button("Send to Subscribers"):

    missing_cc = [
        name
        for name, value in {
            "CC_ACCESS_TOKEN": CC_ACCESS_TOKEN,
            "CC_REFRESH_TOKEN": CC_REFRESH_TOKEN,
            "CC_CLIENT_ID": CC_CLIENT_ID,
            "CC_CLIENT_SECRET": CC_CLIENT_SECRET,
            "CC_LIST_ID": CC_LIST_ID,
            "CC_FROM_EMAIL": CC_FROM_EMAIL,
            "CC_REPLY_TO_EMAIL": CC_REPLY_TO_EMAIL,
        }.items()
        if not value
    ]
    if missing_cc:
        st.error("Missing Constant Contact config: " + ", ".join(missing_cc))
        st.stop()

    if not email_blocks:
        st.error("No briefs to send.")
        st.stop()

    # 1️⃣ Build the combined HTML content with tracking tag at top
    #    We explicitly add [[trackingImage]] inside <body>:
    email_body = (
            "<html><body>[[trackingImage]]"
            # Centered logo
            + f"<div style='text-align:center; margin-bottom:20px;'>"
              f"<img src='{LOGO_URL}' alt='MPP logo' width='200' />"
              f"</div>"
            + "<h1>Markets Policy Partners Flash-Brief</h1>"
            + "".join(email_blocks)
            + "</body></html>"
    )

    # 1.1️⃣ Sanity-check size (400 KB limit)
    size_bytes = len(email_body.encode("utf-8"))
    if size_bytes > 380_000:
        st.error(f"Email body too large ({size_bytes} bytes). Trim content.")
        st.stop()

    # 2️⃣ Verify that our 'from' address is confirmed in CC (once per session)
    if "cc_from_confirmed" not in st.session_state:
        v_url = "https://api.cc.email/v3/account/emails"
        try:
            v_resp = cc_request("GET", v_url)  # ← CHANGED ↓
        except requests.exceptions.RequestException as e:
            st.error(f"Network error fetching verified emails: {e}")
            st.stop()

        if v_resp.status_code != 200:
            st.error(f"Could not fetch verified emails — status {v_resp.status_code}")
            st.json(v_resp.json())
            st.stop()

        resp_data = v_resp.json()
        if isinstance(resp_data, dict):
            email_list = resp_data.get("email_addresses", [])
        elif isinstance(resp_data, list):
            email_list = resp_data
        else:
            email_list = []

        confirmed_emails = {
            item.get("email_address")
            for item in email_list
            if item.get("confirm_status") == "CONFIRMED"
        }

        if CC_FROM_EMAIL not in confirmed_emails:
            st.error("Your from-email is not verified (CONFIRMED) in Constant Contact.")
            st.stop()

        st.session_state.cc_from_confirmed = True

    # 3️⃣ Build the exact payload *matching the docs*
    now_str = datetime.now(NY_TZ).strftime("%m/%d/%y (%I:%M %p)").lower()  # eg. 06/15/25 (12:05 pm)
    payload = {
        "name": f"MPP Brief - {now_str}",
        "campaign_type": "OTHER",
        "email_campaign_activities": [
            {
                "format_type": 5,                                    # must be numeric
                "from_email": CC_FROM_EMAIL,                         # string, confirmed
                "from_name": "Markets Policy Partners",               # required string
                "reply_to_email": CC_REPLY_TO_EMAIL,                  # string, confirmed
                "subject": "Markets Policy Partners Flash-Brief",     # required string
                "html_content": email_body,                           # full HTML
                "plain_content": (
                    "Markets Policy Partners Flash-Brief\n\n"
                    + "\n\n".join(
                        re.sub(r"<[^>]+>", "", block) for block in email_blocks
                    )
                ),
                "contact_list_ids": [CC_LIST_ID],                     # subscriber list
                # physical_address_in_footer is *optional*—we omit it.
            }
        ]
    }

    # 4️⃣ Submit to /v3/emails (Create Campaign)
    try:
        resp = cc_request(
            "POST",
            "https://api.cc.email/v3/emails",
            headers={"Content-Type": "application/json"},
            json=payload,
        )
    except requests.exceptions.RequestException as e:
        st.error(f"Network error creating campaign: {e}")
        st.stop()

    # 5️⃣ Handle the response
    if resp.status_code in (200, 201):
        st.success("✅ Campaign created! Check Constant Contact to send or schedule.")
    elif resp.status_code == 400:
        st.error("❌ Validation error—please check required payload fields.")
        st.json(resp.json())
    elif resp.status_code == 401:
        st.error("❌ Access token expired or invalid.")
    elif resp.status_code == 404:
        st.error("❌ Endpoint not found—verify your URL.")
        st.json(resp.json())
    elif resp.status_code == 429:
        st.error("❌ Rate limit exceeded—please wait and try again.")
        st.json(resp.json())
    else:
        st.error(f"❌ Constant Contact returned {resp.status_code} (Internal Server Error)")
        st.json(resp.json())

# streamlit run summary_agent.py