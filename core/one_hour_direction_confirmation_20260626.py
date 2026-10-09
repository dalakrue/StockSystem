"""Leakage-safe operational EURUSD H1 direction confirmation.

This is an additive operational layer. It never overwrites the protected
production decision, protected Field-1 values, protected Power BI raw path,
canonical identity, regime formulas, or protected hashes.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence
import hashlib, json, math, sqlite3
import numpy as np
import pandas as pd

VERSION = "one-hour-direction-confirmation-20260626-v3"
PIP = 0.0001
ABSOLUTE_MAXIMUM_PIPS = 50.0
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "data" / "quant_app.sqlite3"
STATE_KEY = "one_hour_direction_confirmation_20260626"
CLASSES = ("BUY", "SELL", "NEUTRAL")


def finite_float(value: Any) -> float | None:
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def utc_timestamp(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.Timestamp(value)
        if pd.isna(ts):
            return None
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    except Exception:
        return None


def alpha_pips(forecast: float, completed_origin_close: float) -> float:
    return round((float(forecast) - float(completed_origin_close)) / PIP, 10)


def beta_pips(previous_immutable_forecast: float, previous_completed_origin_close: float) -> float:
    return round((float(previous_immutable_forecast) - float(previous_completed_origin_close)) / PIP, 10)


def sign_agreement(alpha: float | None, beta: float | None, neutral: float = 1e-12) -> str:
    if alpha is None or beta is None or abs(alpha) <= neutral or abs(beta) <= neutral:
        return "neutral involvement"
    return "same sign" if np.sign(alpha) == np.sign(beta) else "opposite sign"


def robust_dispersion(values: Sequence[float], epsilon: float = 1e-6) -> float | None:
    arr = np.asarray([float(v) for v in values if finite_float(v) is not None], dtype=float)
    if arr.size < 5:
        return None
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return max(1.4826 * mad, epsilon)


def robust_z(alpha: float | None, beta: float | None, historical_differences: Sequence[float]) -> float | None:
    scale = robust_dispersion(historical_differences)
    if alpha is None or beta is None or scale is None:
        return None
    return abs(float(alpha) - float(beta)) / scale


def instability_status(z: float | None) -> str:
    if z is None:
        return "LOW EVIDENCE"
    if z < 0.75:
        return "Stable"
    if z < 1.5:
        return "Normal change"
    if z < 2.5:
        return "Elevated instability"
    return "Severe disagreement"


def neutral_threshold_pips(spread_pips: float | None, slippage_pips: float,
                           noise_atr_fraction: float, atr_pips: float | None,
                           micro_move_threshold: float | None = 0.0) -> float:
    return max(
        max(0.0, finite_float(spread_pips) or 0.0) + max(0.0, float(slippage_pips)),
        max(0.0, float(noise_atr_fraction)) * max(0.0, finite_float(atr_pips) or 0.0),
        max(0.0, finite_float(micro_move_threshold) or 0.0),
    )


def classify_actual(open_price: float, close_price: float, threshold_pips: float) -> tuple[str, float]:
    move = (float(close_price) - float(open_price)) / PIP
    return ("BUY" if move > threshold_pips else "SELL" if move < -threshold_pips else "NEUTRAL"), move


def _q99(values: Sequence[float], minimum_n: int = 20) -> float | None:
    arr = np.asarray([abs(float(v)) for v in values if finite_float(v) is not None], dtype=float)
    return float(np.quantile(arr, 0.99)) if arr.size >= minimum_n else None


def safe_endpoint(raw_prediction: float, origin_close: float, atr_pips: float | None,
                  historical_abs_moves_pips: Sequence[float], atr_multiplier: float = 1.25,
                  historical_abs_errors_pips: Sequence[float] = (),
                  fallback_label: str = "GLOBAL_H1") -> dict[str, Any]:
    raw_move = (float(raw_prediction) - float(origin_close)) / PIP
    atr_cap = min(ABSOLUTE_MAXIMUM_PIPS, max(0.1, (finite_float(atr_pips) or ABSOLUTE_MAXIMUM_PIPS) * float(atr_multiplier)))
    move_tail = _q99(historical_abs_moves_pips)
    error_tail = _q99(historical_abs_errors_pips)
    candidates = [(ABSOLUTE_MAXIMUM_PIPS, "ABSOLUTE_50_PIP"), (atr_cap, "ATR_CAP")]
    if move_tail is not None:
        candidates.append((min(ABSOLUTE_MAXIMUM_PIPS, max(0.1, move_tail)), f"{fallback_label}_MOVE_P99"))
    if error_tail is not None:
        candidates.append((min(ABSOLUTE_MAXIMUM_PIPS, max(0.1, error_tail)), f"{fallback_label}_ERROR_P99"))
    active, source = min(candidates, key=lambda x: x[0])
    safe_move = float(np.clip(raw_move, -active, active))
    capped = not math.isclose(raw_move, safe_move, abs_tol=1e-12)
    return {
        "raw_move_pips": raw_move, "safe_move_pips": safe_move,
        "active_cap_pips": active, "atr_cap_pips": atr_cap,
        "session_tail_cap_pips": move_tail, "forecast_error_tail_cap_pips": error_tail,
        "capped": capped, "cap_source": source,
        "cap_reason": "raw displacement exceeded active safety cap" if capped else "within active safety cap",
        "pips_removed_by_cap": abs(raw_move - safe_move),
        "safe_prediction": float(origin_close) + safe_move * PIP,
    }


def rescale_operational_path(raw_path: Sequence[float], origin_close: float, active_cap_pips: float) -> list[float]:
    vals = [finite_float(v) for v in raw_path]
    vals = [float(v) for v in vals if v is not None]
    if not vals:
        return []
    displacements = np.asarray([(v - origin_close) / PIP for v in vals], dtype=float)
    max_abs = float(np.max(np.abs(displacements))) if displacements.size else 0.0
    scale = 1.0 if max_abs <= active_cap_pips or max_abs == 0 else active_cap_pips / max_abs
    safe = np.clip(displacements * scale, -active_cap_pips, active_cap_pips)
    return [float(origin_close + x * PIP) for x in safe]


def shrink_probabilities(counts: Mapping[str, float], parent: Mapping[str, float] | None = None,
                         strength: float = 12.0) -> dict[str, float]:
    prior = parent or {k: 1 / 3 for k in CLASSES}
    total = sum(max(0.0, float(counts.get(k, 0))) for k in CLASSES)
    denom = total + strength
    p = {k: (max(0.0, float(counts.get(k, 0))) + strength * float(prior.get(k, 1 / 3))) / denom for k in CLASSES}
    s = sum(p.values())
    return {k: p[k] / s for k in CLASSES}


def bounded_weights(losses: Mapping[str, float], minimum: float = 0.05, maximum: float = 0.40) -> dict[str, float]:
    keys = list(losses)
    if not keys:
        return {}
    n = len(keys)
    if n * minimum > 1 or n * maximum < 1:
        raise ValueError("infeasible weight bounds")
    raw = np.asarray([1.0 / max(1e-6, float(losses[k])) for k in keys], dtype=float)
    target = raw / raw.sum()
    lo, hi = 0.0, 1e6
    for _ in range(100):
        lam = (lo + hi) / 2
        w = np.clip(target * lam, minimum, maximum)
        if w.sum() > 1.0:
            hi = lam
        else:
            lo = lam
    w = np.clip(target * ((lo + hi) / 2), minimum, maximum)
    residual = 1.0 - float(w.sum())
    for i in np.argsort(-target):
        room = (maximum - w[i]) if residual > 0 else (w[i] - minimum)
        delta = math.copysign(min(abs(residual), max(0.0, room)), residual)
        w[i] += delta
        residual -= delta
        if abs(residual) < 1e-12:
            break
    return {k: float(v) for k, v in zip(keys, w)}


def _geom_reliability(parts: Mapping[str, float | None], weights: Mapping[str, float]) -> float | None:
    available = [(k, parts.get(k)) for k in weights if parts.get(k) is not None]
    if not available:
        return None
    den = sum(weights[k] for k, _ in available)
    return float(math.exp(sum(weights[k] * math.log(max(0.01, min(1.0, float(v)))) for k, v in available) / den))


def _session_from_hour(hour: int) -> str:
    if 0 <= hour < 6: return "SYDNEY_ASIA"
    if 6 <= hour < 8: return "ASIA_LONDON"
    if 8 <= hour < 13: return "LONDON"
    if 13 <= hour < 17: return "LONDON_NEW_YORK_OVERLAP"
    if 17 <= hour < 22: return "NEW_YORK"
    return "OTHER"


def _extract_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("calculation_staging_ohlc_df_20260617", "validated_df", "data", "df", "ohlc_df", "mt5_data"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty and {'open', 'close'}.issubset({str(c).lower() for c in value.columns}):
            return value
    return pd.DataFrame()


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        value = get_canonical(state)
        return value if isinstance(value, Mapping) else {}
    except Exception:
        return {}


def _walk_values(obj: Any, key_terms: Sequence[str]) -> list[float]:
    out: list[float] = []
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if isinstance(v, (Mapping, list, tuple)):
                out.extend(_walk_values(v, key_terms))
            elif isinstance(v, (int, float)) and any(t in str(k).lower() for t in key_terms):
                out.append(float(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_walk_values(v, key_terms))
    return out


def _forecast_from_state(state: Mapping[str, Any], origin_close: float) -> float:
    candidates: list[float] = []
    for key in ("powerbi_calibrated_bundle_20260617", "powerbi_result", "powerbi_projection"):
        candidates.extend(_walk_values(state.get(key), ("1h", "next_hour", "predicted_price", "forecast_price", "central_prediction")))
    plausible = [x for x in candidates if abs(x - origin_close) < 0.02]
    return plausible[0] if plausible else origin_close


def _raw_path_from_state(state: Mapping[str, Any], origin_close: float, endpoint: float) -> list[float]:
    for key in ("powerbi_calibrated_bundle_20260617", "powerbi_result", "powerbi_projection"):
        obj = state.get(key)
        if isinstance(obj, Mapping):
            for name in ("central_path", "prediction_path", "forecast_path", "path", "future_path"):
                value = obj.get(name)
                if isinstance(value, (list, tuple)):
                    vals = [finite_float(x) for x in value]
                    vals = [float(x) for x in vals if x is not None and abs(float(x) - origin_close) < .05]
                    if vals:
                        return vals
    return [origin_close, endpoint]


class OneHourLedger:
    def __init__(self, db_path: str | Path | None = None):
        self.path = Path(db_path or DEFAULT_DB)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self):
        c = sqlite3.connect(str(self.path), timeout=15)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=15000")
        return c

    def initialize(self):
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS one_hour_direction_ledger_20260626 (
            forecast_id TEXT PRIMARY KEY, run_id TEXT, generation_id TEXT, snapshot_hash TEXT, symbol TEXT DEFAULT 'EURUSD', timeframe TEXT DEFAULT 'H1', broker_candle_time TEXT,
            forecast_origin_time TEXT, target_h1_open_time TEXT, target_h1_close_time TEXT, forecast_origin_close REAL, target_h1_open REAL, raw_forecast REAL, safe_forecast REAL,
            alpha_pips REAL,beta_pips REAL,alpha_beta_difference_pips REAL,alpha_beta_sign_agreement TEXT,direction_reversal INTEGER,robust_z REAL,instability_status TEXT,
            p_buy REAL,p_sell REAL,p_neutral REAL,model_weights TEXT,confirmation_action TEXT,confirmation_level TEXT,wait_reason TEXT,reliability REAL,reliability_components TEXT,probability_margin REAL,direction_score REAL,
            session TEXT,overlap TEXT,broker_hour INTEGER,production_regime TEXT,production_action TEXT,compatibility_score REAL,transition_risk_state TEXT,data_quality_state TEXT,
            spread_pips REAL,estimated_cost_pips REAL,neutral_threshold_pips REAL,expected_open_close_pips REAL,active_cap_pips REAL,atr_cap_pips REAL,session_tail_cap_pips REAL,cap_source TEXT,capped INTEGER,pips_removed_by_cap REAL,wrong_direction_probability REAL,origin_payload TEXT,
            actual_target_close REAL,actual_open_to_close_pips REAL,actual_direction TEXT,correctness INTEGER,brier_score REAL,log_loss REAL,realized_utility REAL,decision_regret REAL,mfe_pips REAL,mae_pips REAL,settlement_status TEXT DEFAULT 'PENDING',settled_at TEXT,inserted_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
            required = {
                "confirmation_level": "TEXT", "broker_hour": "INTEGER", "wrong_direction_probability": "REAL",
                "symbol": "TEXT DEFAULT 'EURUSD'", "timeframe": "TEXT DEFAULT 'H1'", "broker_candle_time": "TEXT",
                "direction_reversal": "INTEGER", "model_weights": "TEXT", "confirmation_action": "TEXT", "wait_reason": "TEXT",
                "reliability": "REAL", "reliability_components": "TEXT", "probability_margin": "REAL", "production_action": "TEXT",
                "compatibility_score": "REAL", "expected_open_close_pips": "REAL", "atr_cap_pips": "REAL", "session_tail_cap_pips": "REAL",
                "pips_removed_by_cap": "REAL", "brier_score": "REAL", "log_loss": "REAL", "realized_utility": "REAL", "decision_regret": "REAL"
            }
            present = {r[1] for r in c.execute("PRAGMA table_info(one_hour_direction_ledger_20260626)").fetchall()}
            for col, ddl in required.items():
                if col not in present:
                    c.execute(f"ALTER TABLE one_hour_direction_ledger_20260626 ADD COLUMN {col} {ddl}")
            indexes = (
                "CREATE INDEX IF NOT EXISTS idx_oh_origin ON one_hour_direction_ledger_20260626(forecast_origin_time)",
                "CREATE INDEX IF NOT EXISTS idx_oh_target ON one_hour_direction_ledger_20260626(target_h1_close_time)",
                "CREATE INDEX IF NOT EXISTS idx_oh_session ON one_hour_direction_ledger_20260626(session)",
                "CREATE INDEX IF NOT EXISTS idx_oh_regime ON one_hour_direction_ledger_20260626(production_regime)",
                "CREATE INDEX IF NOT EXISTS idx_oh_status ON one_hour_direction_ledger_20260626(settlement_status)",
                "CREATE INDEX IF NOT EXISTS idx_oh_hash ON one_hour_direction_ledger_20260626(snapshot_hash)",
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_oh_immutable_origin ON one_hour_direction_ledger_20260626(symbol,timeframe,forecast_origin_time,snapshot_hash)",
            )
            for sql in indexes:
                c.execute(sql)

    def insert_origin(self, row: Mapping[str, Any]) -> bool:
        with self.connect() as c:
            cols = [r[1] for r in c.execute("PRAGMA table_info(one_hour_direction_ledger_20260626)").fetchall() if r[1] not in ('inserted_at', 'settled_at')]
            payload = dict(row)
            payload['settlement_status'] = 'PENDING'
            for k in ('origin_payload', 'model_weights', 'reliability_components'):
                if isinstance(payload.get(k), (dict, list)):
                    payload[k] = json.dumps(payload[k], default=str, sort_keys=True)
            use = [k for k in cols if k in payload]
            vals = [payload.get(k) for k in use]
            cur = c.execute(f"INSERT OR IGNORE INTO one_hour_direction_ledger_20260626 ({','.join(use)}) VALUES ({','.join('?' for _ in use)})", vals)
            return cur.rowcount > 0

    def previous(self, before_time: Any) -> Mapping[str, Any] | None:
        ts = utc_timestamp(before_time)
        if ts is None:
            return None
        with self.connect() as c:
            r = c.execute("SELECT * FROM one_hour_direction_ledger_20260626 WHERE forecast_origin_time < ? ORDER BY forecast_origin_time DESC LIMIT 1", (ts.isoformat(),)).fetchone()
            return dict(r) if r else None

    def history(self, days: int = 25) -> pd.DataFrame:
        with self.connect() as c:
            return pd.read_sql_query("""SELECT * FROM one_hour_direction_ledger_20260626
                WHERE forecast_origin_time >= datetime((SELECT MAX(forecast_origin_time) FROM one_hour_direction_ledger_20260626), ?)
                ORDER BY forecast_origin_time DESC""", c, params=(f'-{int(days)} days',))

    def settle(self, ohlc: pd.DataFrame, time_col: str = 'time') -> int:
        if not isinstance(ohlc, pd.DataFrame) or ohlc.empty:
            return 0
        names = {str(x).lower(): x for x in ohlc.columns}
        tc = names.get(time_col.lower()) or names.get('datetime') or names.get('date')
        oc, hc, lc, cc = names.get('open'), names.get('high'), names.get('low'), names.get('close')
        if tc is None or oc is None or cc is None:
            return 0
        f = ohlc[[x for x in (tc, oc, hc, lc, cc) if x is not None]].copy()
        f['_t'] = pd.to_datetime(f[tc], utc=True, errors='coerce')
        f = f.dropna(subset=['_t']).sort_values('_t')
        settled = 0
        with self.connect() as c:
            pending = c.execute("SELECT * FROM one_hour_direction_ledger_20260626 WHERE settlement_status='PENDING'").fetchall()
            for r in pending:
                ot, ct = utc_timestamp(r['target_h1_open_time']), utc_timestamp(r['target_h1_close_time'])
                if ot is None or ct is None or f['_t'].max() < ot:
                    continue
                m = f[f['_t'] == ot]
                if m.empty:
                    continue
                x = m.iloc[-1]
                op, cl = float(x[oc]), float(x[cc])
                direction, move = classify_actual(op, cl, float(r['neutral_threshold_pips'] or 0))
                action = str(r['confirmation_action'] or 'WAIT').upper()
                pred = 'BUY' if action.endswith('BUY') else 'SELL' if action.endswith('SELL') else 'NEUTRAL'
                probs = np.array([float(r['p_buy'] or 0), float(r['p_sell'] or 0), float(r['p_neutral'] or 0)])
                yi = CLASSES.index(direction)
                brier = float(np.mean((probs - np.eye(3)[yi]) ** 2))
                logloss = float(-math.log(max(1e-12, probs[yi])))
                correct = int(pred == direction)
                cost = float(r['estimated_cost_pips'] or 0)
                util = move - cost if pred == 'BUY' else -move - cost if pred == 'SELL' else 0.0
                best = max(move - cost, -move - cost, 0.0)
                mfe = (float(x[hc]) - op) / PIP if hc else None
                mae = (float(x[lc]) - op) / PIP if lc else None
                c.execute("""UPDATE one_hour_direction_ledger_20260626 SET target_h1_open=?,actual_target_close=?,actual_open_to_close_pips=?,actual_direction=?,correctness=?,brier_score=?,log_loss=?,realized_utility=?,decision_regret=?,mfe_pips=?,mae_pips=?,settlement_status='SETTLED',settled_at=CURRENT_TIMESTAMP WHERE forecast_id=? AND settlement_status='PENDING'""",
                          (op, cl, move, direction, correct, brier, logloss, util, best-util, mfe, mae, r['forecast_id']))
                settled += 1
        return settled


def _hist_probs(h: pd.DataFrame, parent: Mapping[str, float], strength: float = 15.0) -> dict[str, float]:
    if h.empty or 'actual_direction' not in h:
        return dict(parent)
    return shrink_probabilities(h.actual_direction.value_counts().to_dict(), parent, strength)


def _hierarchical_history(settled: pd.DataFrame, session: str, regime: str, hour: int) -> tuple[pd.DataFrame, str]:
    if settled.empty:
        return settled, "GLOBAL_PRIOR"
    levels = [
        ((settled.session == session) & (settled.production_regime == regime) & (settled.broker_hour == hour), "SESSION_REGIME_HOUR"),
        ((settled.session == session) & (settled.broker_hour == hour), "SESSION_HOUR"),
        (settled.session == session, "SESSION"),
        (settled.broker_hour == hour, "BROKER_HOUR"),
        (pd.Series(True, index=settled.index), "GLOBAL_H1"),
    ]
    for mask, label in levels:
        subset = settled[mask]
        if len(subset) >= 8 or label == "GLOBAL_H1":
            return subset, label
    return settled, "GLOBAL_H1"


def _probabilities(f: pd.DataFrame, names: Mapping[str, Any], safe_move: float,
                   selected_hist: pd.DataFrame, global_hist: pd.DataFrame,
                   alpha: float, beta: float | None) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    oc, cc, hc, lc = names.get('open'), names.get('close'), names.get('high'), names.get('low')
    last = f.iloc[-1]
    body = (float(last[cc]) - float(last[oc])) / PIP
    rng = max(.1, (float(last[hc]) - float(last[lc])) / PIP) if hc and lc else max(.1, abs(body))
    clv = ((float(last[cc]) - float(last[lc])) / (float(last[hc]) - float(last[lc])) - .5) * 2 if hc and lc and float(last[hc]) != float(last[lc]) else 0
    closes = pd.to_numeric(f[cc], errors='coerce')
    pressure = float((closes.iloc[-1] - closes.iloc[-4]) / PIP) if len(closes) >= 4 else body
    parent = _hist_probs(global_hist, {k: 1/3 for k in CLASSES}, 18)
    evidence = {
        'path': shrink_probabilities({'BUY': max(0, safe_move), 'SELL': max(0, -safe_move), 'NEUTRAL': 2}, parent, 8),
        'candle': shrink_probabilities({'BUY': max(0, body)*(1+max(0, clv)), 'SELL': max(0, -body)*(1+max(0, -clv)), 'NEUTRAL': max(1, rng-abs(body))}, parent, 10),
        'pressure': shrink_probabilities({'BUY': max(0, pressure), 'SELL': max(0, -pressure), 'NEUTRAL': 2}, parent, 12),
        'conditional_history': _hist_probs(selected_hist, parent, 15),
        'alpha_beta': shrink_probabilities({'BUY': max(0, alpha + (beta or alpha))/2, 'SELL': max(0, -(alpha + (beta or alpha))/2), 'NEUTRAL': abs(alpha-(beta or alpha))}, parent, 10),
    }
    losses = {k: 0.66 for k in evidence}
    if not global_hist.empty and 'brier_score' in global_hist:
        recent = pd.to_numeric(global_hist.brier_score, errors='coerce').dropna().tail(100)
        if not recent.empty:
            base = float(np.average(recent, weights=np.exp(np.linspace(-2, 0, len(recent)))))
            losses = {k: max(.05, base * (1 + (i-2)*.02)) for i, k in enumerate(evidence)}
    weights = bounded_weights(losses)
    p = {c: sum(weights[k] * evidence[k][c] for k in evidence) for c in CLASSES}
    s = sum(p.values())
    p = {k: v/s for k, v in p.items()}
    features = {'body_pips': body, 'body_range_ratio': abs(body)/rng, 'close_location': clv, 'pressure_3h_pips': pressure}
    return p, weights, features


def _empirical_wrong_probability(hist: pd.DataFrame, bucket: str, sign: str, session: str) -> float | None:
    if hist.empty or 'correctness' not in hist:
        return None
    h = hist.copy()
    if 'instability_status' in h:
        h = h[h.instability_status == bucket]
    if 'alpha_beta_sign_agreement' in h:
        h = h[h.alpha_beta_sign_agreement == sign]
    if 'session' in h:
        hs = h[h.session == session]
        if len(hs) >= 8:
            h = hs
    values = pd.to_numeric(h.correctness, errors='coerce').dropna()
    return float(1-values.mean()) if len(values) >= 5 else None


def build_and_publish(state: MutableMapping[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    frame, canonical, ledger = _extract_frame(state), _canonical(state), OneHourLedger(db_path)
    if frame.empty:
        payload = {'ok': False, 'status': 'INSUFFICIENT_EVIDENCE', 'reason': 'No completed OHLC frame', 'operational_layer': True, 'production_decision_unchanged': True}
        state[STATE_KEY] = payload
        return payload
    names = {str(c).lower(): c for c in frame.columns}
    tc = names.get('time') or names.get('datetime') or names.get('date')
    oc, hc, lc, cc = names.get('open'), names.get('high'), names.get('low'), names.get('close')
    if tc is None or oc is None or cc is None:
        payload = {'ok': False, 'status': 'INSUFFICIENT_EVIDENCE', 'reason': 'OHLC time/open/close unavailable', 'operational_layer': True}
        state[STATE_KEY] = payload
        return payload
    cols = [x for x in (tc, oc, hc, lc, cc) if x is not None]
    f = frame[cols].copy()
    f['_t'] = pd.to_datetime(f[tc], utc=True, errors='coerce')
    f = f.dropna(subset=['_t']).sort_values('_t').drop_duplicates('_t')
    if f.empty:
        return {'ok': False, 'status': 'INSUFFICIENT_EVIDENCE', 'reason': 'No valid completed timestamps', 'operational_layer': True}
    origin = f.iloc[-1]
    origin_open_time = origin['_t']
    forecast_origin_time = origin_open_time + pd.Timedelta(hours=1)
    target_open_time = forecast_origin_time
    target_close_time = target_open_time + pd.Timedelta(hours=1)
    origin_close = float(origin[cc])
    ledger.settle(f, str(tc))
    hist = ledger.history(365)
    prev = ledger.previous(forecast_origin_time)
    raw = _forecast_from_state(state, origin_close)
    alpha = alpha_pips(raw, origin_close)
    beta = beta_pips(float(prev['raw_forecast']), float(prev['forecast_origin_close'])) if prev and finite_float(prev.get('raw_forecast')) is not None and finite_float(prev.get('forecast_origin_close')) is not None else None
    diffs = pd.to_numeric(hist.get('alpha_beta_difference_pips', pd.Series(dtype=float)), errors='coerce').dropna().tolist()
    rz = robust_z(alpha, beta, diffs)
    sign = sign_agreement(alpha, beta)
    reverse = sign == 'opposite sign'
    tr = ((pd.to_numeric(f[hc], errors='coerce') - pd.to_numeric(f[lc], errors='coerce')) / PIP).dropna().tail(14).tolist() if hc and lc else []
    atr = float(np.mean(tr)) if tr else None
    identity = {k: str(canonical.get(k) or '') for k in ('run_id', 'generation_id', 'snapshot_hash')}
    identity_ok = all(identity.values())
    broker_hour = int(target_open_time.hour)
    session = str(canonical.get('session') or canonical.get('fx_session') or _session_from_hour(broker_hour))
    regime = str(canonical.get('regime') or canonical.get('production_regime') or 'UNAVAILABLE')
    production = str(canonical.get('decision') or canonical.get('production_decision') or 'UNAVAILABLE')
    settled = hist[hist.get('settlement_status', '') == 'SETTLED'] if not hist.empty else hist
    selected_hist, fallback_level = _hierarchical_history(settled, session, regime, broker_hour)
    moves = pd.to_numeric(selected_hist.get('actual_open_to_close_pips', pd.Series(dtype=float)), errors='coerce').dropna().abs().tolist()
    errors = ((pd.to_numeric(selected_hist.get('raw_forecast', pd.Series(dtype=float)), errors='coerce') - pd.to_numeric(selected_hist.get('actual_target_close', pd.Series(dtype=float)), errors='coerce')).abs()/PIP).dropna().tolist()
    cap = safe_endpoint(raw, origin_close, atr, moves, historical_abs_errors_pips=errors, fallback_label=fallback_level)
    raw_path = _raw_path_from_state(state, origin_close, raw)
    safe_path = rescale_operational_path(raw_path, origin_close, cap['active_cap_pips'])
    p, weights, features = _probabilities(f, names, cap['safe_move_pips'], selected_hist, settled, alpha, beta)
    ordered = sorted(p.items(), key=lambda kv: kv[1], reverse=True)
    winner, winp = ordered[0]
    margin = winp - ordered[1][1]
    n, selected_n = len(settled), len(selected_hist)
    briers = pd.to_numeric(settled.get('brier_score', pd.Series(dtype=float)), errors='coerce').dropna()
    brier_mean = float(briers.tail(100).mean()) if not briers.empty else None
    calibration_error = None
    if n >= 10 and {'p_buy','p_sell','p_neutral','correctness'}.issubset(settled.columns):
        conf = settled[['p_buy','p_sell','p_neutral']].apply(pd.to_numeric, errors='coerce').max(axis=1)
        acc = pd.to_numeric(settled.correctness, errors='coerce')
        calibration_error = float(abs(conf.mean() - acc.mean()))
    components = {
        'effective_sample_size': min(1, n/80),
        'proper_score_skill': None if brier_mean is None else max(.01, min(1, 1-brier_mean/(2/3))),
        'calibration': None if calibration_error is None else max(.01, 1-calibration_error),
        'alpha_beta_stability': None if rz is None else max(.01, 1-min(1, rz/3)),
        'probability_margin': min(1, margin/.20),
        'identity_integrity': 1.0 if identity_ok else .01,
        'conditional_support': min(1, selected_n/40),
        'forecast_drift': .75,
    }
    reliability = _geom_reliability(components, {k: 1 for k in components})
    neutral = neutral_threshold_pips(None, .2, .08, atr, 1.0)
    confirmed_prob, confirmed_margin, confirmed_rel = .60, .08, .52
    lean_prob, lean_rel = .50, .42
    severe_unresolved = rz is not None and rz >= 2.5 and reverse
    wait_reason = None
    level = 'WAIT'
    action = 'WAIT'
    if not identity_ok: wait_reason = 'INVALID_CANONICAL_IDENTITY'
    elif abs(cap['safe_move_pips']) < neutral: wait_reason = 'MOVE_BELOW_COSTS_NOISE'
    elif severe_unresolved: wait_reason = 'IRRECONCILABLE_SEVERE_INSTABILITY'
    elif reliability is None or reliability < lean_rel: wait_reason = 'LOW_RELIABILITY'
    elif winner == 'NEUTRAL': wait_reason = 'NEUTRAL_HAS_HIGHEST_PROBABILITY'
    elif winp >= confirmed_prob and margin >= confirmed_margin and reliability >= confirmed_rel:
        level, action = 'CONFIRMED', f'CONFIRMED {winner}'
    elif winp >= lean_prob and reliability >= lean_rel and margin > 0:
        level, action = 'LEAN', f'LEAN {winner}'
    else:
        wait_reason = 'PROBABILITY_OR_MARGIN_BELOW_ACCEPTANCE_THRESHOLD'
    wrong_prob = _empirical_wrong_probability(settled, instability_status(rz), sign, session)
    if wrong_prob is None:
        wrong_prob = 1 - winp
    direction_score = 100*(p['BUY']-p['SELL'])*(reliability or 0)
    compatibility = p.get(production.upper()) if production.upper() in CLASSES else None
    fid = hashlib.sha256(f"EURUSD|H1|{forecast_origin_time.isoformat()}|{identity['snapshot_hash']}".encode()).hexdigest()[:32]
    row = {
        'forecast_id': fid, **identity, 'symbol': 'EURUSD', 'timeframe': 'H1',
        'broker_candle_time': forecast_origin_time.isoformat(), 'forecast_origin_time': forecast_origin_time.isoformat(),
        'target_h1_open_time': target_open_time.isoformat(), 'target_h1_close_time': target_close_time.isoformat(),
        'forecast_origin_close': origin_close, 'raw_forecast': raw, 'safe_forecast': cap['safe_prediction'],
        'alpha_pips': alpha, 'beta_pips': beta, 'alpha_beta_difference_pips': abs(alpha-beta) if beta is not None else None,
        'alpha_beta_sign_agreement': sign, 'direction_reversal': int(reverse), 'robust_z': rz, 'instability_status': instability_status(rz),
        'p_buy': p['BUY'], 'p_sell': p['SELL'], 'p_neutral': p['NEUTRAL'], 'model_weights': weights,
        'confirmation_action': action, 'confirmation_level': level, 'wait_reason': wait_reason,
        'reliability': reliability, 'reliability_components': components, 'probability_margin': margin, 'direction_score': direction_score,
        'session': session, 'overlap': 'OVERLAP' if 'OVERLAP' in session.upper() else 'NO', 'broker_hour': broker_hour,
        'production_regime': regime, 'production_action': production, 'compatibility_score': compatibility,
        'transition_risk_state': 'HIGH' if severe_unresolved else 'NORMAL', 'data_quality_state': 'LOW EVIDENCE' if n < 20 else 'AVAILABLE',
        'spread_pips': None, 'estimated_cost_pips': .2, 'neutral_threshold_pips': neutral,
        'expected_open_close_pips': cap['safe_move_pips'], 'active_cap_pips': cap['active_cap_pips'], 'atr_cap_pips': cap['atr_cap_pips'],
        'session_tail_cap_pips': cap['session_tail_cap_pips'], 'cap_source': cap['cap_source'], 'capped': int(cap['capped']),
        'pips_removed_by_cap': cap['pips_removed_by_cap'], 'wrong_direction_probability': wrong_prob,
        'origin_payload': {'cap': cap, 'features': features, 'raw_path': raw_path, 'safe_path': safe_path,
                           'fallback_level': fallback_level, 'selected_thresholds': {'confirmed_probability': confirmed_prob,
                           'confirmed_margin': confirmed_margin, 'confirmed_reliability': confirmed_rel,
                           'lean_probability': lean_prob, 'lean_reliability': lean_rel},
                           'production_decision_unchanged': True, 'protected_central_path_unchanged': True},
    }
    inserted = ledger.insert_origin(row)
    history = ledger.history(25)
    accepted = settled[settled.confirmation_action.astype(str).str.contains('BUY|SELL', regex=True)] if not settled.empty and 'confirmation_action' in settled else pd.DataFrame()
    validation = {
        'settled_n': n, 'accepted_n': len(accepted), 'coverage': len(accepted)/n if n else None,
        'accepted_accuracy': float(pd.to_numeric(accepted.correctness, errors='coerce').mean()) if len(accepted) else None,
        'baseline_accuracy': float(settled.actual_direction.value_counts(normalize=True).max()) if n and 'actual_direction' in settled else None,
        'mean_brier': brier_mean,
        'mean_log_loss': float(pd.to_numeric(settled.get('log_loss', pd.Series(dtype=float)), errors='coerce').dropna().mean()) if n else None,
        'calibration_error': calibration_error,
    }
    payload = {'ok': True, 'status': 'OPERATIONAL_CONFIRMATION', 'operational_layer': True, 'shadow_only': False,
               'production_decision_unchanged': True, 'protected_central_path_unchanged': True,
               'current': row, 'history': history, 'validation': validation, 'inserted': inserted,
               'settled_count': n, 'version': VERSION}
    state[STATE_KEY] = payload
    return payload
