from __future__ import annotations
import json
import pandas as pd
import streamlit as st
from core.one_hour_direction_confirmation_20260626 import STATE_KEY


def _fmt(v, d=3, suffix=''):
    try:
        return f"{float(v):.{d}f}{suffix}"
    except Exception:
        return "UNAVAILABLE"


def _decoded(v):
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v) if v else {}
    except Exception:
        return {}


def _metric_grid(items, columns=6):
    for start in range(0, len(items), columns):
        row = st.columns(columns)
        for col, (label, value) in zip(row, items[start:start+columns]):
            col.metric(label, value if value not in (None, '') else 'UNAVAILABLE')


def _history(p):
    h = p.get('history')
    return h if isinstance(h, pd.DataFrame) else pd.DataFrame(h or [])


def _current_paths(cur):
    origin = _decoded(cur.get('origin_payload'))
    return origin.get('raw_path') or [], origin.get('safe_path') or [], origin


def render_for_field(state, field: int):
    p = state.get(STATE_KEY) or {}
    cur = p.get('current') or {}
    if not p.get('ok'):
        st.info('Operational one-hour direction confirmation is unavailable: ' + str(p.get('reason') or 'run Settings calculation.'))
        return
    val = p.get('validation') or {}
    raw_path, safe_path, origin = _current_paths(cur)
    cap = origin.get('cap') or {}
    st.caption('OPERATIONAL CONFIRMATION · protected production action, raw Power BI path, regime formulas, canonical identity and protected hashes remain unchanged')

    if field == 1:
        st.markdown('## Operational H1 Open-to-Close Direction Confirmation')
        action = cur.get('confirmation_action') or 'WAIT'
        agreement = 'AGREE' if action.endswith(str(cur.get('production_action') or '')) else 'CONFLICT'
        _metric_grid([
            ('Operational H1 action', action), ('Protected production action', cur.get('production_action')),
            ('Confirmation level', cur.get('confirmation_level')), ('P(BUY)', _fmt(cur.get('p_buy'))),
            ('P(SELL)', _fmt(cur.get('p_sell'))), ('P(NEUTRAL)', _fmt(cur.get('p_neutral'))),
            ('Direction score', _fmt(cur.get('direction_score'), 1)), ('Reliability', _fmt(cur.get('reliability'))),
            ('Probability margin', _fmt(cur.get('probability_margin'))), ('Alpha', _fmt(cur.get('alpha_pips'), 1, ' pips')),
            ('Beta', _fmt(cur.get('beta_pips'), 1, ' pips')), ('Alpha–Beta difference', _fmt(cur.get('alpha_beta_difference_pips'), 1, ' pips')),
            ('Instability', cur.get('instability_status')), ('Expected target O→C', _fmt(cur.get('expected_open_close_pips'), 1, ' pips')),
            ('Safe target price', _fmt(cur.get('safe_forecast'), 5)), ('Active cap', _fmt(cur.get('active_cap_pips'), 1, ' pips')),
            ('Session', cur.get('session')), ('Production agreement', agreement),
        ])
        st.dataframe(pd.DataFrame([{
            'Entry broker time': cur.get('target_h1_open_time'), 'Exit broker time': cur.get('target_h1_close_time'),
            'Sign agreement': cur.get('alpha_beta_sign_agreement'), 'Direction reversal': bool(cur.get('direction_reversal')),
            'Robust Z': cur.get('robust_z'), 'Wrong-direction probability': cur.get('wrong_direction_probability'),
            'Cap source': cur.get('cap_source'), 'Pips removed': cur.get('pips_removed_by_cap'),
            'Evidence state': cur.get('data_quality_state'), 'WAIT/Lean reason': cur.get('wait_reason'),
            'Settled origins': val.get('settled_n'), 'Accepted coverage': val.get('coverage'),
            'Selective accuracy': val.get('accepted_accuracy'), 'Baseline accuracy': val.get('baseline_accuracy'),
            'Brier score': val.get('mean_brier'), 'Log loss': val.get('mean_log_loss'),
        }]), use_container_width=True, hide_index=True)
        h = _history(p)
        if not h.empty:
            wanted = ['forecast_origin_time','target_h1_open_time','target_h1_close_time','session','overlap','broker_hour','production_regime','production_action','confirmation_action','confirmation_level','p_buy','p_sell','p_neutral','probability_margin','reliability','alpha_pips','beta_pips','alpha_beta_difference_pips','robust_z','instability_status','raw_forecast','safe_forecast','active_cap_pips','actual_open_to_close_pips','actual_direction','correctness','brier_score','log_loss','realized_utility','decision_regret','settlement_status','run_id','generation_id','snapshot_hash']
            st.markdown('#### Immutable Direction-Confirmation History — Last 25 Broker Days')
            st.dataframe(h[[c for c in wanted if c in h]], use_container_width=True, hide_index=True, height=500)
        with st.expander('Model weights, reliability components and canonical identity', expanded=False):
            st.json({'model_weights': _decoded(cur.get('model_weights')), 'reliability_components': _decoded(cur.get('reliability_components')), 'identity': {k: cur.get(k) for k in ('run_id','generation_id','snapshot_hash','symbol','timeframe','broker_candle_time')}, 'selected_thresholds': origin.get('selected_thresholds')}, expanded=False)

    elif field == 2:
        st.markdown('#### Protected Raw Path + Operational Safe Path')
        _metric_grid([
            ('Raw one-hour forecast', _fmt(cur.get('raw_forecast'), 5)), ('Safe one-hour forecast', _fmt(cur.get('safe_forecast'), 5)),
            ('Raw displacement', _fmt(cap.get('raw_move_pips'), 1, ' pips')), ('Safe displacement', _fmt(cap.get('safe_move_pips'), 1, ' pips')),
            ('Active cap', _fmt(cur.get('active_cap_pips'), 1, ' pips')), ('Cap source', cur.get('cap_source')),
            ('Pips removed', _fmt(cur.get('pips_removed_by_cap'), 1, ' pips')), ('Alpha', _fmt(cur.get('alpha_pips'), 1, ' pips')),
            ('Beta', _fmt(cur.get('beta_pips'), 1, ' pips')), ('Alpha–Beta difference', _fmt(cur.get('alpha_beta_difference_pips'), 1, ' pips')),
            ('Robust instability', cur.get('instability_status')), ('Wrong-direction probability', _fmt(cur.get('wrong_direction_probability'))),
        ])
        max_len = max(len(raw_path), len(safe_path), 2)
        rp = list(raw_path) + [None] * (max_len-len(raw_path))
        sp = list(safe_path) + [None] * (max_len-len(safe_path))
        chart = pd.DataFrame({
            'Protected raw central path': rp,
            'Prediction path (green)': sp,
        })
        chart.index.name = 'Projected point'
        # Explicit series colors make the operational prediction path visibly green
        # while the protected raw path remains separately visible and unchanged.
        try:
            st.line_chart(chart, color=['#F2C94C', '#20C997'])
        except TypeError:
            st.line_chart(chart)
        st.caption('Green = operational one-hour prediction path. Yellow = protected raw central path. Every operational point is rescaled against the completed origin close; protected calculations remain unchanged.')
        st.dataframe(pd.DataFrame([{
            'Target H1 open marker': cur.get('target_h1_open_time'), 'Target H1 close marker': cur.get('target_h1_close_time'),
            'Origin close': cur.get('forecast_origin_close'), 'Alpha point': cur.get('raw_forecast'),
            'Beta pips': cur.get('beta_pips'), 'Interval width proxy': 2*(cur.get('active_cap_pips') or 0),
            'Empirical interval coverage': None, 'Session path MAE': None, 'One-hour direction reliability': cur.get('reliability')
        }]), use_container_width=True, hide_index=True)

    elif field == 3:
        st.markdown('#### One-Hour Regime Compatibility (Additive Interpretation)')
        probs = {'BUY': cur.get('p_buy'), 'SELL': cur.get('p_sell'), 'NEUTRAL': cur.get('p_neutral')}
        best = max(probs, key=lambda k: probs[k] if probs[k] is not None else -1)
        st.dataframe(pd.DataFrame([{
            'Regime state': cur.get('production_regime'), 'Next-H1 compatible direction': best,
            'P(BUY)': cur.get('p_buy'), 'P(SELL)': cur.get('p_sell'), 'P(NEUTRAL)': cur.get('p_neutral'),
            'Same-session sample size': cur.get('origin_payload', {}).get('selected_n') if isinstance(cur.get('origin_payload'), dict) else None,
            'Compatibility with operational direction': cur.get('compatibility_score'),
            'Conflict flag': not str(cur.get('confirmation_action')).endswith(str(cur.get('production_action'))),
            'Final contribution weight': cur.get('direction_score'), 'Transition-risk penalty': cur.get('transition_risk_state'),
            'Session': cur.get('session'), 'Evidence state': cur.get('data_quality_state')
        }]), use_container_width=True, hide_index=True)
        h = _history(p)
        if not h.empty:
            cols = [c for c in ['forecast_origin_time','session','production_regime','production_action','confirmation_action','p_buy','p_sell','p_neutral','compatibility_score','transition_risk_state','actual_direction','correctness','settlement_status'] if c in h]
            st.markdown('#### One-Hour Regime Compatibility History — Last 25 Broker Days')
            st.dataframe(h[cols], use_container_width=True, hide_index=True, height=420)

    elif field == 8:
        st.markdown('#### Direction Probability and Alpha–Beta Evidence — Last 25 Broker Days')
        h = _history(p)
        if h.empty:
            st.info('No immutable one-hour history rows are stored yet.')
            return
        bucket_cols = [c for c in ['session','overlap','broker_hour','production_regime','instability_status','confirmation_action','actual_direction'] if c in h]
        settled = h[h.settlement_status.eq('SETTLED')] if 'settlement_status' in h else h
        if not settled.empty and bucket_cols:
            grouped = settled.groupby(bucket_cols, dropna=False).agg(
                sample_size=('forecast_id','count'), shrinkage_adjusted_accuracy=('correctness','mean'),
                brier_score=('brier_score','mean'), log_loss=('log_loss','mean'), reliability=('reliability','mean')
            ).reset_index()
            grouped['coverage'] = grouped['sample_size'] / max(1, len(settled))
            st.dataframe(grouped, use_container_width=True, hide_index=True, height=500)
        cols = [c for c in ['forecast_origin_time','session','overlap','broker_hour','production_regime','alpha_pips','beta_pips','alpha_beta_difference_pips','robust_z','instability_status','p_buy','p_sell','p_neutral','reliability','confirmation_action','actual_direction','correctness','brier_score','log_loss','settlement_status'] if c in h]
        with st.expander('Immutable origin rows', expanded=False):
            st.dataframe(h[cols], use_container_width=True, hide_index=True, height=500)

    elif field == 9:
        st.markdown('#### Operational Policy and Regret — Last 25 Broker Days')
        h = _history(p)
        if h.empty:
            st.info('No policy/regret rows are stored yet.')
            return
        x = h.copy()
        x['accepted'] = x.get('confirmation_action', 'WAIT').astype(str).str.contains('BUY|SELL', regex=True)
        x['predicted_utility'] = x.get('expected_open_close_pips')
        x['actual_utility_after_costs'] = x.get('realized_utility')
        x['best_counterfactual_utility'] = x.get('realized_utility') + x.get('decision_regret')
        x['direction_flip'] = x.get('direction_reversal')
        cols = [c for c in ['forecast_origin_time','session','production_action','confirmation_action','confirmation_level','accepted','predicted_utility','actual_utility_after_costs','best_counterfactual_utility','decision_regret','direction_flip','wrong_direction_probability','actual_open_to_close_pips','actual_direction','settlement_status'] if c in x]
        st.dataframe(x[cols], use_container_width=True, hide_index=True, height=500)
        if 'session' in x:
            summary = x.groupby('session', dropna=False).agg(origins=('forecast_id','count'), accepted=('accepted','sum'), mean_regret=('decision_regret','mean'), mean_wrong_direction_probability=('wrong_direction_probability','mean')).reset_index()
            summary['coverage'] = summary['accepted']/summary['origins'].clip(lower=1)
            st.markdown('#### Session Policy Comparison')
            st.dataframe(summary, use_container_width=True, hide_index=True)
