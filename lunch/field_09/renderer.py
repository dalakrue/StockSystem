"""Read-only renderer. This module only displays previously saved evidence."""
import pandas as pd
import streamlit as st


def _metric(col, label, value, suffix=''):
    col.metric(label, '—' if value is None else f'{value}{suffix}')


def render(vm):
    p = vm['payload'] or {}
    additive = vm.get("counterfactual_policy_20260625") or {}
    st.markdown('### Field 9 — EURUSD H1 Decision Transmission, Impact Decay, Counterfactual Regret & Stability')
    st.caption('Operational policy evidence is additive; protected BUY/SELL/WAIT and exit logic remain unchanged.')
    from ui.lunch_one_hour_direction_20260626 import render_for_field
    render_for_field(vm['context'].history_repository.state, 9)
    if (not p or p.get('status') == 'ERROR') and additive.get('status') != 'OK':
        st.warning(f"Full Field 9 research is unavailable: {p.get('reason','Run Full Calculation to publish it.')} Lightweight operational history remains available above.")
        return

    s = p.get('current_summary', {}) if isinstance(p, dict) else {}
    additive_current = additive.get('current', {}) if isinstance(additive, dict) else {}
    st.markdown('### Field 9 — EURUSD H1 Decision Transmission, Impact Decay, Counterfactual Regret & Stability')
    st.caption('SHADOW ONLY · Production BUY/SELL/WAIT and exit logic remain unchanged · Saved canonical evidence only')

    top = st.columns(4)
    _metric(top[0], 'After-cost EV', additive_current.get('best_counterfactual_value', s.get('expected_h3_net_impact')), ' pips' if additive_current.get('best_counterfactual_value') is None else '')
    _metric(top[1], 'Conservative EV', additive_current.get('production_action_value'))
    _metric(top[2], 'Regret', additive_current.get('production_regret', s.get('regret')), ' pips' if additive_current.get('production_regret') is None else '')
    _metric(top[3], 'Evidence', 'PROVEN' if additive.get('status') == 'OK' else 'NOT PROVEN')

    with st.expander('Section A — Current Summary', expanded=False):
        c = st.columns(4)
        _metric(c[0], 'Production decision', s.get('production_decision'))
        _metric(c[1], 'Shadow action', s.get('shadow_preferred_action', additive_current.get('decision_role')))
        _metric(c[2], '3H net impact', s.get('expected_h3_net_impact'), ' pips')
        _metric(c[3], 'Regret', s.get('regret', additive_current.get('production_regret')), ' pips')
        c = st.columns(4)
        _metric(c[0], 'Peak hour', s.get('peak_impact_hour'))
        _metric(c[1], 'Peak impact', s.get('peak_expected_impact'), ' pips')
        _metric(c[2], 'Positive probability', s.get('probability_positive_net_impact'))
        _metric(c[3], 'Stability', s.get('stability', additive_current.get('stability')))
        st.json({'evidence_status': s.get('evidence_status', additive.get('status')), 'reality_check_status': s.get('reality_check_status'), 'production_changed': 'NO', 'exit_changed': 'NO', 'shadow_only': 'YES'}, expanded=False)

    with st.expander('Section B — Impact Path', expanded=False):
        df = pd.DataFrame(vm['path'])
        st.dataframe(df, use_container_width=True, hide_index=True)
        if not df.empty and {'horizon', 'expected_cumulative_net_pips'}.issubset(df.columns):
            st.line_chart(df.set_index('horizon')[['expected_cumulative_net_pips', 'lower_bound', 'upper_bound']])

    with st.expander('Section C — Counterfactual Action Matrix', expanded=False):
        st.dataframe(pd.DataFrame(vm['matrix']), use_container_width=True, hide_index=True)
    with st.expander('Section D — Impact Mechanisms', expanded=False):
        a = p.get('attribution', {})
        st.caption(a.get('label', 'PREDICTIVE_CONTRIBUTION'))
        st.dataframe(pd.DataFrame(a.get('contributions', [])), use_container_width=True, hide_index=True)
    with st.expander('Section E — Decision Flip', expanded=False):
        st.json(p.get('decision_flip', {}), expanded=False)
    with st.expander('Section F — Stability', expanded=False):
        st.json({'influence': p.get('influence_audit', {}), 'model_class_reliance': p.get('model_class_reliance', {}), 'conditional_predictive_ability': p.get('conditional_predictive_ability', {}), 'reality_check': p.get('reality_check', {})}, expanded=False)
    with st.expander('Section G — Historical Impact', expanded=False):
        hist = pd.DataFrame(vm['history'])
        if not hist.empty:
            st.dataframe(hist, use_container_width=True, hide_index=True, height=520)
        else:
            st.info('No matured Field 9 history is stored; no values were fabricated.')

    rg = vm.get('research_grade_v17') or {}
    if rg:
        with st.expander('Section H — Research-Grade Policy Value, Robustness & Grounding', expanded=False):
            st.json({'contract': rg.get('contract', {}), 'field9': rg.get('field9', {}), 'validation_errors': rg.get('validation_errors', []), 'status': rg.get('status')}, expanded=False)

    with st.expander('Section I — Ten-Foundation Active Research Evidence', expanded=False):
        from ui.lunch_ten_foundation_active_20260624 import render_for_field as render_ten_foundation
        render_ten_foundation(vm['context'].history_repository.state, 9)
    st.caption(f"Readiness: {vm['readiness'].get('status','INSUFFICIENT_DATA')} · Rendered from saved namespace field9_eurusd_h1_decision_impact · No heavy calculation")

    with st.expander("Unified Research-Grade Shadow Validation", expanded=False):
        from ui.lunch_research_grade_system_v17_20260624 import render_for_field
        render_for_field(vm["context"].history_repository.state, 9)

    with st.expander("Field 9 — Doubly Robust Counterfactual Action Value, Regret and Stability", expanded=False):
        st.caption("COUNTERFACTUAL POLICY EVIDENCE — NOT EXECUTED-TRADE PROOF")
        if additive.get("status") == "OK":
            current = additive_current
            c = st.columns(5)
            _metric(c[0], 'Decision role', current.get('decision_role'))
            _metric(c[1], 'BUY DR value', current.get('buy_dr_value'))
            _metric(c[2], 'WAIT DR value', current.get('wait_dr_value'))
            _metric(c[3], 'SELL DR value', current.get('sell_dr_value'))
            _metric(c[4], 'Regret', current.get('production_regret'))
            hist = pd.DataFrame(additive.get('history') or [])
            st.markdown('#### Field 9 Doubly Robust Counterfactual Decision History — Last 25 Days')
            if not hist.empty:
                st.dataframe(hist, use_container_width=True, hide_index=True, height=480)
            else:
                st.info('No additive Field 9 counterfactual history was published for this run.')
        else:
            st.info('Field 9 additive counterfactual evidence is not published for the current run.')
