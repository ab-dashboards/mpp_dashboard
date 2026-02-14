# MPP Dashboard

A production-oriented data pipeline and Streamlit dashboard for curating macroeconomic releases and market-focused flash briefs.

## What this repository does

- Pulls macro and market feeds (RSS/Atom and crawler-based sources).
- Queues and downloads source documents.
- Converts raw HTML releases to normalized plain text.
- Extracts Nasdaq earnings-preview tickers and text sidecars.
- Builds a Streamlit dashboard that summarizes releases with LLM-generated briefs.

## Repository structure

- `agents/` – pipeline and UI scripts.
- `agents/parsers/` – source-specific parser modules.
- `data/` – local working files (queue/raw/calendar), generated at runtime.
- `logs/` – runtime logs, generated locally.
- `releases/` – generated plain-text release outputs.
- `tests/` – unit tests for deterministic helper logic.

## Quickstart

### 1) Create environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Configure secrets

Copy `.env.example` to `.env` and set real values.

### 3) Run the pipeline

```bash
python main.py run rss
python main.py run download
python main.py run scrape
python main.py run earnings
python main.py run summary
```

Or run everything except the Streamlit UI:

```bash
python main.py run all
```

## Environment variables

See `.env.example` for the full list.

Core variables:
- `OPENAI_API_KEY`
- `FRED_API_KEY`
- `CC_ACCESS_TOKEN`
- `CC_REFRESH_TOKEN`
- `CC_CLIENT_ID`
- `CC_CLIENT_SECRET`
- `CC_LIST_ID`
- `CC_FROM_EMAIL`
- `CC_REPLY_TO_EMAIL`

Optional:
- `NGROK_AUTH_TOKEN`
- `NGROK_PATH`
- `NGROK_PORT`

## Development

```bash
pytest -q
ruff check .
```

## Security

- Never commit real secrets.
- Use `.env` for local development only.
- See `SECURITY.md` for disclosure and secret-rotation guidance.

## License

MIT License. See `LICENSE`.
