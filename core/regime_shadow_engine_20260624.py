"""Shadow changepoint/regime-duration evidence for Field 3 and Morning."""
from __future__ import annotations
from typing import Any, Mapping
import math
import numpy as np
import pandas as pd

VERSION = "regime-shadow-engine-20260624-v1"


def _num(s: Any) -> pd.Series:
    return pd.to_numeric(pd.Series(s), errors="coerce").astype(float)


def bocpd_shadow(frame: pd.DataFrame, *, price_col: str = "close", min_points: int = 24) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame) or frame.empty or price_col not in frame:
        return {"status": "INSUFFICIENT EVIDENCE", "version": VERSION}
    p = _num(frame[price_col]).dropna()
    if len(p) < min_points:
        return {"status": "INSUFFICIENT EVIDENCE", "sample_count": int(len(p)), "version": VERSION}
    r = np.log(p).diff().dropna().to_numpy(dtype=float)
    w = min(96, max(12, len(r)//3))
    recent = r[-w:]; past = r[:-w] if len(r) > w else r
    sigma = max(float(np.nanstd(past)), 1e-12)
    mean_shift = abs(float(np.nanmean(recent) - np.nanmean(past))) / sigma
    vol_shift = abs(float(np.nanstd(recent) - np.nanstd(past))) / sigma
    raw = 1.0 - math.exp(-0.5 * (mean_shift + 0.5 * vol_shift))
    cp = float(max(0.0, min(1.0, raw)))
    run_length = int(w if cp < 0.35 else max(1, w * (1 - cp)))
    return {"status": "OK", "posterior_changepoint_probability": cp, "expected_run_length": run_length, "median_run_length": run_length, "transition_warning": bool(cp >= 0.35), "transition_confirmed": bool(cp >= 0.65), "evidence_strength": "HIGH" if cp >= 0.65 else "MEDIUM" if cp >= 0.35 else "LOW", "last_probable_change_time": str(frame.index[-run_length] if len(frame.index) >= run_length else frame.index[0]), "sample_count": int(len(p)), "version": VERSION}


def explicit_duration_shadow(regime_history: pd.DataFrame | list[Mapping[str, Any]], *, regime_col: str = "regime", time_col: str = "time", min_completed: int = 5) -> dict[str, Any]:
    df = pd.DataFrame(regime_history)
    if df.empty or regime_col not in df:
        return {"status": "INSUFFICIENT EVIDENCE", "version": VERSION}
    regs = df[regime_col].astype(str).replace("", np.nan).dropna().tolist()
    if not regs:
        return {"status": "INSUFFICIENT EVIDENCE", "version": VERSION}
    completed: list[tuple[str,int]] = []
    cur = regs[0]; length = 1
    for r in regs[1:]:
        if r == cur: length += 1
        else: completed.append((cur, length)); cur = r; length = 1
    current_regime = cur; current_age = length
    same = [d for r, d in completed if r == current_regime]
    if len(same) < min_completed:
        return {"status": "INSUFFICIENT EVIDENCE", "current_regime_age": int(current_age), "completed_samples": int(len(same)), "version": VERSION}
    arr = np.asarray(same, dtype=float)
    exp_total = float(np.mean(arr)); remaining = float(max(0.0, exp_total - current_age))
    percentile = float((arr <= current_age).mean())
    # Empirical transition probability approximation by horizon.
    probs = {f"H{h}": float(min(1.0, max(0.0, (current_age + h - np.median(arr)) / max(np.std(arr), 1.0) * 0.15 + 0.5))) for h in (1,3,6)}
    return {"status": "OK", "current_regime": current_regime, "current_regime_age": int(current_age), "expected_total_duration": exp_total, "expected_remaining_duration": remaining, "duration_percentile": percentile, "transition_probabilities": probs, "candidate_distribution": "empirical-discrete-shadow", "completed_samples": int(len(same)), "version": VERSION}


__all__ = ["bocpd_shadow", "explicit_duration_shadow", "VERSION"]
