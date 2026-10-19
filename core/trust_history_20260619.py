# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Immutable settled-forecast ledger and trust validation for EURUSD H1.

The store is additive and shares the existing SQLite database. Original
forecast fields are inserted once and are never overwritten. Settlement updates
only outcome fields after the target H1 candle is fully available.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from core.trust_config_20260619 import TRUST_CONFIG

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "quant_app.sqlite3"
_LOCK = threading.RLock()
SCHEMA_VERSION = "adx-trust-history-3.0.0"
CALCULATION_VERSION = "trust-validation-20260619-v1"
HORIZONS = (1, 2, 3, 6)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _text(value: Any, default: str = "") -> str:
    return default if value in (None, "") else str(value)


def _utc(value: Any) -> Optional[pd.Timestamp]:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    except Exception:
        return None


def _iso(value: Any) -> Optional[str]:
    ts = _utc(value)
    return ts.isoformat() if ts is not None else None


def _direction(value: Any) -> str:
    text = str(value or "").upper()
    if "BUY" in text or "BULL" in text or text == "UP":
        return "BUY"
    if "SELL" in text or "BEAR" in text or text == "DOWN":
        return "SELL"
    return "WAIT"


def _session(ts: pd.Timestamp) -> str:
    hour = int(ts.hour)
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 12:
        return "LONDON"
    if 12 <= hour < 16:
        return "LONDON_NY_OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "LATE_NY"


def normalize_completed_ohlc(frame: Any) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    data = frame.copy(deep=False)
    cmap = {str(c).strip().lower(): c for c in data.columns}
    tcol = next((cmap[x] for x in ("time", "timestamp", "datetime", "date") if x in cmap), None)
    cols: dict[str, Any] = {}
    for name in ("open", "high", "low", "close"):
        col = cmap.get(name) or cmap.get(name[0])
        if col is None:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        cols[name] = col
    idx = pd.to_datetime(data[tcol] if tcol is not None else data.index, utc=True, errors="coerce")
    out = pd.DataFrame(
        {name: pd.to_numeric(data[col], errors="coerce").to_numpy() for name, col in cols.items()},
        index=pd.DatetimeIndex(idx),
    )
    out = out.loc[~out.index.isna()].dropna().sort_index()
    out = out.loc[~out.index.duplicated(keep="last")]
    return out


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _forecast(canonical: Mapping[str, Any], horizon: int) -> Mapping[str, Any]:
    return _mapping(_mapping(_mapping(canonical.get("forecasts")).get("horizons")).get(f"{horizon}h"))


def _extract_quantiles(canonical: Mapping[str, Any], horizon: int, forecast: Mapping[str, Any]) -> dict[str, Optional[float]]:
    result = {"p10": None, "p25": None, "p50": None, "p75": None, "p90": None}
    for key in result:
        result[key] = _finite(forecast.get(key) or forecast.get(key.upper()), None)
    probabilistic = _mapping(canonical.get("probabilistic_projection"))
    candidates = probabilistic.get("horizons") or probabilistic.get("quantiles") or probabilistic.get("projection")
    if isinstance(candidates, Mapping):
        row = _mapping(candidates.get(f"{horizon}h") or candidates.get(str(horizon)) or candidates.get(horizon))
        for key in result:
            if result[key] is None:
                result[key] = _finite(row.get(key) or row.get(key.upper()), None)
    if result["p50"] is None:
        result["p50"] = _finite(forecast.get("point_forecast"), None)
    if result["p10"] is None:
        result["p10"] = _finite(forecast.get("lower_bound"), None)
    if result["p90"] is None:
        result["p90"] = _finite(forecast.get("upper_bound"), None)
    return result


def _signed_pips(origin: float, actual: float, direction: str) -> float:
    pip = float(TRUST_CONFIG["pip_size"])
    raw = (actual - origin) / pip
    return raw if direction == "BUY" else -raw if direction == "SELL" else -abs(raw)


def _safe_probability(value: Any) -> Optional[float]:
    v = _finite(value, None)
    if v is None:
        return None
    if v > 1.0:
        v /= 100.0
    return max(0.0, min(1.0, v))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class TrustHistoryStore:
    def __init__(self, db_path: Path | str | None = None) -> None:
        configured = os.environ.get("ADX_LEDGER_DB_PATH")
        self.db_path = Path(db_path or configured or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_error = ""
        self.initialize()

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=20, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=20000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _execute(self, sql: str, params: Sequence[Any] = (), *, fetch: bool = False, many: bool = False) -> Any:
        last: Optional[Exception] = None
        for attempt in range(5):
            try:
                with _LOCK, self.connection() as conn:
                    cur = conn.executemany(sql, params) if many else conn.execute(sql, tuple(params))
                    return [dict(row) for row in cur.fetchall()] if fetch else cur.rowcount
            except sqlite3.OperationalError as exc:
                last = exc
                if "locked" not in str(exc).lower() or attempt == 4:
                    raise
                import time
                time.sleep(0.12 * (attempt + 1))
        raise RuntimeError(str(last or "database operation failed"))

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS settled_forecast_ledger_v3 (
                calculation_id TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                forecast_origin_time TEXT NOT NULL,
                forecast_origin_price REAL,
                target_time TEXT NOT NULL,
                horizon INTEGER NOT NULL,
                session TEXT,
                d1_regime TEXT,
                h4_regime TEXT,
                h1_regime TEXT,
                regime_age REAL,
                regime_transition_risk REAL,
                full_metric_direction TEXT,
                final_decision TEXT,
                tradeability_status TEXT,
                raw_confidence REAL,
                calibrated_confidence REAL,
                raw_buy_probability REAL,
                raw_sell_probability REAL,
                raw_wait_probability REAL,
                calibrated_buy_probability REAL,
                calibrated_sell_probability REAL,
                calibrated_wait_probability REAL,
                required_probability_threshold REAL,
                expected_value_after_costs REAL,
                expected_favorable_movement REAL,
                expected_adverse_movement REAL,
                estimated_cost_pips REAL,
                predicted_close REAL,
                p10 REAL,
                p25 REAL,
                p50 REAL,
                p75 REAL,
                p90 REAL,
                lower_band REAL,
                upper_band REAL,
                actual_close REAL,
                absolute_error_pips REAL,
                squared_error REAL,
                direction_correct INTEGER,
                interval_hit INTEGER,
                maximum_favorable_excursion REAL,
                maximum_adverse_excursion REAL,
                tp_touched INTEGER,
                sl_touched INTEGER,
                selected_tp REAL,
                selected_sl REAL,
                main_reason TEXT,
                strongest_blocker TEXT,
                data_quality_status TEXT,
                drift_status TEXT,
                event_risk_status TEXT,
                priority REAL,
                knn_score REAL,
                greedy_rank REAL,
                model_agreement REAL,
                record_status TEXT NOT NULL DEFAULT 'PENDING',
                settlement_timestamp TEXT,
                created_at TEXT NOT NULL,
                source TEXT,
                schema_version TEXT NOT NULL,
                PRIMARY KEY(calculation_id, horizon)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS forecast_method_ledger_v3 (
                calculation_id TEXT NOT NULL,
                calculation_version TEXT NOT NULL,
                forecast_origin_time TEXT NOT NULL,
                target_time TEXT NOT NULL,
                horizon INTEGER NOT NULL,
                method TEXT NOT NULL,
                predicted_close REAL,
                predicted_direction TEXT,
                actual_close REAL,
                absolute_error REAL,
                squared_error REAL,
                directional_loss REAL,
                quantile_loss REAL,
                record_status TEXT NOT NULL DEFAULT 'PENDING',
                settlement_timestamp TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY(calculation_id, horizon, method)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trust_validation_snapshots_v3 (
                calculation_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                calculation_version TEXT,
                settled_sample_count INTEGER,
                trust_classification TEXT,
                summary_json TEXT NOT NULL,
                schema_version TEXT NOT NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_trust_origin ON settled_forecast_ledger_v3(forecast_origin_time)",
            "CREATE INDEX IF NOT EXISTS idx_trust_target ON settled_forecast_ledger_v3(target_time)",
            "CREATE INDEX IF NOT EXISTS idx_trust_horizon ON settled_forecast_ledger_v3(horizon)",
            "CREATE INDEX IF NOT EXISTS idx_trust_regime ON settled_forecast_ledger_v3(h1_regime,h4_regime,d1_regime)",
            "CREATE INDEX IF NOT EXISTS idx_trust_session ON settled_forecast_ledger_v3(session)",
            "CREATE INDEX IF NOT EXISTS idx_trust_calc ON settled_forecast_ledger_v3(calculation_id)",
            "CREATE INDEX IF NOT EXISTS idx_trust_status_target ON settled_forecast_ledger_v3(record_status,target_time)",
            "CREATE INDEX IF NOT EXISTS idx_method_status_target ON forecast_method_ledger_v3(record_status,target_time)",
        ]
        with _LOCK, self.connection() as conn:
            for statement in statements:
                conn.execute(statement)
        self._backfill_legacy_once()

    def _backfill_legacy_once(self) -> None:
        """Seed immutable history from the older ledger without changing it."""
        try:
            with _LOCK, self.connection() as conn:
                legacy = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='predictions'").fetchone()
                if not legacy:
                    return
                existing = conn.execute("SELECT COUNT(*) FROM settled_forecast_ledger_v3").fetchone()[0]
                if existing:
                    return
                rows = conn.execute(
                    """
                    SELECT r.run_id,r.calculation_version,r.created_at,r.latest_completed_candle_time,r.source,
                           p.horizon_hours,p.current_price,p.predicted_price,p.predicted_direction,
                           p.buy_probability_raw,p.sell_probability_raw,p.wait_probability_raw,
                           p.buy_probability_calibrated,p.sell_probability_calibrated,p.wait_probability_calibrated,
                           p.decision_threshold,p.expected_value,p.expected_gain,p.expected_loss,p.estimated_cost,
                           p.lower_bound,p.upper_bound,p.priority_score,p.knn_score,p.greedy_score,p.due_time,
                           o.actual_price,o.absolute_error,o.direction_correct,o.target_hit,o.stop_hit,
                           o.maximum_favourable_excursion,o.maximum_adverse_excursion,o.outcome_status,o.settled_at,
                           rs.major_regime,rs.regime_age_hours,rs.transition_probability_3h
                    FROM calculation_runs r
                    JOIN predictions p ON p.run_id=r.run_id
                    LEFT JOIN prediction_outcomes o ON o.run_id=p.run_id AND o.horizon_hours=p.horizon_hours
                    LEFT JOIN regime_snapshots rs ON rs.run_id=r.run_id
                    ORDER BY r.created_at ASC
                    """
                ).fetchall()
                insert = """
                    INSERT OR IGNORE INTO settled_forecast_ledger_v3(
                        calculation_id,calculation_version,forecast_origin_time,forecast_origin_price,target_time,horizon,
                        session,d1_regime,h4_regime,h1_regime,regime_age,regime_transition_risk,full_metric_direction,
                        final_decision,tradeability_status,raw_confidence,calibrated_confidence,raw_buy_probability,
                        raw_sell_probability,raw_wait_probability,calibrated_buy_probability,calibrated_sell_probability,
                        calibrated_wait_probability,required_probability_threshold,expected_value_after_costs,
                        expected_favorable_movement,expected_adverse_movement,estimated_cost_pips,predicted_close,
                        p10,p25,p50,p75,p90,lower_band,upper_band,actual_close,absolute_error_pips,squared_error,
                        direction_correct,interval_hit,maximum_favorable_excursion,maximum_adverse_excursion,tp_touched,
                        sl_touched,selected_tp,selected_sl,main_reason,strongest_blocker,data_quality_status,drift_status,
                        event_risk_status,priority,knn_score,greedy_rank,model_agreement,record_status,settlement_timestamp,
                        created_at,source,schema_version
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """
                payloads = []
                pip = float(TRUST_CONFIG["pip_size"])
                for row in rows:
                    d = dict(row)
                    origin = _utc(d.get("latest_completed_candle_time") or d.get("created_at"))
                    if origin is None:
                        continue
                    direction = _direction(d.get("predicted_direction"))
                    raw = d.get(f"{direction.lower()}_probability_raw") if direction in {"BUY", "SELL", "WAIT"} else None
                    cal = d.get(f"{direction.lower()}_probability_calibrated") if direction in {"BUY", "SELL", "WAIT"} else None
                    abs_pips = (_finite(d.get("absolute_error"), 0.0) or 0.0) / pip if d.get("absolute_error") is not None else None
                    status = str(d.get("outcome_status") or "PENDING").upper()
                    payloads.append((
                        d.get("run_id"), d.get("calculation_version") or "legacy", origin.isoformat(), d.get("current_price"),
                        _iso(d.get("due_time")) or (origin + pd.Timedelta(hours=int(d.get("horizon_hours") or 1))).isoformat(),
                        int(d.get("horizon_hours") or 1), _session(origin), None, None, d.get("major_regime"), d.get("regime_age_hours"),
                        d.get("transition_probability_3h"), direction, d.get("decision"), d.get("decision"), raw, cal,
                        d.get("buy_probability_raw"), d.get("sell_probability_raw"), d.get("wait_probability_raw"),
                        d.get("buy_probability_calibrated"), d.get("sell_probability_calibrated"), d.get("wait_probability_calibrated"),
                        d.get("decision_threshold"), d.get("expected_value"), d.get("expected_gain"), d.get("expected_loss"),
                        (_finite(d.get("estimated_cost"), 0.0) or 0.0) / pip, d.get("predicted_price"), d.get("lower_bound"), None,
                        d.get("predicted_price"), None, d.get("upper_bound"), d.get("lower_bound"), d.get("upper_bound"),
                        d.get("actual_price"), abs_pips, (abs_pips ** 2 if abs_pips is not None else None), d.get("direction_correct"),
                        int(bool(d.get("actual_price") is not None and d.get("lower_bound") is not None and d.get("upper_bound") is not None and d.get("lower_bound") <= d.get("actual_price") <= d.get("upper_bound"))),
                        d.get("maximum_favourable_excursion"), d.get("maximum_adverse_excursion"), d.get("target_hit"), d.get("stop_hit"),
                        None, None, "Migrated from prediction_ledger_20260617", "", "UNKNOWN", "UNKNOWN", "UNKNOWN", d.get("priority_score"),
                        d.get("knn_score"), d.get("greedy_score"), None, status if status in {"PENDING", "SETTLED", "INVALID", "EXCLUDED"} else "PENDING",
                        d.get("settled_at"), d.get("created_at") or _utc_now(), d.get("source"), SCHEMA_VERSION,
                    ))
                if payloads:
                    conn.executemany(insert, payloads)
        except Exception as exc:
            self.last_error = f"legacy backfill: {exc}"

    def settle_pending(self, ohlc: pd.DataFrame) -> Dict[str, Any]:
        frame = normalize_completed_ohlc(ohlc)
        if frame.empty:
            return {"ok": False, "settled": 0, "pending": 0, "message": "No completed OHLC rows"}
        latest = frame.index.max()
        rows = self._execute(
            "SELECT * FROM settled_forecast_ledger_v3 WHERE record_status='PENDING' ORDER BY target_time ASC",
            fetch=True,
        )
        settled = invalid = 0
        pip = float(TRUST_CONFIG["pip_size"])
        for row in rows:
            target = _utc(row.get("target_time"))
            origin_ts = _utc(row.get("forecast_origin_time"))
            if target is None or origin_ts is None:
                self._execute(
                    "UPDATE settled_forecast_ledger_v3 SET record_status='INVALID',settlement_timestamp=? WHERE calculation_id=? AND horizon=? AND record_status='PENDING'",
                    (_utc_now(), row.get("calculation_id"), int(row.get("horizon") or 1)),
                )
                invalid += 1
                continue
            if target > latest:
                continue
            eligible = frame.loc[frame.index >= target]
            if eligible.empty:
                continue
            actual_time = eligible.index[0]
            actual = float(eligible.iloc[0]["close"])
            origin_price = _finite(row.get("forecast_origin_price"), None)
            predicted = _finite(row.get("predicted_close"), None)
            if origin_price is None or predicted is None:
                self._execute(
                    "UPDATE settled_forecast_ledger_v3 SET record_status='INVALID',settlement_timestamp=? WHERE calculation_id=? AND horizon=? AND record_status='PENDING'",
                    (_utc_now(), row.get("calculation_id"), int(row.get("horizon") or 1)),
                )
                invalid += 1
                continue
            direction = _direction(row.get("full_metric_direction"))
            actual_direction = "BUY" if actual > origin_price else "SELL" if actual < origin_price else "WAIT"
            correct = int(direction == actual_direction)
            abs_pips = abs(actual - predicted) / pip
            segment = frame.loc[(frame.index > origin_ts) & (frame.index <= actual_time)]
            if segment.empty:
                segment = eligible.head(1)
            high = float(segment["high"].max())
            low = float(segment["low"].min())
            if direction == "BUY":
                mfe = max(0.0, (high - origin_price) / pip)
                mae = max(0.0, (origin_price - low) / pip)
            elif direction == "SELL":
                mfe = max(0.0, (origin_price - low) / pip)
                mae = max(0.0, (high - origin_price) / pip)
            else:
                mfe = 0.0
                mae = max(abs(high - origin_price), abs(origin_price - low)) / pip
            lower = _finite(row.get("lower_band"), None)
            upper = _finite(row.get("upper_band"), None)
            interval_hit = int(lower is not None and upper is not None and lower <= actual <= upper)
            tp = _finite(row.get("selected_tp"), None)
            sl = _finite(row.get("selected_sl"), None)
            tp_hit = int(tp is not None and ((direction == "BUY" and high >= tp) or (direction == "SELL" and low <= tp)))
            sl_hit = int(sl is not None and ((direction == "BUY" and low <= sl) or (direction == "SELL" and high >= sl)))
            self._execute(
                """
                UPDATE settled_forecast_ledger_v3 SET actual_close=?,absolute_error_pips=?,squared_error=?,direction_correct=?,
                    interval_hit=?,maximum_favorable_excursion=?,maximum_adverse_excursion=?,tp_touched=?,sl_touched=?,
                    record_status='SETTLED',settlement_timestamp=?
                WHERE calculation_id=? AND horizon=? AND record_status='PENDING'
                """,
                (actual, abs_pips, abs_pips ** 2, correct, interval_hit, mfe, mae, tp_hit, sl_hit, _utc_now(), row.get("calculation_id"), int(row.get("horizon") or 1)),
            )
            self._execute(
                """
                UPDATE forecast_method_ledger_v3 SET actual_close=?,absolute_error=ABS(predicted_close-?),
                    squared_error=(predicted_close-?)*(predicted_close-?),
                    directional_loss=CASE WHEN predicted_direction=(CASE WHEN ?>? THEN 'BUY' WHEN ?<? THEN 'SELL' ELSE 'WAIT' END) THEN 0 ELSE 1 END,
                    record_status='SETTLED',settlement_timestamp=?
                WHERE calculation_id=? AND horizon=? AND record_status='PENDING'
                """,
                (actual, actual, actual, actual, actual, origin_price, actual, origin_price, _utc_now(), row.get("calculation_id"), int(row.get("horizon") or 1)),
            )
            settled += 1
        return {"ok": True, "settled": settled, "invalid": invalid, "pending": max(0, len(rows) - settled - invalid), "latest_completed": latest.isoformat()}

    def _method_forecasts(self, canonical: Mapping[str, Any], ohlc: pd.DataFrame, horizon: int, point: Optional[float], origin: float) -> dict[str, Optional[float]]:
        frame = normalize_completed_ohlc(ohlc)
        close = frame["close"] if not frame.empty else pd.Series(dtype=float)
        returns = close.diff()
        recent_drift = float(returns.tail(12).median()) if len(returns.dropna()) else 0.0
        ewma_drift = float(returns.ewm(span=12, adjust=False).mean().iloc[-1]) if len(returns.dropna()) else 0.0
        session_drift = recent_drift
        if not frame.empty:
            sessions = pd.Series([_session(ts) for ts in frame.index], index=frame.index)
            current_session = _session(frame.index[-1])
            session_moves = close.diff().loc[sessions.eq(current_session)].dropna().tail(80)
            if len(session_moves):
                session_drift = float(session_moves.median())
        full_metric_row = _mapping(canonical.get("full_metric_current_row"))
        fm_point = _finite(
            full_metric_row.get(f"H+{horizon} Predicted Close")
            or full_metric_row.get("Predicted Close")
            or full_metric_row.get("Prediction"),
            None,
        )
        return {
            "FULL_METRIC_FORECAST": fm_point,
            "POWERBI_COMBINED_PATH": point,
            "LAST_CLOSE": origin,
            "RECENT_DRIFT": origin + recent_drift * horizon,
            "SESSION_BASELINE": origin + session_drift * horizon,
            "LIGHTWEIGHT_CHALLENGER": origin + ewma_drift * horizon,
        }

    def record_forecasts(self, canonical: Mapping[str, Any], ohlc: pd.DataFrame) -> Dict[str, Any]:
        calc_id = _text(canonical.get("canonical_calculation_id") or canonical.get("run_id"))
        if not calc_id:
            return {"ok": False, "inserted": 0, "message": "Missing calculation ID"}
        created = _utc(canonical.get("created_at")) or pd.Timestamp.now(tz="UTC")
        origin_time = _utc(canonical.get("latest_completed_candle_time")) or created.floor("h")
        market = _mapping(canonical.get("market"))
        origin_price = _finite(canonical.get("last_close") or market.get("current_price"), None)
        if origin_price is None:
            return {"ok": False, "inserted": 0, "message": "Missing forecast origin price"}
        final = _mapping(canonical.get("final_decision"))
        regime = _mapping(canonical.get("regime"))
        data_quality = _mapping(canonical.get("data_quality"))
        drift = _mapping(canonical.get("drift"))
        nlp = _mapping(canonical.get("nlp"))
        priority = _mapping(canonical.get("priority"))
        authority_direction = _direction(final.get("directional_market_view") or canonical.get("full_metric_direction"))
        calculation_version = _text(canonical.get("calculation_version"), "unknown")
        h1_regime = _text(regime.get("major_regime") or canonical.get("current_major_regime"), "UNKNOWN")
        h4_regime = _text(regime.get("middle_standard_regime"), h1_regime)
        d1_regime = _text(regime.get("higher_standard_regime"), h4_regime)
        selected_tp = _finite(canonical.get("selected_tp") or _mapping(canonical.get("risk")).get("selected_tp"), None)
        selected_sl = _finite(canonical.get("selected_sl") or _mapping(canonical.get("risk")).get("selected_sl"), None)
        cost_pips = _finite(_mapping(canonical.get("risk")).get("estimated_cost"), None)
        pip = float(TRUST_CONFIG["pip_size"])
        if cost_pips is not None and abs(cost_pips) < 0.05:
            cost_pips = abs(cost_pips) / pip
        if cost_pips is None:
            cost_pips = float(TRUST_CONFIG["default_cost_pips"]) + float(TRUST_CONFIG["safety_buffer_pips"])
        inserted = methods_inserted = 0
        for horizon in HORIZONS:
            forecast = _forecast(canonical, horizon)
            if not forecast:
                continue
            target = _utc(forecast.get("due_time")) or origin_time + pd.Timedelta(hours=horizon)
            point = _finite(forecast.get("point_forecast"), None)
            quantiles = _extract_quantiles(canonical, horizon, forecast)
            direction = _direction(forecast.get("direction") or authority_direction)
            raw = _safe_probability(forecast.get(f"{direction.lower()}_probability_raw"))
            calibrated = _safe_probability(forecast.get(f"{direction.lower()}_probability_calibrated"))
            blocker_list = list(forecast.get("blocking_reasons") or final.get("blocking_reasons") or [])
            values = (
                calc_id, calculation_version, origin_time.isoformat(), origin_price, target.isoformat(), horizon,
                _session(origin_time), d1_regime, h4_regime, h1_regime, _finite(regime.get("age_hours"), None),
                _safe_probability(regime.get("transition_probability_3h") or regime.get("transition_probability_1h")),
                authority_direction, _text(final.get("final_decision"), "WAIT"), _text(final.get("tradeability_decision"), "WAIT"),
                raw, calibrated, _safe_probability(forecast.get("buy_probability_raw")), _safe_probability(forecast.get("sell_probability_raw")),
                _safe_probability(forecast.get("wait_probability_raw")), _safe_probability(forecast.get("buy_probability_calibrated")),
                _safe_probability(forecast.get("sell_probability_calibrated")), _safe_probability(forecast.get("wait_probability_calibrated")),
                _safe_probability(forecast.get("threshold")), _finite(forecast.get("expected_value"), None),
                _finite(forecast.get("expected_gain"), None), _finite(forecast.get("expected_loss"), None), cost_pips,
                point, quantiles["p10"], quantiles["p25"], quantiles["p50"], quantiles["p75"], quantiles["p90"],
                _finite(forecast.get("lower_bound"), None), _finite(forecast.get("upper_bound"), None),
                None, None, None, None, None, None, None, None, None, selected_tp, selected_sl,
                _text(final.get("main_reason"), ""), _text(blocker_list[0] if blocker_list else "", ""),
                _text(data_quality.get("status"), "UNKNOWN"), _text(drift.get("status"), "UNKNOWN"),
                _text(nlp.get("conflict_level"), "UNKNOWN"), _finite(forecast.get("priority_score") or priority.get("score"), None),
                _finite(forecast.get("knn_score") or priority.get("knn_score"), None), _finite(forecast.get("greedy_score") or priority.get("greedy_score"), None),
                _safe_probability(_mapping(canonical.get("forecasts")).get("agreement_score")), "PENDING", None, created.isoformat(),
                _text(canonical.get("source"), "UNKNOWN"), SCHEMA_VERSION,
            )
            sql = """
                INSERT OR IGNORE INTO settled_forecast_ledger_v3(
                    calculation_id,calculation_version,forecast_origin_time,forecast_origin_price,target_time,horizon,
                    session,d1_regime,h4_regime,h1_regime,regime_age,regime_transition_risk,full_metric_direction,
                    final_decision,tradeability_status,raw_confidence,calibrated_confidence,raw_buy_probability,
                    raw_sell_probability,raw_wait_probability,calibrated_buy_probability,calibrated_sell_probability,
                    calibrated_wait_probability,required_probability_threshold,expected_value_after_costs,
                    expected_favorable_movement,expected_adverse_movement,estimated_cost_pips,predicted_close,
                    p10,p25,p50,p75,p90,lower_band,upper_band,actual_close,absolute_error_pips,squared_error,
                    direction_correct,interval_hit,maximum_favorable_excursion,maximum_adverse_excursion,tp_touched,
                    sl_touched,selected_tp,selected_sl,main_reason,strongest_blocker,data_quality_status,drift_status,
                    event_risk_status,priority,knn_score,greedy_rank,model_agreement,record_status,settlement_timestamp,
                    created_at,source,schema_version
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """
            inserted += max(0, int(self._execute(sql, values)))
            for method, method_point in self._method_forecasts(canonical, ohlc, horizon, point, origin_price).items():
                if method_point is None:
                    continue
                method_direction = "BUY" if method_point > origin_price else "SELL" if method_point < origin_price else "WAIT"
                methods_inserted += max(0, int(self._execute(
                    """
                    INSERT OR IGNORE INTO forecast_method_ledger_v3(
                        calculation_id,calculation_version,forecast_origin_time,target_time,horizon,method,predicted_close,
                        predicted_direction,record_status,created_at
                    ) VALUES (?,?,?,?,?,?,?,?, 'PENDING', ?)
                    """,
                    (calc_id, calculation_version, origin_time.isoformat(), target.isoformat(), horizon, method, method_point, method_direction, created.isoformat()),
                )))
        return {"ok": True, "inserted": inserted, "method_rows": methods_inserted, "calculation_id": calc_id}

    def frame(self, *, status: Optional[str] = None, limit: int = 10000) -> pd.DataFrame:
        clauses = []
        params: list[Any] = []
        if status:
            clauses.append("record_status=?")
            params.append(status)
        params.append(int(limit))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = self._execute(
            f"SELECT * FROM settled_forecast_ledger_v3{where} ORDER BY forecast_origin_time DESC,horizon ASC LIMIT ?",
            params,
            fetch=True,
        )
        return pd.DataFrame(rows)

    def method_frame(self, *, status: str = "SETTLED", limit: int = 50000) -> pd.DataFrame:
        rows = self._execute(
            "SELECT * FROM forecast_method_ledger_v3 WHERE record_status=? ORDER BY forecast_origin_time ASC LIMIT ?",
            (status, int(limit)),
            fetch=True,
        )
        return pd.DataFrame(rows)

    def pending_count(self) -> int:
        rows = self._execute("SELECT COUNT(*) AS n FROM settled_forecast_ledger_v3 WHERE record_status='PENDING'", fetch=True)
        return int(rows[0]["n"]) if rows else 0

    def persist_snapshot(self, calculation_id: str, summary: Mapping[str, Any]) -> None:
        self._execute(
            """
            INSERT OR REPLACE INTO trust_validation_snapshots_v3(
                calculation_id,created_at,calculation_version,settled_sample_count,trust_classification,summary_json,schema_version
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                calculation_id, _utc_now(), _text(summary.get("calculation_version")), int(summary.get("settled_sample_count") or 0),
                _text(summary.get("trust_classification"), "INSUFFICIENT"), _json(summary), SCHEMA_VERSION,
            ),
        )


def _calibration_metrics(probabilities: pd.Series, outcomes: pd.Series) -> Dict[str, Any]:
    p = pd.to_numeric(probabilities, errors="coerce")
    y = pd.to_numeric(outcomes, errors="coerce")
    valid = p.notna() & y.notna()
    p = p.loc[valid].clip(1e-6, 1 - 1e-6)
    y = y.loc[valid].clip(0, 1)
    n = int(len(p))
    if n < int(TRUST_CONFIG["minimum_calibration_samples"]):
        return {
            "status": "DEVELOPING", "sample_count": n, "brier_score": None, "expected_calibration_error": None,
            "maximum_calibration_error": None, "calibration_slope": None, "calibration_intercept": None,
            "reliability_bins": [], "message": "Calibration developing — insufficient settled samples",
        }
    brier = float(np.mean((p.to_numpy() - y.to_numpy()) ** 2))
    bins = []
    ece = mce = 0.0
    for low in np.linspace(0, 0.9, 10):
        high = low + 0.1
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        count = int(mask.sum())
        if not count:
            continue
        mean_p = float(p.loc[mask].mean())
        mean_y = float(y.loc[mask].mean())
        gap = abs(mean_p - mean_y)
        ece += gap * count / n
        mce = max(mce, gap)
        bins.append({"lower": round(low, 2), "upper": round(high, 2), "count": count, "mean_probability": mean_p, "observed_rate": mean_y})
    x = np.log(p.to_numpy() / (1 - p.to_numpy()))
    slope = intercept = None
    if np.std(x) > 1e-12:
        try:
            slope, intercept = np.polyfit(x, y.to_numpy(), 1)
            slope, intercept = float(slope), float(intercept)
        except Exception:
            pass
    return {
        "status": "VALID", "sample_count": n, "brier_score": brier,
        "expected_calibration_error": float(ece), "maximum_calibration_error": float(mce),
        "calibration_slope": slope, "calibration_intercept": intercept, "reliability_bins": bins,
        "message": "Settled out-of-sample calibration",
    }


def _diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, horizon: int) -> Dict[str, Any]:
    mask = np.isfinite(loss_a) & np.isfinite(loss_b)
    d = loss_a[mask] - loss_b[mask]
    n = len(d)
    if n < int(TRUST_CONFIG["minimum_dm_samples"]):
        return {"status": "UNAVAILABLE", "sample_count": n, "reason": "Need aligned settled forecasts"}
    mean_d = float(np.mean(d))
    centered = d - mean_d
    lag_max = max(0, min(int(horizon) - 1, n // 5))
    variance = float(np.var(centered, ddof=1))
    for lag in range(1, lag_max + 1):
        covariance = float(np.sum(centered[lag:] * centered[:-lag]) / n)
        variance += 2.0 * (1.0 - lag / (lag_max + 1)) * covariance
    variance = max(variance / n, 1e-12)
    statistic = mean_d / math.sqrt(variance)
    p_value = math.erfc(abs(statistic) / math.sqrt(2.0))
    preferred = "METHOD_A" if mean_d < 0 else "METHOD_B" if mean_d > 0 else "TIE"
    return {"status": "SIGNIFICANT" if p_value < 0.05 else "NOT_SIGNIFICANT", "sample_count": n, "statistic": statistic, "p_value": p_value, "preferred": preferred}


def _spa_equivalent(methods: pd.DataFrame, benchmark: str = "LAST_CLOSE") -> Dict[str, Any]:
    if methods.empty:
        return {"status": "UNAVAILABLE", "sample_count": 0, "reason": "No settled method forecasts"}
    pivot = methods.pivot_table(index=["calculation_id", "horizon"], columns="method", values="absolute_error", aggfunc="first")
    if benchmark not in pivot.columns:
        return {"status": "UNAVAILABLE", "sample_count": 0, "reason": "Benchmark unavailable"}
    candidates = [c for c in pivot.columns if c != benchmark]
    if not candidates:
        return {"status": "UNAVAILABLE", "sample_count": 0, "reason": "No challenger methods"}
    aligned = pivot[[benchmark] + candidates].dropna()
    n = len(aligned)
    if n < int(TRUST_CONFIG["minimum_spa_samples"]):
        return {"status": "UNAVAILABLE", "sample_count": n, "reason": "Insufficient aligned settled forecasts"}
    differentials = {c: aligned[benchmark].to_numpy() - aligned[c].to_numpy() for c in candidates}
    means = {c: float(np.mean(v)) for c, v in differentials.items()}
    best = max(means, key=means.get)
    observed = means[best]
    rng = np.random.default_rng(20260619)
    centered = {c: v - np.mean(v) for c, v in differentials.items()}
    boot = []
    block = max(2, int(round(n ** (1 / 3))))
    for _ in range(600):
        indices: list[int] = []
        while len(indices) < n:
            start = int(rng.integers(0, n))
            indices.extend([(start + j) % n for j in range(block)])
        indices = indices[:n]
        boot.append(max(float(np.mean(v[indices])) for v in centered.values()))
    p_value = float((1 + sum(x >= observed for x in boot)) / (len(boot) + 1))
    return {
        "status": "SUPERIOR" if observed > 0 and p_value < 0.05 else "NOT_PROVEN",
        "sample_count": n, "best_method": best, "benchmark": benchmark,
        "mean_loss_improvement": observed, "p_value": p_value,
        "test": "block-bootstrap SPA-equivalent on aligned absolute-error losses",
    }


def _dsr(net_pips: np.ndarray, trial_sharpes: np.ndarray) -> Dict[str, Any]:
    values = net_pips[np.isfinite(net_pips)]
    trials = trial_sharpes[np.isfinite(trial_sharpes)]
    if len(values) < 30:
        return {"status": "UNAVAILABLE", "sample_size": int(len(values)), "reason": "Need at least 30 aligned net returns"}
    if len(trials) < 2:
        return {"status": "UNAVAILABLE", "sample_size": int(len(values)), "number_of_tested_configurations": int(len(trials)), "reason": "Need at least two genuine tested configurations"}
    std = float(np.std(values, ddof=1))
    if std <= 1e-12:
        return {"status": "UNAVAILABLE", "sample_size": int(len(values)), "reason": "Zero return variance"}
    mean = float(np.mean(values))
    z = (values - mean) / std
    skew = float(np.mean(z ** 3))
    kurt = float(np.mean(z ** 4))
    raw_sharpe = mean / std * math.sqrt(252.0)
    trial_std = max(float(np.std(trials, ddof=1)), 1e-12)
    expected_max = float(np.mean(trials) + trial_std * math.sqrt(2.0 * math.log(max(len(trials), 2))))
    denom = math.sqrt(max((1.0 - skew * raw_sharpe + (kurt - 1.0) * raw_sharpe ** 2 / 4.0) / max(len(values) - 1, 1), 1e-12))
    statistic = (raw_sharpe - expected_max) / denom
    probability = 0.5 * (1.0 + math.erf(statistic / math.sqrt(2.0)))
    return {
        "status": "ACCEPT" if probability >= 0.95 else "WEAK" if probability >= 0.70 else "REJECT",
        "raw_sharpe": raw_sharpe, "deflated_sharpe_probability": probability, "sample_size": int(len(values)),
        "skewness": skew, "kurtosis": kurt, "number_of_tested_configurations": int(len(trials)),
    }


def _pbo(frame: pd.DataFrame) -> Dict[str, Any]:
    if frame.empty or "calculation_version" not in frame:
        return {"status": "UNAVAILABLE", "reason": "No genuine configuration history", "tested_configuration_count": 0, "fold_count": 0}
    configs = sorted(frame["calculation_version"].dropna().astype(str).unique())
    min_configs = int(TRUST_CONFIG["minimum_pbo_configurations"])
    if len(configs) < min_configs:
        return {"status": "UNAVAILABLE", "reason": "Need at least two genuinely tested configurations", "tested_configuration_count": len(configs), "fold_count": 0}
    data = frame.sort_values("forecast_origin_time").copy()
    folds = np.array_split(np.arange(len(data)), max(int(TRUST_CONFIG["minimum_pbo_folds"]), min(8, len(data) // 25)))
    ranks = []
    usable = 0
    for test_idx in folds:
        if len(test_idx) < 5:
            continue
        train_idx = np.setdiff1d(np.arange(len(data)), test_idx)
        train = data.iloc[train_idx]
        test = data.iloc[test_idx]
        train_scores = train.groupby("calculation_version")["net_pips"].mean()
        test_scores = test.groupby("calculation_version")["net_pips"].mean()
        common = train_scores.index.intersection(test_scores.index)
        if len(common) < min_configs:
            continue
        best = train_scores.loc[common].idxmax()
        rank = float(test_scores.loc[common].rank(pct=True, ascending=True).loc[best])
        ranks.append(rank)
        usable += 1
    if usable < int(TRUST_CONFIG["minimum_pbo_folds"]):
        return {"status": "UNAVAILABLE", "reason": "Insufficient chronological folds with multiple configurations", "tested_configuration_count": len(configs), "fold_count": usable}
    probability = float(np.mean(np.asarray(ranks) <= 0.5))
    return {"status": "VALID", "probability_of_backtest_overfitting": probability, "tested_configuration_count": len(configs), "fold_count": usable, "validation_status": "REJECT" if probability > 0.5 else "ACCEPT"}


def aggregate_trust(store: TrustHistoryStore) -> Dict[str, Any]:
    frame = store.frame(status="SETTLED", limit=50000)
    if frame.empty:
        return {
            "schema_version": SCHEMA_VERSION, "settled_sample_count": 0, "pending_sample_count": store.pending_count(),
            "trust_classification": "INSUFFICIENT", "message": "Calibration developing — insufficient settled samples",
            "groups": [], "calibration": {}, "interval": {}, "pbo": {"status": "UNAVAILABLE"},
            "dsr": {"status": "UNAVAILABLE"}, "dm": [], "spa": {"status": "UNAVAILABLE"},
        }
    numeric_cols = [
        "forecast_origin_price", "actual_close", "absolute_error_pips", "squared_error", "direction_correct", "interval_hit",
        "maximum_favorable_excursion", "maximum_adverse_excursion", "tp_touched", "sl_touched", "expected_value_after_costs",
        "estimated_cost_pips", "raw_confidence", "calibrated_confidence", "lower_band", "upper_band", "predicted_close",
    ]
    for col in numeric_cols:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["forecast_origin_time"] = pd.to_datetime(frame["forecast_origin_time"], utc=True, errors="coerce")
    frame["signed_gross_pips"] = [
        _signed_pips(float(o), float(a), _direction(d)) if pd.notna(o) and pd.notna(a) else np.nan
        for o, a, d in zip(frame["forecast_origin_price"], frame["actual_close"], frame["full_metric_direction"])
    ]
    frame["net_pips"] = frame["signed_gross_pips"] - frame["estimated_cost_pips"].fillna(float(TRUST_CONFIG["default_cost_pips"]) + float(TRUST_CONFIG["safety_buffer_pips"]))
    frame["interval_width_pips"] = (frame["upper_band"] - frame["lower_band"]).abs() / float(TRUST_CONFIG["pip_size"])
    groups = []
    group_cols = ["h1_regime", "h4_regime", "d1_regime", "session", "horizon", "full_metric_direction", "calculation_version"]
    for keys, group in frame.groupby(group_cols, dropna=False):
        n = len(group)
        net = group["net_pips"].dropna().to_numpy(dtype=float)
        wins = net[net > 0]
        losses = net[net < 0]
        equity = np.cumsum(net) if len(net) else np.array([])
        drawdown = float(np.max(np.maximum.accumulate(equity) - equity)) if len(equity) else None
        pf = float(np.sum(wins) / abs(np.sum(losses))) if len(losses) and abs(np.sum(losses)) > 1e-12 else None
        cal = _calibration_metrics(group["calibrated_confidence"], group["direction_correct"])
        coverage = float(group["interval_hit"].mean()) if group["interval_hit"].notna().any() else None
        width = float(group["interval_width_pips"].mean()) if group["interval_width_pips"].notna().any() else None
        if n >= int(TRUST_CONFIG["validated_min_samples"]) and np.nanmean(net) > 0 and (cal.get("expected_calibration_error") is None or cal.get("expected_calibration_error") <= TRUST_CONFIG["acceptable_ece"]):
            trust = "VALIDATED"
        elif np.nanmean(net) < 0:
            trust = "REJECTED"
        elif n >= int(TRUST_CONFIG["developing_min_samples"]):
            trust = "DEVELOPING"
        else:
            trust = "INSUFFICIENT"
        groups.append({
            **dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,))),
            "settled_sample_count": n, "opportunity_coverage": float((group["tradeability_status"].isin(["BUY", "SELL"])).mean()),
            "trade_frequency": float((group["final_decision"].isin(["BUY", "SELL"])).mean()),
            "direction_accuracy": float(group["direction_correct"].mean()), "average_net_pips": float(np.nanmean(net)) if len(net) else None,
            "median_net_pips": float(np.nanmedian(net)) if len(net) else None, "win_rate": float(np.mean(net > 0)) if len(net) else None,
            "profit_factor": pf, "maximum_drawdown": drawdown, "mae": float(group["absolute_error_pips"].mean()),
            "rmse": float(math.sqrt(group["squared_error"].mean())), "brier_score": cal.get("brier_score"),
            "calibration_error": cal.get("expected_calibration_error"), "interval_coverage": coverage, "mean_interval_width": width,
            "tp_touch_rate": float(group["tp_touched"].mean()) if group["tp_touched"].notna().any() else None,
            "sl_touch_rate": float(group["sl_touched"].mean()) if group["sl_touched"].notna().any() else None,
            "average_mfe": float(group["maximum_favorable_excursion"].mean()), "average_adverse_excursion": float(group["maximum_adverse_excursion"].mean()),
            "trust_classification": trust,
        })
    overall_cal = _calibration_metrics(frame["calibrated_confidence"], frame["direction_correct"])
    raw_cal = _calibration_metrics(frame["raw_confidence"], frame["direction_correct"])
    coverage = float(frame["interval_hit"].mean()) if frame["interval_hit"].notna().any() else None
    width = float(frame["interval_width_pips"].mean()) if frame["interval_width_pips"].notna().any() else None
    methods = store.method_frame(status="SETTLED", limit=100000)
    dm_rows = []
    if not methods.empty:
        pivot = methods.pivot_table(index=["calculation_id", "horizon"], columns="method", values="absolute_error", aggfunc="first")
        if "LAST_CLOSE" in pivot:
            for method in [c for c in pivot.columns if c != "LAST_CLOSE"]:
                aligned = pivot[[method, "LAST_CLOSE"]].dropna()
                result = _diebold_mariano(aligned[method].to_numpy(), aligned["LAST_CLOSE"].to_numpy(), 1)
                result.update({"method": method, "benchmark": "LAST_CLOSE", "loss": "absolute_error"})
                dm_rows.append(result)
    config_sharpes = []
    for _, group in frame.groupby("calculation_version"):
        values = group["net_pips"].dropna().to_numpy(dtype=float)
        if len(values) >= 5 and np.std(values, ddof=1) > 1e-12:
            config_sharpes.append(float(np.mean(values) / np.std(values, ddof=1) * math.sqrt(252.0)))
    dsr = _dsr(frame["net_pips"].to_numpy(dtype=float), np.asarray(config_sharpes, dtype=float))
    pbo = _pbo(frame)
    spa = _spa_equivalent(methods)
    n = len(frame)
    mean_net = float(frame["net_pips"].mean())
    severe_calibration = overall_cal.get("expected_calibration_error") is not None and overall_cal["expected_calibration_error"] > 0.25
    severe_overfit = pbo.get("probability_of_backtest_overfitting") is not None and pbo["probability_of_backtest_overfitting"] > 0.7
    if mean_net < 0 or severe_calibration or severe_overfit:
        classification = "REJECTED"
    elif n >= int(TRUST_CONFIG["validated_min_samples"]) and overall_cal.get("expected_calibration_error") is not None and overall_cal["expected_calibration_error"] <= TRUST_CONFIG["acceptable_ece"]:
        classification = "VALIDATED"
    elif n >= int(TRUST_CONFIG["developing_min_samples"]):
        classification = "DEVELOPING"
    else:
        classification = "INSUFFICIENT"
    return {
        "schema_version": SCHEMA_VERSION, "calculation_version": CALCULATION_VERSION,
        "settled_sample_count": n, "pending_sample_count": store.pending_count(), "trust_classification": classification,
        "average_net_pips": mean_net, "direction_accuracy": float(frame["direction_correct"].mean()),
        "calibration": {"calibrated": overall_cal, "raw": raw_cal},
        "interval": {
            "coverage": coverage, "mean_width_pips": width, "target_coverage": TRUST_CONFIG["target_interval_coverage"],
            "undercoverage": bool(coverage is not None and coverage < TRUST_CONFIG["target_interval_coverage"] - TRUST_CONFIG["acceptable_coverage_error"]),
            "overcoverage": bool(coverage is not None and coverage > TRUST_CONFIG["target_interval_coverage"] + TRUST_CONFIG["acceptable_coverage_error"]),
            "sharpness": None if width is None else 1.0 / max(width, 1e-9), "settled_residual_sample_count": int(frame["absolute_error_pips"].notna().sum()),
        },
        "expected_mfe_pips": float(frame["maximum_favorable_excursion"].mean()),
        "expected_mae_pips": float(frame["maximum_adverse_excursion"].mean()),
        "pbo": pbo, "dsr": dsr, "dm": dm_rows, "spa": spa,
        "groups": groups,
        "message": "Settled out-of-sample history only; pending forecasts are excluded",
    }


def enrich_canonical_with_trust(canonical: Mapping[str, Any], store: TrustHistoryStore) -> dict[str, Any]:
    payload = dict(canonical)
    summary = aggregate_trust(store)
    payload["trust_validation"] = summary
    payload["calculation_id"] = payload.get("canonical_calculation_id") or payload.get("run_id")
    payload["calculation_started_at"] = payload.get("calculation_started_at") or payload.get("created_at")
    payload["calculation_completed_at"] = payload.get("calculation_completed_at") or _utc_now()
    payload["data_timestamp"] = payload.get("latest_completed_candle_time")
    payload["data_quality_status"] = _text(_mapping(payload.get("data_quality")).get("status"), "UNKNOWN")
    payload["stale_data_status"] = "STALE" if bool(payload.get("stale") or _mapping(payload.get("metadata")).get("stale")) else "CURRENT"
    market = _mapping(payload.get("market"))
    source_present = bool(payload.get("source") or market.get("source") or market.get("source_available"))
    payload["source_status"] = "AVAILABLE" if source_present and not str(payload["data_quality_status"]).startswith("FAIL") else "UNAVAILABLE"
    payload["error_status"] = "OK" if not payload.get("failure_reason") else "ERROR"
    payload.setdefault("metadata", {})["trust_history_schema_version"] = SCHEMA_VERSION
    payload["metadata"]["pending_forecasts_are_not_scored"] = True
    payload["metadata"]["original_forecasts_are_immutable"] = True
    payload["metadata"]["walk_forward_policy"] = "chronological, purged and embargoed existing OOS forecasts"
    return payload


_DEFAULT_STORE: Optional[TrustHistoryStore] = None


def get_trust_history_store() -> TrustHistoryStore:
    global _DEFAULT_STORE
    if _DEFAULT_STORE is None:
        _DEFAULT_STORE = TrustHistoryStore()
    return _DEFAULT_STORE


__all__ = [
    "TrustHistoryStore", "get_trust_history_store", "aggregate_trust", "enrich_canonical_with_trust",
    "normalize_completed_ohlc", "SCHEMA_VERSION", "CALCULATION_VERSION",
]
