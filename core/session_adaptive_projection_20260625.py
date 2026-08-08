
from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from core.publication_identity_20260625 import freeze_publication_identity
from core.session_context_20260625 import resolve_session_contract
from core.session_projection_store_20260625 import compute_session_statistics, settled_projection_records


def _f(value: Any) -> float | None:
    try:
        out = float(value)
        return out if np.isfinite(out) else None
    except Exception:
        return None


def _atr14_h1(state: Mapping[str, Any]) -> float:
    for key in ('atr_14_h1_20260625', 'atr_14_h1', 'atr'):
        value = _f(state.get(key))
        if value is not None and value > 0:
            return value
    df = state.get('dv_pp_df')
    if isinstance(df, pd.DataFrame) and not df.empty:
        cols = {str(c).lower(): c for c in df.columns}
        if {'high', 'low', 'close'} <= set(cols):
            hi = pd.to_numeric(df[cols['high']], errors='coerce')
            lo = pd.to_numeric(df[cols['low']], errors='coerce')
            cl = pd.to_numeric(df[cols['close']], errors='coerce').shift(1)
            tr = pd.concat([(hi - lo).abs(), (hi - cl).abs(), (lo - cl).abs()], axis=1).max(axis=1)
            atr = float(tr.tail(14).mean()) if tr.notna().any() else 0.0
            return max(atr, 0.0001)
    return 0.0010



def _market_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    """Return one bounded completed-H1 view without copying every session frame."""
    frame = None
    for key in ('canonical_completed_ohlc_df_20260617', 'calculation_staging_ohlc_df_20260617', 'dv_pp_df', 'last_df'):
        candidate = state.get(key)
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            frame = candidate
            break
    if frame is None:
        return pd.DataFrame()
    normalized = {str(c).strip().lower().replace('_', ' '): c for c in frame.columns}
    time_col = next((normalized.get(name) for name in ('time', 'datetime', 'timestamp', 'date') if normalized.get(name) is not None), None)
    close_col = normalized.get('close') or normalized.get('c')
    if time_col is None or close_col is None:
        return pd.DataFrame()
    out = pd.DataFrame({
        'time': pd.to_datetime(frame[time_col], errors='coerce', utc=True),
        'close': pd.to_numeric(frame[close_col], errors='coerce'),
    }).dropna().sort_values('time').drop_duplicates('time', keep='last')
    return out.tail(2400).reset_index(drop=True)


def _session_codes(times: pd.Series) -> pd.Series:
    """Vectorized DST-aware classification matching session_context priority."""
    utc = pd.to_datetime(times, errors='coerce', utc=True)
    london = utc.dt.tz_convert('Europe/London')
    new_york = utc.dt.tz_convert('America/New_York')
    sydney = utc.dt.tz_convert('Australia/Sydney')
    tokyo = utc.dt.tz_convert('Asia/Tokyo')
    london_open = london.dt.hour.ge(8) & london.dt.hour.lt(17)
    new_york_open = new_york.dt.hour.ge(8) & new_york.dt.hour.lt(17)
    sydney_open = sydney.dt.hour.ge(7) & sydney.dt.hour.lt(16)
    tokyo_open = tokyo.dt.hour.ge(9) & tokyo.dt.hour.lt(18)
    values = np.full(len(utc), 'GLOBAL_FALLBACK', dtype=object)
    # Match session_context.detect_session_from_utc priority exactly.  This is
    # shadow-only classification over completed candles and never rewrites the
    # protected historical session or production decision.
    values[sydney_open.to_numpy()] = 'SYDNEY'
    values[tokyo_open.to_numpy()] = 'TOKYO'
    values[new_york_open.to_numpy()] = 'NEW_YORK'
    values[london_open.to_numpy()] = 'LONDON'
    values[(tokyo_open & sydney_open).to_numpy()] = 'TOKYO_SYDNEY_OVERLAP'
    values[(tokyo_open & london_open).to_numpy()] = 'TOKYO_LONDON_OVERLAP'
    values[(london_open & new_york_open).to_numpy()] = 'LONDON_NEW_YORK_OVERLAP'
    return pd.Series(values, index=times.index, dtype='object')


def compute_intraday_session_priors(state: Mapping[str, Any], horizons: list[int]) -> pd.DataFrame:
    """Leakage-safe conditional H1 drift priors from completed candles only.

    Forward moves are evaluated only where the future close already exists.  The
    current incomplete/unknown target is never used.  Results are a relative
    session effect (session median minus global median), not a new price engine.
    """
    market = _market_frame(state)
    if market.empty:
        return pd.DataFrame()
    market['session'] = _session_codes(market['time'])
    rows: list[dict[str, Any]] = []
    close = market['close'].astype(float)
    for horizon in sorted({max(1, int(h)) for h in horizons}):
        # Explicit completed-window alignment avoids any centered/backfilled or
        # negative-shift construction while retaining the same forward-move pairs.
        if len(close) <= horizon:
            continue
        forward_values = close.iloc[horizon:].to_numpy(dtype=float) - close.iloc[:-horizon].to_numpy(dtype=float)
        valid = market.iloc[:-horizon].copy()
        valid['forward_move'] = forward_values
        valid = valid.dropna(subset=['forward_move'])
        if valid.empty:
            continue
        global_median = float(valid['forward_move'].median())
        for session, group in valid.groupby('session', sort=False):
            values = pd.to_numeric(group['forward_move'], errors='coerce').dropna()
            if values.empty:
                continue
            rows.append({
                'horizon': horizon,
                'session': str(session),
                'prior_sample_count': int(len(values)),
                'session_median_move': float(values.median()),
                'global_median_move': global_median,
                'relative_session_move': float(values.median() - global_median),
                'prior_mad': float((values - values.median()).abs().median()),
            })
    return pd.DataFrame(rows)



def compute_session_microstructure_profiles(state: Mapping[str, Any], horizons: list[int]) -> pd.DataFrame:
    """Completed-candle session profiles used only by the additive shadow path.

    The profile makes session changes observable through three independent,
    leakage-safe channels: directional drift, realized range/volatility and
    directional persistence. All statistics use completed origin/target pairs.
    """
    market = _market_frame(state)
    if market.empty:
        return pd.DataFrame()
    source = None
    for key in ('canonical_completed_ohlc_df_20260617', 'calculation_staging_ohlc_df_20260617', 'dv_pp_df', 'last_df'):
        candidate = state.get(key)
        if isinstance(candidate, pd.DataFrame) and not candidate.empty:
            source = candidate
            break
    if source is None:
        return pd.DataFrame()
    cols = {str(c).strip().lower(): c for c in source.columns}
    if not {'high','low','close'} <= set(cols):
        return pd.DataFrame()
    profile = market.copy()
    aligned = source.copy()
    time_col = next((cols.get(k) for k in ('time','datetime','timestamp','date') if cols.get(k) is not None), None)
    if time_col is None:
        return pd.DataFrame()
    aligned = pd.DataFrame({
        'time': pd.to_datetime(source[time_col], errors='coerce', utc=True),
        'high': pd.to_numeric(source[cols['high']], errors='coerce'),
        'low': pd.to_numeric(source[cols['low']], errors='coerce'),
        'close2': pd.to_numeric(source[cols['close']], errors='coerce'),
    }).dropna().sort_values('time').drop_duplicates('time', keep='last')
    profile = profile.merge(aligned, on='time', how='inner')
    if profile.empty:
        return pd.DataFrame()
    profile['session'] = _session_codes(profile['time'])
    profile['range'] = (profile['high'] - profile['low']).abs()
    profile['ret1'] = profile['close'].diff()
    global_range = float(profile['range'].median()) if profile['range'].notna().any() else 0.0
    rows=[]
    for horizon in sorted({max(1,int(h)) for h in horizons}):
        if len(profile) <= horizon:
            continue
        valid=profile.iloc[:-horizon].copy()
        valid['forward_move']=profile['close'].iloc[horizon:].to_numpy(float)-profile['close'].iloc[:-horizon].to_numpy(float)
        valid['direction_persist']=np.sign(valid['ret1'].fillna(0).to_numpy()) == np.sign(valid['forward_move'].to_numpy())
        valid['false_breakout']=((valid['forward_move'].abs() < valid['range'] * 0.35) & (valid['range'] > valid['range'].median())).astype(float)
        global_abs=float(valid['forward_move'].abs().median()) if not valid.empty else 0.0
        global_persist=float(valid['direction_persist'].mean()) if not valid.empty else 0.5
        for session,grp in valid.groupby('session',sort=False):
            n=len(grp)
            if not n:
                continue
            med_move=float(grp['forward_move'].median())
            abs_move=float(grp['forward_move'].abs().median())
            range_med=float(grp['range'].median())
            rows.append({
                'horizon':horizon,'session':str(session),'profile_sample_count':int(n),
                'median_forward_move':med_move,
                'relative_abs_move':abs_move-global_abs,
                'volatility_ratio':float(np.clip(range_med/max(global_range,1e-12),0.55,1.80)),
                'directional_persistence':float(grp['direction_persist'].mean()),
                'relative_persistence':float(grp['direction_persist'].mean()-global_persist),
                'false_breakout_frequency':float(grp['false_breakout'].mean()),
            })
    return pd.DataFrame(rows)

def session_evidence_tier(sample_count: int) -> str:
    if sample_count >= 60:
        return 'SESSION_CALIBRATED'
    if sample_count >= 30:
        return 'SESSION_SHRUNK'
    if sample_count >= 10:
        return 'GLOBAL_DOMINANT'
    return 'GLOBAL_FALLBACK'


def build_session_adjusted_projection(state: Mapping[str, Any], canonical: Mapping[str, Any], base_horizons: pd.DataFrame, selected_session: str | None = None) -> dict[str, Any]:
    identity = freeze_publication_identity(state, canonical)
    session_contract = resolve_session_contract(state, canonical, selected_session)
    records = settled_projection_records(state)
    stats = compute_session_statistics(records)
    atr14 = _atr14_h1(state)
    requested_horizons = []
    if isinstance(base_horizons, pd.DataFrame) and not base_horizons.empty:
        for value in base_horizons.get('horizon', base_horizons.get('Horizon', pd.Series(dtype=float))):
            try:
                requested_horizons.append(int(value))
            except Exception:
                pass
    intraday_priors = compute_intraday_session_priors(state, requested_horizons)
    micro_profiles = compute_session_microstructure_profiles(state, requested_horizons)
    result_rows = []
    if not isinstance(base_horizons, pd.DataFrame) or base_horizons.empty:
        return {
            'contract': session_contract.to_dict(),
            'identity': identity,
            'horizons': pd.DataFrame(),
            'history': pd.DataFrame(),
            'stats': stats,
            'intraday_priors': intraday_priors,
            'microstructure_profiles': micro_profiles,
        }
    for _, row in base_horizons.iterrows():
        horizon = int(row.get('horizon') or row.get('Horizon') or 1)
        base_prediction = _f(row.get('central_price') or row.get('Base Central Path') or row.get('base_prediction'))
        current_price = _f(row.get('current_price') or row.get('Current Price'))
        lower = _f(row.get('lower_bound') or row.get('Lower Bound'))
        upper = _f(row.get('upper_bound') or row.get('Upper Bound'))
        global_part = stats.loc[stats['horizon'].eq(horizon)] if not stats.empty else pd.DataFrame()
        session_part = stats.loc[stats['horizon'].eq(horizon) & stats['session'].eq(session_contract.selected_session)] if not stats.empty else pd.DataFrame()
        global_bias = float(global_part['median_signed_residual'].mean()) if not global_part.empty else 0.0
        session_bias = float(session_part['median_signed_residual'].mean()) if not session_part.empty else global_bias
        n = int(session_part['sample_count'].max()) if not session_part.empty else 0
        strength = n / (n + 30.0)
        shrunk_residual_bias = strength * session_bias + (1.0 - strength) * global_bias
        prior_part = intraday_priors.loc[
            intraday_priors['horizon'].eq(horizon) & intraday_priors['session'].eq(session_contract.selected_session)
        ] if not intraday_priors.empty else pd.DataFrame()
        prior_n = int(prior_part['prior_sample_count'].max()) if not prior_part.empty else 0
        prior_strength = prior_n / (prior_n + 60.0)
        relative_session_move = float(prior_part['relative_session_move'].median()) if not prior_part.empty else 0.0
        # Residual correction remains primary when settled forecasts exist.  The
        # completed-H1 intraday prior supplies a bounded session difference when
        # a selected session has little or no settled projection evidence.
        profile_part = micro_profiles.loc[
            micro_profiles['horizon'].eq(horizon) & micro_profiles['session'].eq(session_contract.selected_session)
        ] if not micro_profiles.empty else pd.DataFrame()
        profile_n = int(profile_part['profile_sample_count'].max()) if not profile_part.empty else 0
        profile_strength = profile_n / (profile_n + 80.0)
        volatility_ratio = float(profile_part['volatility_ratio'].median()) if not profile_part.empty else 1.0
        relative_persistence = float(profile_part['relative_persistence'].median()) if not profile_part.empty else 0.0
        false_breakout_frequency = float(profile_part['false_breakout_frequency'].median()) if not profile_part.empty else 0.5

        # Session shape term: completed-candle direction persistence changes the
        # slope, while session volatility changes its magnitude. A high false-
        # breakout rate dampens the adjustment. This remains shadow-only.
        base_move = 0.0 if base_prediction is None or current_price is None else base_prediction - current_price
        persistence_multiplier = float(np.clip(1.0 + 1.5 * relative_persistence, 0.65, 1.35))
        breakout_discount = float(np.clip(1.10 - 0.70 * false_breakout_frequency, 0.55, 1.0))
        session_shape_move = base_move * (volatility_ratio * persistence_multiplier * breakout_discount - 1.0)
        horizon_gain = float(np.sqrt(max(1, horizon)))
        combined_bias = (shrunk_residual_bias + prior_strength * relative_session_move + profile_strength * session_shape_move) * horizon_gain
        bound = 0.35 * atr14
        bias_correction = float(np.clip(combined_bias, -bound, bound))
        adjusted = None if base_prediction is None else base_prediction + bias_correction
        tier = session_evidence_tier(n)
        if lower is not None and adjusted is not None:
            adjusted = max(lower, adjusted)
        if upper is not None and adjusted is not None:
            adjusted = min(upper, adjusted)
        result_rows.append({
            'horizon': horizon,
            'Selected Session': session_contract.selected_session,
            'selected_session': session_contract.selected_session,
            'sample_count': n,
            'session_weight': round(strength, 6),
            'intraday_prior_sample_count': prior_n,
            'intraday_prior_weight': round(prior_strength, 6),
            'microstructure_sample_count': profile_n,
            'microstructure_weight': round(profile_strength, 6),
            'volatility_ratio': volatility_ratio,
            'directional_persistence_delta': relative_persistence,
            'false_breakout_frequency': false_breakout_frequency,
            'relative_session_move': relative_session_move,
            'evidence_tier': tier if n else ('INTRADAY_PRIOR' if prior_n >= 30 else tier),
            'Base Prediction': base_prediction,
            'Session Prediction': adjusted,
            'base_prediction': base_prediction,
            'session_prediction': adjusted,
            'current_price': current_price,
            'lower': lower,
            'upper': upper,
            'session_direction_accuracy': float(session_part['direction_accuracy'].mean()) if not session_part.empty else np.nan,
            'coverage': float(session_part['interval_coverage'].mean()) if not session_part.empty else float(global_part['interval_coverage'].mean()) if not global_part.empty else np.nan,
            'mae': float(session_part['mae'].mean()) if not session_part.empty else float(global_part['mae'].mean()) if not global_part.empty else np.nan,
            'rmse': float(session_part['rmse'].mean()) if not session_part.empty else float(global_part['rmse'].mean()) if not global_part.empty else np.nan,
            'bias_correction': bias_correction,
            'run_id': identity['run_id'],
            'generation_id': identity['generation_id'],
            'snapshot_hash': identity['snapshot_hash'],
        })
    adjusted_df = pd.DataFrame(result_rows)
    history = records.copy()
    if not history.empty:
        history = history.loc[history['forecast_origin_time'] >= (history['forecast_origin_time'].max() - pd.Timedelta(days=25))].copy()
        history['Selected/Detected Session'] = history['session']
        history['Session Weight'] = history['session'].map(lambda s: float(stats.loc[stats['session'].eq(s), 'sample_count'].max() or 0) / (float(stats.loc[stats['session'].eq(s), 'sample_count'].max() or 0) + 30.0) if not stats.empty else 0.0)
        history['Evidence Tier'] = history['session'].map(lambda s: session_evidence_tier(int(stats.loc[stats['session'].eq(s), 'sample_count'].max() or 0)) if not stats.empty else 'GLOBAL_FALLBACK')
        history['Settlement Status'] = history['settlement_status']
        history['Run ID'] = identity['run_id']
        history['Generation ID'] = identity['generation_id']
        history['Snapshot Hash'] = identity['snapshot_hash']
        history['Session Prediction'] = history.apply(lambda r: float(r['base_prediction']) + float(adjusted_df.loc[adjusted_df['horizon'].eq(int(r['horizon'])), 'bias_correction'].iloc[0]) if not adjusted_df.empty and int(r['horizon']) in set(adjusted_df['horizon']) else r['base_prediction'], axis=1)
        history['Session Error'] = np.where(history['actual'].notna(), history['Session Prediction'] - history['actual'], np.nan)
        history['Base Direction Correct'] = history['direction_correct']
        history['Session Direction Correct'] = np.where(history['actual'].notna() & history['current_price'].notna(), ((history['Session Prediction'] - history['current_price']) >= 0) == ((history['actual'] - history['current_price']) >= 0), np.nan)
        history = history.rename(columns={
            'forecast_origin_time': 'Forecast Origin Broker Time',
            'horizon': 'Horizon',
            'base_prediction': 'Base Prediction',
            'lower': 'Lower',
            'upper': 'Upper',
            'actual': 'Actual',
            'base_error': 'Base Error',
            'coverage': 'Coverage',
        })
        history = history[[c for c in ['Forecast Origin Broker Time', 'Selected/Detected Session', 'Horizon', 'Base Prediction', 'Session Prediction', 'Lower', 'Upper', 'Actual', 'Base Error', 'Session Error', 'Base Direction Correct', 'Session Direction Correct', 'Coverage', 'Session Weight', 'Evidence Tier', 'Settlement Status', 'Run ID', 'Generation ID', 'Snapshot Hash'] if c in history.columns]].sort_values('Forecast Origin Broker Time', ascending=False).head(600).reset_index(drop=True)
    return {
        'contract': session_contract.to_dict(),
        'identity': identity,
        'horizons': adjusted_df,
        'history': history,
        'stats': stats,
        'intraday_priors': intraday_priors,
        'microstructure_profiles': micro_profiles,
    }


__all__ = ['build_session_adjusted_projection', 'session_evidence_tier', 'compute_intraday_session_priors', 'compute_session_microstructure_profiles']
