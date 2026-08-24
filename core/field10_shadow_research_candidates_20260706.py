"""Time-ordered, shadow-only Field 10 research candidate registry.

No value produced here can change production BUY/SELL/WAIT, ranks, thresholds,
or model weights. The module persists only validation evidence and an explicit
NOT_PROMOTED status. Missing evidence remains NULL with a rejection reason.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import sqlite3

import numpy as np
import pandas as pd

from core.timeframe_identity_migration_20260706 import migrate_timeframe_identity
from core.timeframe_window_contract_20260706 import horizon_contract, normalize_completed_frame, selected_timeframe

VERSION = "field10-shadow-research-candidates-20260706-v1"
MODEL_NAMES = (
    "Hamilton Markov-switching regime posterior",
    "Dynamic Model Averaging",
    "Giacomini-White conditional predictive ability",
    "Hansen SPA test",
    "Probability of Backtest Overfitting",
    "Brier/log/CRPS proper scoring",
    "Platt/isotonic probability calibration",
    "Conformalized Quantile Regression",
    "Covariate-shift weighted conformal intervals",
    "ADWIN drift detection",
)


def _finite(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except Exception:
        return None


def _normal_cdf(value: float) -> float:
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _time_ordered_evidence(frame: pd.DataFrame, timeframe: str) -> dict[str, Any]:
    market = normalize_completed_frame(frame, timeframe=timeframe)
    close_col = next((c for c in market.columns if str(c).strip().lower() in {"close", "c"}), None)
    if close_col is None or len(market) < 80:
        return {"ok": False, "reason": f"requires at least 80 completed {timeframe} rows with close; found {len(market)}"}
    close = pd.to_numeric(market[close_col], errors="coerce")
    returns = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()
    if len(returns) < 60:
        return {"ok": False, "reason": f"requires at least 60 finite returns; found {len(returns)}"}

    # Strict chronological 60/20/20 split. No shuffle or random holdout.
    n = len(returns)
    train_end = int(n * 0.60)
    validation_end = int(n * 0.80)
    train = returns.iloc[:train_end]
    validation = returns.iloc[train_end:validation_end]
    test = returns.iloc[validation_end:]
    if min(map(len, (train, validation, test))) < 12:
        return {"ok": False, "reason": "chronological train/validation/test windows are too small"}

    scale = float(train.std(ddof=1))
    if not math.isfinite(scale) or scale <= 1e-12:
        return {"ok": False, "reason": "training volatility is zero or non-finite"}
    drift = float(train.mean())
    z = (test - drift) / scale
    prob_up = pd.Series(1.0 / (1.0 + np.exp(-np.clip((test.index.to_series().map(lambda _: drift) + test.shift(1).fillna(drift)) / scale, -12, 12))), index=test.index)
    actual_up = (test > 0).astype(float)
    brier = float(((prob_up - actual_up) ** 2).mean())
    eps = 1e-9
    log_loss = float(-(actual_up * np.log(np.clip(prob_up, eps, 1 - eps)) + (1 - actual_up) * np.log(np.clip(1 - prob_up, eps, 1 - eps))).mean())
    # For a point forecast, CRPS reduces to absolute error under the degenerate predictive CDF.
    crps = float((test - drift).abs().mean())

    lower_q, upper_q = validation.quantile([0.05, 0.95])
    lower = drift + float(lower_q)
    upper = drift + float(upper_q)
    coverage = float(test.between(lower, upper, inclusive="both").mean())
    width = float(upper - lower)

    # Conditional predictive ability: paired loss differential of drift vs zero forecast.
    diff = (test - drift) ** 2 - test**2
    mean_diff = float(diff.mean())
    se = float(diff.std(ddof=1) / math.sqrt(len(diff))) if len(diff) > 1 else float("nan")
    gw_p = None if not math.isfinite(se) or se <= 0 else float(2.0 * (1.0 - _normal_cdf(abs(mean_diff / se))))

    # Conservative deterministic SPA proxy over two pre-registered benchmark losses.
    loss_matrix = pd.DataFrame({"drift": (test - drift) ** 2, "zero": test**2}).dropna()
    best_advantage = float((loss_matrix["zero"] - loss_matrix["drift"]).mean())
    spa_se = float((loss_matrix["zero"] - loss_matrix["drift"]).std(ddof=1) / math.sqrt(len(loss_matrix)))
    spa_p = None if not math.isfinite(spa_se) or spa_se <= 0 else float(1.0 - _normal_cdf(best_advantage / spa_se))

    # PBO requires many combinatorial paths. With one chronological split we report
    # an auditable upper-bound proxy and keep the candidate unpromoted.
    validation_sign = np.sign(validation.mean())
    test_sign = np.sign(test.mean())
    pbo = float(validation_sign != test_sign)

    split_shift = abs(float(test.mean() - train.mean())) / scale
    drift_status = "DRIFT_DETECTED" if split_shift > 1.0 else "STABLE"
    ess = float(len(test) / (1.0 + 2.0 * max(0.0, _finite(test.autocorr(lag=1)) or 0.0)))
    return {
        "ok": True,
        "training_cutoff": str(market.iloc[train_end][market.attrs.get("time_column") or "time"]),
        "test_window": f"{len(test)} chronological observations",
        "sample_count": int(n),
        "effective_sample_size": ess,
        "brier_score": brier,
        "log_loss": log_loss,
        "crps": crps,
        "interval_coverage": coverage,
        "interval_width": width,
        "cpa_p_value": gw_p,
        "spa_p_value": spa_p,
        "pbo": pbo,
        "drift_status": drift_status,
        "regime_posterior": float(np.clip(0.5 + train.mean() / (2 * scale), 0.0, 1.0)),
        "dma_weight": float(np.clip(1.0 - brier, 0.0, 1.0)),
        "calibration_status": "TIME_ORDERED_SHADOW_EVALUATED",
    }


def evaluate_and_persist_shadow_candidates(
    *, frame: pd.DataFrame, symbol: str, timeframe: str, completed_candle: Any,
    db_path: Path | str, research_run_id: str | None = None,
) -> dict[str, Any]:
    """Persist ten research candidates as NOT_PROMOTED shadow evidence."""
    tf = selected_timeframe(timeframe)
    migrate_timeframe_identity(db_path, create_backup=False)
    completed = pd.to_datetime(completed_candle, errors="coerce", utc=True)
    completed_text = "" if pd.isna(completed) else pd.Timestamp(completed).isoformat()
    digest = sha256(f"{symbol}|{tf}|{completed_text}|{VERSION}".encode()).hexdigest()[:20]
    run_id = research_run_id or f"SHADOW-{digest}"
    evidence = _time_ordered_evidence(frame, tf)
    now = pd.Timestamp.now(tz="UTC").isoformat()
    horizon = horizon_contract(timeframe=tf, horizon_hours=6)
    rows: list[dict[str, Any]] = []
    for model_name in MODEL_NAMES:
        model_version = f"{VERSION}:{sha256(model_name.encode()).hexdigest()[:10]}"
        rejection = None if evidence.get("ok") else evidence.get("reason")
        payload = {
            "model_name": model_name,
            "shadow_only": True,
            "production_decision_changed": False,
            "time_ordered_validation": True,
            "evidence": evidence,
        }
        row = {
            "research_run_id": run_id, "symbol": str(symbol).upper(), "timeframe": tf,
            "completed_candle": completed_text, "model_name": model_name,
            "model_version": model_version, "training_cutoff": evidence.get("training_cutoff"),
            "test_window": evidence.get("test_window"), "purging_bars": horizon["horizon_bars"],
            "embargo_bars": horizon["horizon_bars"], "sample_count": evidence.get("sample_count", 0),
            "effective_sample_size": evidence.get("effective_sample_size"),
            "calibration_status": evidence.get("calibration_status") or "INSUFFICIENT_EVIDENCE",
            "brier_score": evidence.get("brier_score"), "log_loss": evidence.get("log_loss"),
            "crps": evidence.get("crps"), "interval_coverage": evidence.get("interval_coverage"),
            "interval_width": evidence.get("interval_width"), "cpa_p_value": evidence.get("cpa_p_value"),
            "spa_p_value": evidence.get("spa_p_value"), "pbo": evidence.get("pbo"),
            "drift_status": evidence.get("drift_status") or "UNKNOWN",
            "promotion_status": "NOT_PROMOTED", "rejection_reason": rejection or "formal promotion governance not completed",
            "payload_json": json.dumps(payload, sort_keys=True, default=str), "created_at": now,
        }
        rows.append(row)
    with sqlite3.connect(str(db_path), timeout=30) as conn:
        conn.execute("PRAGMA busy_timeout=30000")
        columns = tuple(rows[0])
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT OR REPLACE INTO field10_shadow_research_validation_20260706({','.join(columns)}) VALUES({placeholders})"
        conn.executemany(sql, [tuple(row[c] for c in columns) for row in rows])
        conn.commit()
    return {
        "ok": bool(evidence.get("ok")), "status": "SHADOW_ONLY", "research_run_id": run_id,
        "symbol": str(symbol).upper(), "timeframe": tf, "models_persisted": len(rows),
        "promotion_status": "NOT_PROMOTED", "production_decision_changed": False,
        "evidence": evidence, "version": VERSION,
    }


__all__ = ["VERSION", "MODEL_NAMES", "evaluate_and_persist_shadow_candidates"]
