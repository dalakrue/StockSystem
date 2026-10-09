#!/usr/bin/env python3
"""Fast first load of Twelve Data history into the local candle store.

Populates the canonical 5000-row per-symbol cache and the SQLite candle
repository for a symbol universe in one run:

    python scripts/fast_first_load_twelvedata.py --timeframe H1

Twelve Data keys are read from the environment (TWELVE_DATA_API_KEY_1 ..
TWELVE_DATA_API_KEY_8) or from the app's saved secrets/state. Run from the
app root so ``core`` imports resolve.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

DEFAULT_SYMBOLS = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "NZDUSD", "USDCAD",
    "EURGBP", "EURJPY", "GBPJPY", "EURCHF", "AUDJPY", "EURAUD", "EURCAD",
    "AUDCAD", "AUDNZD", "NZDJPY", "CADJPY", "CHFJPY", "GBPCAD",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fast first load of Twelve Data history.")
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                        help="Comma-separated symbols (default: 20 majors).")
    parser.add_argument("--timeframe", default="H1", help="Candle timeframe (default: H1).")
    parser.add_argument("--bars", type=int, default=5000, help="Canonical rows per symbol (default: 5000).")
    parser.add_argument("--db", default=str(APP_ROOT / "data" / "multi_symbol_field10_20260701.sqlite3"),
                        help="Candle repository SQLite path.")
    parser.add_argument("--run-id", default="", help="Run label stored with the candles.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    if not symbols:
        print("No symbols given.", file=sys.stderr)
        return 2

    from core.data.candle_repository import CandleRepository, normalize_frame
    from core.data.multi_symbol_scheduler import MultiSymbolScheduler

    state: dict = {"enable_twelve_multi_key_loading": True}
    for index in range(1, 9):
        for env_name in (f"TWELVE_DATA_API_KEY_{index}", f"TWELVE_API_KEY_{index}"):
            value = os.environ.get(env_name, "").strip()
            if value:
                state[f"twelve_api_key_{index}"] = value
                break

    run_id = args.run_id or f"fast-first-load-{int(time.time())}"
    scheduler = MultiSymbolScheduler(db_path=args.db)
    print(f"Loading {len(symbols)} symbols x {args.timeframe} ({args.bars} rows canonical) ...", flush=True)
    started = time.time()
    report = scheduler.run(symbols=symbols, timeframe=args.timeframe, state=state,
                           bars=args.bars, run_id=run_id, force_live=True)

    # Persist every returned frame through the bulk upsert path (idempotent;
    # the orchestrator may already have stored these rows).
    repo = CandleRepository(args.db)
    totals = {"inserted": 0, "rejected": 0, "duplicates": 0}
    print(f"{'SYMBOL':<10}{'ROWS':>8}{'PROVIDER':>22}  STATUS")
    for symbol in symbols:
        payload = (report.get("results") or {}).get(symbol) or {}
        frame = payload.get("frame")
        rows = len(frame) if frame is not None and hasattr(frame, "__len__") else 0
        status = "OK" if payload.get("ok") else str(payload.get("status") or "FAILED")
        print(f"{symbol:<10}{rows:>8}{str(payload.get('provider') or ''):>22}  {status}")
        if frame is not None and rows:
            norm = normalize_frame(frame, symbol=symbol, timeframe=args.timeframe,
                                   provider=str(payload.get("provider") or "TWELVE_DATA"),
                                   provider_symbol=str(payload.get("provider_symbol") or symbol),
                                   source_status="LIVE_PRIMARY", run_id=run_id)
            stats = repo.upsert(norm, run_id=run_id)
            for key in totals:
                totals[key] += stats.get(key, 0)

    elapsed = time.time() - started
    print(f"\nDone in {elapsed:.1f}s. upsert totals={totals} "
          f"unresolved={report.get('unresolved_symbols')} deferred={report.get('deferred_symbols')}")
    return 0 if report.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
