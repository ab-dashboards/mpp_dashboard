# File: mpp_dashboard/agents/summary_agent.py
"""
Markets Policy Partners – Flash-Brief Dashboard  v7.3
Adds: “Send to Subscribers” button that sends the day’s briefs to Constant Contact.
"""

from __future__ import annotations
import glob, os, pathlib, re, json
from datetime import datetime, timedelta

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import pandas as pd
import requests               # ← NEW: needed for Constant Contact API calls

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
.mpp-card                  {{ background:#F5F7FA; border-radius:0.75rem; padding:1.4rem;
                              box-shadow:0 2px 6px rgba(0,0,0,.05); }}
</style>
<div class="mpp-header"><img src="{LOGO_URL}" alt="MPP logo"></div>
""", unsafe_allow_html=True)
st.title("Flash-Brief Dashboard")


# ── ENV / OPENAI ───────────────────────────────────────────────────────────
load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_KEY:
    st.error("🚫  OPENAI_API_KEY missing.")
    st.stop()
client = OpenAI(api_key=OPENAI_KEY)


# ── CONSTANTS & HELPERS ────────────────────────────────────────────────────
ROOT        = pathlib.Path(__file__).resolve().parent.parent
DATA_ROOT   = ROOT / "releases"
CONFIG_XLSX = ROOT / "config" / "feeds_config.xlsx"

REGION_MAP = {"BLS": "United States", "Eurostat": "Euro Area"}

# ---- friendly names lookup
if CONFIG_XLSX.exists():
    cfg_df = pd.read_excel(CONFIG_XLSX, dtype=str)
    DISPLAY_MAP = dict(zip(cfg_df["dataset"],
                           cfg_df.get("display_name", cfg_df["dataset"])))
else:
    DISPLAY_MAP = {}

DATE_RE = re.compile(r"_(\d{8})\.txt$")
DATE_WINDOWS = {
    "Last 24 hours": timedelta(days=1),
    "Last 7 days":   timedelta(days=7),
    "Last 30 days":  timedelta(days=30),
    "All dates":     None,
}

# ---- Constant Contact credentials (hard-coded for this prototype)
CC_ACCESS_TOKEN = (
    "eyJraWQiOiJqRFZQN1F2eHdsaXdZV09sWFpVUDBOUlQ3aml6dlZQaXBwVWRUcFJselZZIiwiYWxnIjoiUlMyNTYifQ.eyJ2ZXIiOjEsImp0aSI6IkFULkRfVVlQUXREdFVmY2ZhSjVHV2x1bGwxME52ZG5la2JNdDZIbkJ1XzV0dDQub2FyMXFzcXA3aldTaG83cEMwaDciLCJpc3MiOiJodHRwczovL2lkZW50aXR5LmNvbnN0YW50Y29udGFjdC5jb20vb2F1dGgyL2F1czFsbTNyeTltRjd4MkphMGg4IiwiYXVkIjoiaHR0cHM6Ly9hcGkuY2MuZW1haWwvdjMiLCJpYXQiOjE3NDkxMzk5OTUsImV4cCI6MTc0OTIyNjM5NSwiY2lkIjoiNjJiNjlhZWQtZGM2YS00ZGI0LTllOGQtYmY4NTg2MDdhNDk2IiwidWlkIjoiMDB1MjJsZTkwYTFpWjdhbkswaDgiLCJzY3AiOlsiYWNjb3VudF9yZWFkIiwib2ZmbGluZV9hY2Nlc3MiLCJjYW1wYWlnbl9kYXRhIiwiY29udGFjdF9kYXRhIl0sImF1dGhfdGltZSI6MTc0OTEyNDkzMywic3ViIjoiYW5raXRiaGF0aWEuZW1haWxAZ21haWwuY29tIiwicGxhdGZvcm1fdXNlcl9pZCI6IjA2NmUxNDg5LWRhYmItNGE3ZC05NzE5LWYxZTViYTlhNjgxMiJ9.pejxCCepo-_VZ-wvUi5_0VSvDWAQpI6o1ZBLxj9Fa8uZbbxUGfD_IRkSItMrIcihDtMrLofoPkoljm6eRbNZj8msRK-oEpbhp2p7v70jpvXYq11snQXYyAqrhdnq_rEceolFr6xV-M0rCiMTvlszwgTdHfhlaf5sdspTo2Zmvlu7Ab_oXReQ-TPZJg_wyVuV20shaz0jWJi4Nv1xQXm3b1X7TP5Lq8mA5AaZ1FgoE2xqsQs2ldfDCRWoAAHTdJqofEEutixXIv0cjSfHmIoI7pJODJzC7yMX0_jYiodV1JMa4WtI53zocOWkTqQUSJI50uwHNscTeg8OXUrx1YiTMg"
)
CC_LIST_ID        = "d15a9376-4088-11f0-ac60-fa163e7ee3ac"
CC_FROM_EMAIL     = "ankitbhatia.email@gmail.com"
CC_REPLY_TO_EMAIL = "ankitbhatia.email@gmail.com"


def rel_date(path: pathlib.Path) -> datetime:
    m = DATE_RE.search(path.name)
    return datetime.strptime(m.group(1), "%Y%m%d") if m else datetime.utcfromtimestamp(path.stat().st_mtime)


def split_dir(dir_name: str) -> tuple[str, str, str]:
    src, code = dir_name.split("_", 1)
    region  = REGION_MAP.get(src, src)
    pretty  = DISPLAY_MAP.get(code, code)
    return region, code, pretty


def gpt_summary(ind_name: str, raw: str) -> tuple[str, str]:
    prompt = (
        "You are a macroeconomic analyst.\n\n"
        f"Indicator: {ind_name}\n\n"
        "Here is the raw press-release content (including tables):\n"
        "----\n" + raw[:120_000] + "\n----\n\n"
        "Return only:\n"
        "• First line: ≤10-word op-ed-style headline.\n"
        "• Blank line.\n"
        "• Then a Bureau-of-Labor-Statistics-style brief (3 very short paragraphs, "
        "no source citations, maximum 150 words).\n"
        "  – Para1: MoM / YoY results, vs. previous month.\n"
        "  – Para2: Very briefly, discuss key Upward and downward drivers.\n"
        "  – Para3: Very briefly, discuss any other highly relevant or significant trends.\n"
        "Do **not** invent numbers – rely only on supplied text."
    )
    res = client.chat.completions.create(
        model="gpt-4.1-mini-2025-04-14",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=1500,
    )
    lines = res.choices[0].message.content.strip().splitlines()
    if not lines:
        return "No headline.", "GPT returned empty response."
    return lines[0], " ".join(l.strip() for l in lines[2:] if l.strip())


# ── BUILD LATEST PATH PER INDICATOR ─────────────────────────────────────────
paths = [pathlib.Path(p) for p in glob.glob(f"{DATA_ROOT}/*/*.txt")]
if not paths:
    st.warning("No .txt files in ./releases — run scrape_agent first.")
    st.stop()

latest_path = {}
for p in paths:
    d = p.parent.name
    if (d not in latest_path) or (rel_date(p) > rel_date(latest_path[d])):
        latest_path[d] = p


# ── SESSION STATE INIT ─────────────────────────────────────────────────────
if "filtered_files" not in st.session_state:
    st.session_state.filtered_files: list[pathlib.Path] = []
if "filters_applied" not in st.session_state:
    st.session_state.filters_applied: bool = False
if "go_clicked" not in st.session_state:
    st.session_state.go_clicked: bool = False


# ── SIDEBAR FILTERS ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Filters")

    regions = sorted({split_dir(d)[0] for d in latest_path})
    sel_regions = st.multiselect("Region / Country", regions, [])

    # indicator list depends on region choice
    ind_opts = []
    for d in latest_path:
        reg, code, pretty = split_dir(d)
        if not sel_regions or reg in sel_regions:
            ind_opts.append(f"{reg} – {pretty}")
    sel_inds = st.multiselect("Indicator", sorted(ind_opts), [])

    date_choice = st.selectbox("Show releases from…", list(DATE_WINDOWS), index=1)
    newest_first = st.checkbox("Newest first", value=True)

    # --- Apply Filters ---
    if st.button("Apply Filters"):
        filtered = []
        delta = DATE_WINDOWS[date_choice]

        for d, p in latest_path.items():
            reg, code, pretty = split_dir(d)
            label = f"{reg} – {pretty}"

            if sel_regions and reg not in sel_regions:
                continue
            if sel_inds and label not in sel_inds:
                continue
            if delta and (datetime.utcnow() - rel_date(p) > delta):
                continue
            filtered.append(p)

        filtered.sort(key=lambda x: rel_date(x), reverse=newest_first)

        st.session_state.filtered_files = filtered
        st.session_state.filters_applied = True
        st.session_state.go_clicked = False

    # --- Show matches & Go ---
    if st.session_state.filters_applied:
        if st.session_state.filtered_files:
            st.markdown("---")
            st.markdown("**Matching releases:**")
            for p in st.session_state.filtered_files:
                r, _, pr = split_dir(p.parent.name)
                st.markdown(f"- {r} – {pr} ({rel_date(p).strftime('%Y-%m-%d')})")
            if st.button("Go"):
                st.session_state.go_clicked = True
        else:
            st.info("No releases match the selection.")


# ── STOP CONDITIONS ─────────────────────────────────────────────────────────
if not (st.session_state.filters_applied and st.session_state.go_clicked):
    st.stop()

if not st.session_state.filtered_files:
    st.warning("Nothing to display.")
    st.stop()


# ── GENERATE & DISPLAY STACKED CARDS ────────────────────────────────────────
email_blocks: list[str] = []                 # ← NEW: collect HTML snippets for email

for p in st.session_state.filtered_files:
    region, _, pretty = split_dir(p.parent.name)
    indicator_name = f"{region} – {pretty}"
    raw_text = p.read_text(encoding="utf-8", errors="ignore")

    head, brief = gpt_summary(indicator_name, raw_text)

    st.markdown(f"#### {indicator_name}")
    st.markdown(
        f"<div class='mpp-card'><h3>{head}</h3><p>{brief}</p></div>",
        unsafe_allow_html=True,
    )

    # Collect for email
    email_blocks.append(f"<h2>{head}</h2><p>{brief}</p>")

st.success("Dashboard built ✔")


# ── SEND-TO-SUBSCRIBERS BUTTON ────────────────────────────────────────────
if st.button("Send to Subscribers"):

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
        v_headers = {"Authorization": f"Bearer {CC_ACCESS_TOKEN}"}

        try:
            v_resp = requests.get(v_url, headers=v_headers, timeout=10)
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
    payload = {
        "name": "MPP Brief",
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
    url = "https://api.cc.email/v3/emails"
    headers = {
        "Authorization": f"Bearer {CC_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
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
