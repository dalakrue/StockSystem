"""Immutable forecast-origin ledger with independent H1/H3/H6 settlement.

This is a new shadow-only table.  It reads project data but never rewrites Field 1
or protected canonical history.  Origin predictions are inserted with INSERT OR
IGNORE so old means/bands/weights cannot be overwritten by future reruns.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping
from datetime import timezone
import json, math, sqlite3, hashlib
import pandas as pd

from core.probabilistic_evaluation_20260624 import true_crps

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "quant_app.sqlite3"
VERSION = "forecast-origin-ledger-20260624-v1"
HORIZONS = {"H1": 1, "H3": 3, "H6": 6}


def _iso(x: Any) -> str | None:
    try:
        ts = pd.Timestamp(x)
        if pd.isna(ts): return None
        if ts.tzinfo is None: ts = ts.tz_localize("UTC")
        else: ts = ts.tz_convert("UTC")
        return ts.isoformat()
    except Exception:
        return None


def _json(x: Any) -> str:
    return json.dumps(x if x is not None else None, ensure_ascii=False, default=str)


def _float(x: Any) -> float | None:
    try:
        v = float(x); return v if math.isfinite(v) else None
    except Exception: return None


def forecast_id(symbol: str, timeframe: str, origin_time: Any, horizon: str, run_id: Any = "") -> str:
    base = f"{symbol}|{timeframe}|{_iso(origin_time) or origin_time}|{horizon}|{run_id}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:32]


class ForecastOriginLedger:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS forecast_origin_ledger_20260624 (
                forecast_id TEXT PRIMARY KEY,
                run_id TEXT, symbol TEXT, timeframe TEXT,
                origin_time TEXT, origin_broker_time TEXT, horizon TEXT, maturity_time TEXT,
                origin_price REAL, origin_mean REAL, origin_median REAL, origin_std REAL,
                origin_lower REAL, origin_upper REAL, origin_quantiles TEXT, origin_samples TEXT,
                origin_model_weights TEXT, origin_active_model_set TEXT,
                origin_regime TEXT, origin_regime_probability REAL, origin_session TEXT,
                origin_volatility_bucket TEXT, matured_actual REAL,
                settlement_status TEXT DEFAULT 'PENDING', settled_at TEXT,
                absolute_error REAL, squared_error REAL, direction_hit INTEGER,
                interval_hit INTEGER, crps REAL, crps_method TEXT,
                evaluation_version TEXT, inserted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_forecast_origin_maturity_20260624 ON forecast_origin_ledger_20260624(symbol,timeframe,horizon,maturity_time,settlement_status)")

    def record_origin_rows(self, rows: Iterable[Mapping[str, Any]]) -> int:
        inserted = 0
        sql = """
        INSERT OR IGNORE INTO forecast_origin_ledger_20260624 (
            forecast_id,run_id,symbol,timeframe,origin_time,origin_broker_time,horizon,maturity_time,
            origin_price,origin_mean,origin_median,origin_std,origin_lower,origin_upper,origin_quantiles,origin_samples,
            origin_model_weights,origin_active_model_set,origin_regime,origin_regime_probability,origin_session,origin_volatility_bucket,
            settlement_status,evaluation_version
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """
        with self._connect() as conn:
            for r in rows:
                horizon = str(r.get("horizon") or "H1").upper()
                fid = str(r.get("forecast_id") or forecast_id(str(r.get("symbol","EURUSD")), str(r.get("timeframe","H1")), r.get("origin_time"), horizon, r.get("run_id","")))
                values = (fid, str(r.get("run_id") or ""), str(r.get("symbol") or "EURUSD"), str(r.get("timeframe") or "H1"), _iso(r.get("origin_time")), str(r.get("origin_broker_time") or ""), horizon, _iso(r.get("maturity_time")), _float(r.get("origin_price")), _float(r.get("origin_mean")), _float(r.get("origin_median")), _float(r.get("origin_std")), _float(r.get("origin_lower")), _float(r.get("origin_upper")), _json(r.get("origin_quantiles")), _json(r.get("origin_samples")), _json(r.get("origin_model_weights")), _json(r.get("origin_active_model_set")), str(r.get("origin_regime") or ""), _float(r.get("origin_regime_probability")), str(r.get("origin_session") or ""), str(r.get("origin_volatility_bucket") or ""), "PENDING", VERSION)
                cur = conn.execute(sql, values); inserted += max(0, cur.rowcount)
        return inserted

    def settle_from_actuals(self, actuals: pd.DataFrame, *, symbol: str = "EURUSD", timeframe: str = "H1", actual_time_col: str = "time", actual_price_col: str = "close", now: Any | None = None) -> dict[str, Any]:
        if not isinstance(actuals, pd.DataFrame) or actuals.empty or actual_time_col not in actuals or actual_price_col not in actuals:
            return {"ok": False, "settled_rows": 0, "reason": "NO_ACTUALS"}
        af = actuals[[actual_time_col, actual_price_col]].copy()
        af["_time"] = pd.to_datetime(af[actual_time_col], utc=True, errors="coerce")
        af["_price"] = pd.to_numeric(af[actual_price_col], errors="coerce")
        af = af.dropna(subset=["_time", "_price"]).drop_duplicates("_time").sort_values("_time")
        current = pd.Timestamp(now, tz="UTC") if now is not None else af["_time"].max()
        settled = 0
        with self._connect() as conn:
            pending = conn.execute("SELECT * FROM forecast_origin_ledger_20260624 WHERE symbol=? AND timeframe=? AND settlement_status='PENDING'", (symbol, timeframe)).fetchall()
            for row in pending:
                maturity = pd.Timestamp(row["maturity_time"])
                if maturity.tzinfo is None: maturity = maturity.tz_localize("UTC")
                if maturity > current:
                    continue
                match = af[af["_time"] >= maturity].head(1)
                if match.empty:
                    continue
                actual = float(match["_price"].iloc[0])
                mean = _float(row["origin_mean"] if row["origin_mean"] is not None else row["origin_median"])
                origin_price = _float(row["origin_price"])
                abs_err = abs(mean - actual) if mean is not None else None
                sq_err = (mean - actual) ** 2 if mean is not None else None
                direction_hit = None
                if mean is not None and origin_price is not None:
                    direction_hit = int(math.copysign(1, mean - origin_price) == math.copysign(1, actual - origin_price)) if mean != origin_price and actual != origin_price else int(mean == actual)
                lower = _float(row["origin_lower"]); upper = _float(row["origin_upper"])
                interval_hit = int(lower <= actual <= upper) if lower is not None and upper is not None else None
                try: samples = json.loads(row["origin_samples"] or "[]")
                except Exception: samples = []
                try: quantiles = json.loads(row["origin_quantiles"] or "{}")
                except Exception: quantiles = {}
                crps, method = true_crps(mean=row["origin_mean"], std=row["origin_std"], samples=samples, quantiles=quantiles, actual=actual)
                conn.execute("""
                UPDATE forecast_origin_ledger_20260624
                SET matured_actual=?, settlement_status='FULLY_SETTLED', settled_at=CURRENT_TIMESTAMP,
                    absolute_error=?, squared_error=?, direction_hit=?, interval_hit=?, crps=?, crps_method=?, evaluation_version=?
                WHERE forecast_id=? AND settlement_status='PENDING'
                """, (actual, abs_err, sq_err, direction_hit, interval_hit, crps, method, VERSION, row["forecast_id"]))
                settled += 1
        return {"ok": True, "settled_rows": int(settled), "evaluation_version": VERSION}

    def read(self, where: str = "1=1", params: tuple[Any, ...] = ()) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(f"SELECT * FROM forecast_origin_ledger_20260624 WHERE {where}", conn, params=params)

    def run_settlement_status(self, run_id: str) -> str:
        df = self.read("run_id=?", (run_id,))
        if df.empty: return "PENDING"
        statuses = set(df["settlement_status"].astype(str))
        if statuses == {"FULLY_SETTLED"}: return "FULLY_SETTLED"
        if "FULLY_SETTLED" in statuses: return "PARTIALLY_SETTLED"
        return "PENDING"


__all__ = ["ForecastOriginLedger", "forecast_id", "VERSION", "HORIZONS"]
