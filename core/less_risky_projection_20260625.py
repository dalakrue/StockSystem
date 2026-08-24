"""Additive less-risky overlay over the already-published Field 2 path.

This module never replaces the protected production path. It extracts the
already-published central path from canonical/saved sources, optionally applies
session-conditioned shadow calibration, then computes a conservative green path.
"""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from core.publication_identity_20260625 import freeze_publication_identity, identity_matches
from core.scalar_normalization_20260625 import scalar_series
from core.session_adaptive_projection_20260625 import build_session_adjusted_projection
from core.session_context_20260625 import resolve_session_contract

HORIZONS = (1, 2, 3)


def _m(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    for k in ('canonical_decision_result_20260617', 'last_valid_canonical_decision_result_20260617', 'adx_shared_calc_result_20260615'):
        v = state.get(k)
        if isinstance(v, Mapping) and v:
            return v
    return {}


def _strict_identity(state: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    from core.canonical_identity_20260627 import build_canonical_identity
    identity = build_canonical_identity(canonical, state=state, require_complete=True).as_dict()
    identity['snapshot_hash'] = identity['source_snapshot_hash']
    return identity


def _display_action(value: Any) -> str:
    raw = str(value or 'WAIT').strip().upper().replace('_', ' ')
    if raw in {'HOLD', 'HOLD AND PROTECT', 'HOLD & PROTECT'}:
        return 'HOLD & PROTECT'
    if raw in {'WAIT PULLBACK', 'WAIT/PULLBACK', 'PULLBACK'}:
        return 'WAIT PULLBACK'
    return raw


def _identity_source(source: Any, fallback: Mapping[str, Any]) -> Mapping[str, Any]:
    mapped = _m(source)
    if not mapped:
        return {}
    return {
        'run_id': mapped.get('run_id') or mapped.get('source_run_id') or fallback.get('run_id'),
        'generation_id': mapped.get('generation_id') or mapped.get('calculation_generation') or fallback.get('generation_id'),
        'snapshot_hash': mapped.get('snapshot_hash') or mapped.get('source_snapshot_hash') or fallback.get('snapshot_hash'),
        'source_snapshot_hash': mapped.get('source_snapshot_hash') or mapped.get('snapshot_hash') or fallback.get('source_snapshot_hash'),
        'source_signature': mapped.get('source_signature') or fallback.get('source_signature'),
        'symbol': mapped.get('symbol') or fallback.get('symbol'),
        'timeframe': mapped.get('timeframe') or fallback.get('timeframe'),
        'completed_broker_candle': mapped.get('completed_broker_candle') or mapped.get('broker_candle_time') or mapped.get('latest_completed_candle_time') or fallback.get('completed_broker_candle'),
    }


def _path_from_main_df(main: pd.DataFrame, identity: Mapping[str, Any], source_key: str) -> pd.DataFrame:
    if not isinstance(main, pd.DataFrame) or main.empty:
        return pd.DataFrame()
    cols = {str(c).lower().replace(' ', '_'): c for c in main.columns}
    time_col = next((cols[k] for k in cols if k in {'time', 'target_time', 'projection_time'}), None)
    path_col = next((cols[k] for k in cols if k in {'main_path', 'central_path', 'predicted_price'}), None)
    if time_col is None or path_col is None:
        return pd.DataFrame()
    lower_col = next((cols[k] for k in cols if k in {'lower_band', 'lower_bound', 'lower'}), None)
    upper_col = next((cols[k] for k in cols if k in {'upper_band', 'upper_bound', 'upper'}), None)
    step_col = next((cols[k] for k in cols if k in {'step', 'horizon', 'horizon_hours'}), None)
    fallback_horizon = scalar_series(np.arange(1, len(main) + 1), index=main.index, default=np.nan)
    horizon_values = pd.to_numeric(main[step_col], errors='coerce') if step_col else fallback_horizon
    horizon_values = horizon_values.where(horizon_values.notna(), fallback_horizon).astype(int)
    out = pd.DataFrame({
        'target_time': pd.to_datetime(main[time_col], errors='coerce', utc=True),
        'central_price': pd.to_numeric(main[path_col], errors='coerce'),
        'lower_bound': pd.to_numeric(main[lower_col], errors='coerce') if lower_col else np.nan,
        'upper_bound': pd.to_numeric(main[upper_col], errors='coerce') if upper_col else np.nan,
        'horizon': horizon_values,
    }).dropna(subset=['target_time', 'central_price'])
    if out.empty:
        return out
    out['source_key'] = source_key
    out['run_id'] = str(identity.get('run_id') or '')
    out['generation_id'] = str(identity.get('generation_id') or '')
    out['snapshot_hash'] = str(identity.get('snapshot_hash') or '')
    out['native_or_interpolated'] = 'NATIVE'
    return out


def _path_from_forecasts(canonical: Mapping[str, Any], identity: Mapping[str, Any]) -> pd.DataFrame:
    forecasts = _m(canonical.get('forecasts'))
    horizons = _m(forecasts.get('horizons'))
    now = pd.to_datetime(canonical.get('latest_completed_candle_time') or canonical.get('broker_candle_time'), errors='coerce', utc=True)
    rows = []
    for horizon in HORIZONS:
        item = _m(horizons.get(f'{horizon}h') or horizons.get(str(horizon)) or horizons.get(horizon))
        central = _f(item.get('predicted_price'), _f(item.get('price')))
        if central is None:
            continue
        rows.append({
            'horizon': horizon,
            'target_time': now + pd.Timedelta(hours=horizon) if pd.notna(now) else pd.NaT,
            'central_price': central,
            'lower_bound': _f(item.get('lower'), _f(item.get('lower_bound'))),
            'upper_bound': _f(item.get('upper'), _f(item.get('upper_bound'))),
            'source_key': 'canonical.forecasts.horizons',
            'run_id': str(identity.get('run_id') or ''),
            'generation_id': str(identity.get('generation_id') or ''),
            'snapshot_hash': str(identity.get('snapshot_hash') or ''),
            'native_or_interpolated': 'NATIVE',
        })
    return pd.DataFrame(rows)


def extract_saved_projection_horizons(state: Mapping[str, Any], canonical: Mapping[str, Any], horizons: tuple[int, ...] = HORIZONS) -> pd.DataFrame:
    """Search the exact-generation central forecast in the requested order."""
    identity = _strict_identity(state, canonical)
    candidates: list[pd.DataFrame] = []

    direct = _path_from_forecasts(canonical, identity)
    if not direct.empty:
        candidates.append(direct)

    bundle = _m(state.get('powerbi_calibrated_bundle_20260617'))
    main = bundle.get('main') if isinstance(bundle.get('main'), pd.DataFrame) else pd.DataFrame()
    source_ident = _identity_source(_m(bundle.get('summary')), identity)
    try:
        from core.canonical_identity_20260627 import build_canonical_identity, identity_mismatches
        exact_identity = build_canonical_identity(canonical, state=state, require_complete=True)
        bundle_exact = not identity_mismatches(bundle, exact_identity)
    except Exception:
        bundle_exact = False
    if bundle_exact:
        main_df = _path_from_main_df(main, source_ident, 'powerbi_calibrated_bundle_20260617["main"]')
        if not main_df.empty:
            candidates.append(main_df)

    # Raw legacy dataframes do not carry the six-field immutable identity and
    # are therefore not eligible for the exact-run green overlay.

    try:
        from ui.lunch_field2_saved_path_v13 import recover_saved_prediction_bundle
        recovered_bundle, _future, meta = recover_saved_prediction_bundle(state, canonical, state.get('dv_pp_df') if isinstance(state.get('dv_pp_df'), pd.DataFrame) else pd.DataFrame())
        recovered_main = recovered_bundle.get('main') if isinstance(recovered_bundle.get('main'), pd.DataFrame) else pd.DataFrame()
        recovered_ident = _identity_source(_m(recovered_bundle.get('summary')), identity)
        try:
            from core.canonical_identity_20260627 import build_canonical_identity, identity_mismatches
            recovered_exact = not identity_mismatches(recovered_bundle, build_canonical_identity(canonical, state=state, require_complete=True))
        except Exception:
            recovered_exact = False
        if meta.get('ok') and recovered_exact:
            item = _path_from_main_df(recovered_main, recovered_ident, 'lunch_field2_saved_path_v13')
            if not item.empty:
                candidates.append(item)
    except Exception:
        pass

    if not candidates:
        return pd.DataFrame(columns=['horizon', 'target_time', 'current_price', 'central_price', 'lower_bound', 'upper_bound', 'source_key', 'run_id', 'generation_id', 'snapshot_hash', 'native_or_interpolated'])

    # Choose the richest candidate from the search order while preserving priority.
    chosen = candidates[0]
    for candidate in candidates[1:]:
        if len(candidate) > len(chosen):
            chosen = candidate

    chosen = chosen.copy().sort_values('horizon')
    chosen = chosen.loc[chosen['horizon'].isin(horizons)].drop_duplicates('horizon', keep='first')

    # Explicit display-only H2 interpolation from exact H1/H3 when needed.
    if 2 in horizons and 2 not in set(chosen['horizon']) and {1, 3}.issubset(set(chosen['horizon'])):
        h1 = chosen.loc[chosen['horizon'].eq(1)].iloc[0]
        h3 = chosen.loc[chosen['horizon'].eq(3)].iloc[0]
        interp = {
            'horizon': 2,
            'target_time': h1['target_time'] + (h3['target_time'] - h1['target_time']) / 2,
            'central_price': float(h1['central_price']) + (float(h3['central_price']) - float(h1['central_price'])) / 2.0,
            'lower_bound': np.nan if pd.isna(h1['lower_bound']) or pd.isna(h3['lower_bound']) else float(h1['lower_bound']) + (float(h3['lower_bound']) - float(h1['lower_bound'])) / 2.0,
            'upper_bound': np.nan if pd.isna(h1['upper_bound']) or pd.isna(h3['upper_bound']) else float(h1['upper_bound']) + (float(h3['upper_bound']) - float(h1['upper_bound'])) / 2.0,
            'source_key': str(h1['source_key']),
            'run_id': str(h1['run_id']),
            'generation_id': str(h1['generation_id']),
            'snapshot_hash': str(h1['snapshot_hash']),
            'native_or_interpolated': 'H2_INTERPOLATED_DISPLAY_ONLY',
        }
        chosen = pd.concat([chosen, pd.DataFrame([interp])], ignore_index=True, axis=0)
    return chosen.sort_values('horizon').reset_index(drop=True)


def build_less_risky_path(state: Mapping[str, Any], selected_session: str | None = None) -> pd.DataFrame:
    canonical = _canonical(state)
    final = _m(canonical.get('final_decision'))
    regime = _m(canonical.get('regime'))
    identity = _strict_identity(state, canonical)
    extracted = extract_saved_projection_horizons(state, canonical)
    current = _f(_m(canonical.get('market')).get('current_price'), _f(canonical.get('current_price')))
    if current is None:
        for k in ('dv_pp_base_result', 'lunch_5layer_powerbi_result'):
            r = state.get(k)
            if isinstance(r, Mapping):
                current = _f(r.get('current_price'), _f(r.get('last_close')))
                if current is not None:
                    break
    if current is None or extracted.empty:
        return pd.DataFrame()
    extracted = extracted.copy()
    extracted['current_price'] = current
    session_projection = build_session_adjusted_projection(state, canonical, extracted, selected_session)
    session_horizons = session_projection.get('horizons') if isinstance(session_projection.get('horizons'), pd.DataFrame) else pd.DataFrame()
    session_contract = resolve_session_contract(state, canonical, selected_session).to_dict()

    direction = _display_action(final.get('less_risky_decision') or final.get('final_decision') or canonical.get('full_metric_direction') or 'WAIT')
    reliability = _f(regime.get('reliability'), _f(regime.get('regime_reliability'), 50.0)) or 50.0
    if reliability <= 1:
        reliability *= 100
    regime_agreement = _f(regime.get('agreement_score'), _f(regime.get('three_standard_agreement'), reliability)) or reliability

    rows = []
    for _, row in extracted.iterrows():
        horizon = int(row['horizon'])
        session_row = session_horizons.loc[session_horizons['horizon'].eq(horizon)].iloc[0] if not session_horizons.empty and horizon in set(session_horizons['horizon']) else None
        base_central = _f(row['central_price'])
        session_adjusted = _f(session_row['Session Prediction']) if session_row is not None else base_central
        lower = _f(row.get('lower_bound'))
        upper = _f(row.get('upper_bound'))
        session_direction_accuracy = _f(session_row['session_direction_accuracy']) if session_row is not None else None
        coverage = _f(session_row['coverage']) if session_row is not None else None
        sample_count = int(session_row['sample_count']) if session_row is not None and not pd.isna(session_row['sample_count']) else 0
        evidence_strength = (
            0.30 * (session_direction_accuracy if session_direction_accuracy is not None else 0.5)
            + 0.25 * (reliability / 100.0)
            + 0.20 * (regime_agreement / 100.0)
            + 0.15 * (session_direction_accuracy if session_direction_accuracy is not None else 0.5)
            + 0.10 * (coverage if coverage is not None else 0.5)
        )
        shrinkage = float(np.clip(evidence_strength, 0.10, 1.00))
        tier = 'SESSION_CALIBRATED' if sample_count >= 60 else 'SESSION_SHRUNK' if sample_count >= 30 else 'GLOBAL_FALLBACK' if sample_count >= 10 else 'MINIMUM_VALID'
        if direction in {'WAIT', 'WAIT PULLBACK', 'NO TRADE'}:
            shrinkage = min(shrinkage, 0.35)
        green = current + shrinkage * ((session_adjusted if session_adjusted is not None else base_central) - current)
        if lower is not None:
            green = max(lower, green)
        if upper is not None:
            green = min(upper, green)
        reason_codes = []
        if session_adjusted is None:
            reason_codes.append('MISSING_SESSION_ADJUSTMENT')
        if session_direction_accuracy is None:
            reason_codes.append('MISSING_SESSION_DIRECTION_ACCURACY')
        if coverage is None:
            reason_codes.append('MISSING_INTERVAL_COVERAGE')
        if row.get('native_or_interpolated') == 'H2_INTERPOLATED_DISPLAY_ONLY':
            reason_codes.append('H2_INTERPOLATED_DISPLAY_ONLY')
        reason_codes.append(tier)
        rows.append({
            'Horizon': f'H+{horizon}',
            'horizon': horizon,
            'Target Broker Time': row['target_time'],
            'Target Time': row['target_time'],
            'Selected Session': session_contract['selected_session'],
            'Current Price': current,
            'Current': current,
            'Base Central Path': base_central,
            'Central Path': base_central,
            'Session-Adjusted Path': session_adjusted,
            'Green Less-Risky Path': green,
            'Less-Risky Green Path': green,
            'Lower Bound': lower,
            'Lower Blue Band': lower,
            'Upper Bound': upper,
            'Upper Red Band': upper,
            'Decision': direction,
            'Session Sample Size': sample_count,
            'Session Direction Accuracy': session_direction_accuracy,
            'Coverage': coverage,
            'Path Trust': shrinkage,
            'Green Tier': tier,
            'Green Path Tier': tier,
            'Reason Codes': ', '.join(reason_codes),
            'Run ID': identity['run_id'],
            'generation_id': identity['generation_id'],
            'snapshot_hash': identity['snapshot_hash'],
            'source_key': row.get('source_key'),
            'native_or_interpolated': row.get('native_or_interpolated'),
        })
    return pd.DataFrame(rows)


def build_path_history_25d(state: Mapping[str, Any], selected_session: str | None = None) -> pd.DataFrame:
    canonical = _canonical(state)
    projection = build_less_risky_path(state, selected_session)
    if projection.empty:
        return pd.DataFrame()
    session_projection = build_session_adjusted_projection(state, canonical, extract_saved_projection_horizons(state, canonical), selected_session)
    history = session_projection.get('history') if isinstance(session_projection.get('history'), pd.DataFrame) else pd.DataFrame()
    if history.empty:
        return pd.DataFrame()
    latest = history.copy()
    latest['Green Less-Risky Path'] = latest['Session Prediction']
    latest['Blue Lower Path'] = latest['Lower']
    latest['Red Upper Path'] = latest['Upper']
    latest['Decision'] = projection.iloc[0]['Decision'] if not projection.empty else 'WAIT'
    latest['Green Path Tier'] = latest['Evidence Tier']
    latest['Green Multiplier'] = latest['Session Weight']
    latest['Coverage Rolling %'] = latest['Coverage']
    latest['Missing Evidence'] = np.where(latest['Evidence Tier'].eq('MINIMUM_VALID'), 'SESSION_EVIDENCE_SPARSE', '')
    return latest[[c for c in ['Forecast Origin Broker Time', 'Selected/Detected Session', 'Horizon', 'Base Prediction', 'Session Prediction', 'Green Less-Risky Path', 'Blue Lower Path', 'Red Upper Path', 'Actual', 'Decision', 'Green Path Tier', 'Green Multiplier', 'Coverage Rolling %', 'Missing Evidence', 'Run ID', 'Generation ID', 'Snapshot Hash'] if c in latest.columns]].sort_values('Forecast Origin Broker Time', ascending=False).head(600).reset_index(drop=True)


def render_less_risky_projection(state: MutableMapping[str, Any], selected_session: str | None = None) -> None:
    import streamlit as st

    st.markdown('#### Green Less-Risky WAIT PULLBACK / HOLD & PROTECT Projection — H+1, H+2, H+3')
    path = build_less_risky_path(state, selected_session)
    if path.empty:
        st.info('The optional green research path is unavailable because a valid exact-run central path was not published. The protected production chart remains unchanged; no stale or synthetic green path was fabricated.')
        return
    state['less_risky_projection_20260625'] = path
    fig = go.Figure()
    x = path['Target Broker Time']
    fig.add_trace(go.Scatter(x=x, y=path['Base Central Path'], name='Existing central/yellow path', mode='lines+markers'))
    fig.add_trace(go.Scatter(x=x, y=path['Green Less-Risky Path'], name='Green Less-Risky Path', mode='lines+markers', connectgaps=False))
    fig.add_trace(go.Scatter(x=x, y=path['Lower Bound'], name='Blue lower bound', mode='lines+markers', connectgaps=False))
    fig.add_trace(go.Scatter(x=x, y=path['Upper Bound'], name='Red upper bound', mode='lines+markers', connectgaps=False))
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=30, b=20), legend=dict(orientation='h'))
    st.plotly_chart(fig, use_container_width=True, config={'displaylogo': False, 'responsive': True})
    st.dataframe(path[[c for c in ['Horizon', 'Target Broker Time', 'Selected Session', 'Current Price', 'Base Central Path', 'Session-Adjusted Path', 'Green Less-Risky Path', 'Lower Bound', 'Upper Bound', 'Decision', 'Session Sample Size', 'Session Direction Accuracy', 'Coverage', 'Path Trust', 'Green Tier', 'Reason Codes', 'Run ID'] if c in path.columns]], use_container_width=True, hide_index=True)
    with st.expander('Green, Session-Adjusted, Blue and Red Path History — Last 25 Days', expanded=False):
        hist = build_path_history_25d(state, selected_session)
        if hist.empty:
            st.info('No settled path-history rows are available yet. The next successful completed-H1 run will append evidence.')
        else:
            st.dataframe(hist, use_container_width=True, hide_index=True, height=420)


__all__ = ['extract_saved_projection_horizons', 'build_less_risky_path', 'build_path_history_25d', 'render_less_risky_projection']
