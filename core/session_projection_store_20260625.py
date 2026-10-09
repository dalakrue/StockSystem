
from __future__ import annotations

from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from core.session_context_20260625 import detect_session_from_utc


def _f(value: Any) -> float | None:
    try:
        out = float(value)
        return out if np.isfinite(out) else None
    except Exception:
        return None



def _finite_values(values: Any) -> pd.Series:
    """Coerce evidence to the finite numeric observations only."""
    series = pd.to_numeric(pd.Series(values), errors="coerce")
    numeric = series.to_numpy(dtype=float, na_value=np.nan)
    return series[np.isfinite(numeric)]


def _finite_mean(values: Any) -> float:
    """Preserve unavailable evidence as NaN without empty-slice warnings."""
    finite = _finite_values(values)
    return float(finite.mean()) if not finite.empty else np.nan


def _finite_median(values: Any) -> float:
    """Preserve unavailable evidence as NaN without all-NaN warnings."""
    finite = _finite_values(values)
    return float(finite.median()) if not finite.empty else np.nan


def _choose_column(frame: pd.DataFrame, names: Iterable[str]) -> str | None:
    lowered = {str(c).lower().replace(' ', '_'): c for c in frame.columns}
    for name in names:
        key = str(name).lower().replace(' ', '_')
        if key in lowered:
            return lowered[key]
    for column in frame.columns:
        text = str(column).lower().replace(' ', '_')
        if any(str(name).lower().replace(' ', '_') in text for name in names):
            return str(column)
    return None


def settled_projection_records(state: Mapping[str, Any]) -> pd.DataFrame:
    candidates: list[pd.DataFrame] = []
    for key in ('dv_pp_bt_hist', 'prediction_vs_actual_history_df', 'prediction_history_df', 'full_metric_history_df_20260618'):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            candidates.append(value.copy())
    if not candidates:
        return pd.DataFrame()
    base = max(candidates, key=len).copy()
    time_col = _choose_column(base, ('forecast_origin_time', 'broker_time', 'time', 'timestamp', 'date'))
    actual_col = _choose_column(base, ('actual', 'actual_price', 'actual_close', 'realized', 'result'))
    pred_col = _choose_column(base, ('predicted', 'predicted_price', 'forecast', 'central_path', 'session_prediction'))
    lower_col = _choose_column(base, ('lower', 'lower_bound', 'blue'))
    upper_col = _choose_column(base, ('upper', 'upper_bound', 'red'))
    horizon_col = _choose_column(base, ('horizon', 'forecast_horizon', 'step'))
    current_col = _choose_column(base, ('current_price', 'current', 'anchor_price', 'open', 'close'))
    if time_col is None or pred_col is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        'forecast_origin_time': pd.to_datetime(base[time_col], errors='coerce', utc=True),
        'base_prediction': pd.to_numeric(base[pred_col], errors='coerce'),
        'actual': pd.to_numeric(base[actual_col], errors='coerce') if actual_col else np.nan,
        'lower': pd.to_numeric(base[lower_col], errors='coerce') if lower_col else np.nan,
        'upper': pd.to_numeric(base[upper_col], errors='coerce') if upper_col else np.nan,
        'horizon': pd.to_numeric(base[horizon_col], errors='coerce').fillna(1).astype(int) if horizon_col else 1,
        'current_price': pd.to_numeric(base[current_col], errors='coerce') if current_col else np.nan,
    }).dropna(subset=['forecast_origin_time', 'base_prediction'])
    if out.empty:
        return out
    sessions = []
    for ts in out['forecast_origin_time']:
        detected, _, _ = detect_session_from_utc(pd.Timestamp(ts).to_pydatetime())
        sessions.append(detected)
    out['session'] = sessions
    out['settlement_status'] = np.where(out['actual'].notna(), 'SETTLED', 'PENDING')
    out['base_error'] = np.where(out['actual'].notna(), out['base_prediction'] - out['actual'], np.nan)
    out['direction_correct'] = np.where(
        out['actual'].notna() & out['current_price'].notna(),
        ((out['base_prediction'] - out['current_price']) >= 0) == ((out['actual'] - out['current_price']) >= 0),
        np.nan,
    )
    out['coverage'] = np.where(
        out['actual'].notna() & out['lower'].notna() & out['upper'].notna(),
        (out['actual'] >= out['lower']) & (out['actual'] <= out['upper']),
        np.nan,
    )
    return out.sort_values('forecast_origin_time', ascending=False).reset_index(drop=True)


def compute_session_statistics(records: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(records, pd.DataFrame) or records.empty:
        return pd.DataFrame(columns=['session', 'horizon', 'sample_count'])
    settled = records.loc[records['settlement_status'] == 'SETTLED'].copy()
    if settled.empty:
        return pd.DataFrame(columns=['session', 'horizon', 'sample_count'])
    groups = []
    for (session, horizon), part in settled.groupby(['session', 'horizon'], dropna=False):
        n = int(len(part))
        err = pd.to_numeric(part['base_error'], errors='coerce')
        cov = pd.to_numeric(part['coverage'], errors='coerce')
        dc = pd.to_numeric(part['direction_correct'], errors='coerce')
        abs_err = err.abs()
        mean_abs_err = _finite_mean(abs_err)
        mean_squared_err = _finite_mean(np.square(err))
        weights = np.exp(-np.linspace(0, 1, len(part))[::-1])
        weights = weights / weights.sum() if weights.sum() else np.ones(len(part)) / max(len(part), 1)
        ewma_err = float(np.nansum(err.fillna(0).to_numpy() * weights)) if n else np.nan
        groups.append({
            'session': str(session),
            'horizon': int(horizon),
            'sample_count': n,
            'median_signed_residual': _finite_median(err),
            'ewma_signed_residual': ewma_err,
            'mae': mean_abs_err,
            'rmse': float(np.sqrt(mean_squared_err)) if np.isfinite(mean_squared_err) else np.nan,
            'direction_accuracy': _finite_mean(dc),
            'actionable_direction_accuracy': _finite_mean(dc),
            'interval_coverage': _finite_mean(cov),
            'average_interval_width': _finite_mean((part['upper'] - part['lower']).abs()),
            'recent_drift_status': 'DRIFT_WARNING' if abs(ewma_err) > (mean_abs_err if np.isfinite(mean_abs_err) else 0.0) else 'STABLE',
            'last_update_time': str(part['forecast_origin_time'].max()),
        })
    return pd.DataFrame(groups)


__all__ = ['settled_projection_records', 'compute_session_statistics']
