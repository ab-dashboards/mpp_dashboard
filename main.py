"""Convenience CLI for running MPP dashboard pipeline stages."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / "agents"

STAGE_TO_SCRIPT = {
    "rss": AGENTS / "rss_agent.py",
    "download": AGENTS / "download_agent.py",
    "scrape": AGENTS / "scrape_agent.py",
    "earnings": AGENTS / "earnings_agent.py",
    "summary": AGENTS / "summary_agent.py",
    "store": AGENTS / "store_agent.py",
    "fred": AGENTS / "fred_calendar_agent.py",
}


def run_script(path: Path) -> None:
    subprocess.run([sys.executable, str(path)], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MPP pipeline stages")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_parser = sub.add_parser("run", help="Run one stage or all stages")
    run_parser.add_argument(
        "stage",
        choices=[*STAGE_TO_SCRIPT.keys(), "all"],
        help="Stage to run",
    )

    args = parser.parse_args()

    if args.cmd == "run":
        if args.stage == "all":
            for stage in ("rss", "download", "scrape", "earnings", "store", "fred"):
                run_script(STAGE_TO_SCRIPT[stage])
            return
        run_script(STAGE_TO_SCRIPT[args.stage])


if __name__ == "__main__":
    main()
