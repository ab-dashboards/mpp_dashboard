"""
store_agent.py
Merges parsed_rows.csv into data/macro.csv (master table) and
deduplicates on (release_id, series).
"""

import pandas as pd, datetime as dt, logging
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARSED_CSV = ROOT / "data" / "parsed_rows.csv"
MACRO_CSV  = ROOT / "data" / "macro.csv"
LOG_DIR    = ROOT / "logs"; LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(filename=LOG_DIR / f"store_{dt.date.today()}.log",
                    level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

def main():
    if not PARSED_CSV.exists():
        logging.info("No parsed rows yet.")
        return

    df_new = pd.read_csv(PARSED_CSV)
    df_new["ingest_ts"] = dt.datetime.utcnow().isoformat(timespec='seconds')

    if MACRO_CSV.exists():
        df_old = pd.read_csv(MACRO_CSV)
        df = pd.concat([df_old, df_new], ignore_index=True)
        df = df.drop_duplicates(subset=["release_id", "series"], keep="last")
    else:
        df = df_new

    df.to_csv(MACRO_CSV, index=False)
    logging.info("macro.csv now has %d rows", len(df))

    # clear parsed file
    PARSED_CSV.unlink()

if __name__ == "__main__":
    main()
