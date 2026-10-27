"""Read-only provider/evaluator evidence. No broker orders are placed.

Run in the app directory at a check: python tools/verify_check_runtime_20261027.py
Credentials come from the same environment / .streamlit/secrets.toml / vault as
the app. Never put a key in command-line arguments or a saved evidence report.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system", default="cycle92", help="Standing monthly system, e.g. cycle92")
    parser.add_argument("--check-mmt", help="Optional exact check in Myanmar time: YYYY-MM-DD HH:MM")
    parser.add_argument("--report", help="Optional output JSON path")
    args = parser.parse_args()
    from core import signal_mode as mode
    from core.check_candle_runtime import fetch_check_frames
    from core.twelve_data_key_pool import TwelveDataKeyPool
    from ui.field3_multisymbol_regime_summary_20260722 import (
        _CYCLE22_PANEL_SYMBOLS, _c22_signals_to_display, _latest_entry_window_utc)
    mode.set_active_system(args.system)
    now = pd.Timestamp.now(tz="UTC")
    if args.check_mmt:
        entry = pd.Timestamp(args.check_mmt).tz_localize("Asia/Rangoon").tz_convert("UTC").tz_localize(None)
    else:
        entry = _latest_entry_window_utc(now)
    if entry is None or entry.hour not in mode.active_check_hours() or entry.minute or entry.weekday() >= 5:
        parser.error("check-mmt must be a weekday entry window of the chosen system")
    if entry.tz_localize("UTC") > now:
        parser.error("the check is in the future; run this command when the check starts")
    state = {}
    if not TwelveDataKeyPool(state).has_available_key():
        print(json.dumps({"status": "NO_KEY", "live_check_proven": False,
                          "message": "Configure Twelve Data in Streamlit Secrets or the environment first."}))
        return 2
    started = time.monotonic()
    frames, latest, diag = fetch_check_frames(state, _CYCLE22_PANEL_SYMBOLS,
                                             [entry-pd.Timedelta(hours=1), entry])
    entries = pd.DataFrame()
    status = "INCOMPLETE_DATA"
    if diag["ready"] == 20:
        try:
            entries = mode._evaluate_and_select_for(args.system, frames, entry+pd.Timedelta(minutes=30))
            status = "FEATURE_DATA_INCOMPLETE" if entries.attrs.get("status") else "CALCULATED"
        except Exception as exc:
            status = "CALCULATION_ERROR_"+type(exc).__name__
    finished = pd.Timestamp.now(tz="UTC")
    delay = (finished-entry.tz_localize("UTC")).total_seconds()
    evidence = dict(system=args.system, check_mmt=str(entry.tz_localize("UTC").tz_convert("Asia/Rangoon")),
                    observed_at_utc=finished.isoformat(), elapsed_seconds=round(time.monotonic()-started, 3),
                    seconds_after_check=round(delay, 3), status=status,
                    within_check_minute=0 <= delay < 60,
                    provider_evaluation_within_check_minute=status == "CALCULATED" and 0 <= delay < 60,
                    deployed_ui_verified=False,
                    live_check_proven=False,  # CLI cannot verify the deployed browser UI.
                    diagnostics=diag, signals=_c22_signals_to_display(entries).to_dict("records"))
    text = json.dumps(evidence, indent=2, default=str)
    print(text)
    if args.report:
        Path(args.report).write_text(text+"\n", encoding="utf-8")
    return 0 if status == "CALCULATED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
