"""2026-06-11 Data Visualization two-section clean upgrade.

Final non-destructive wrapper: keep calculations and helper functions, but show the
Data Visualization tab as only two public sections:
1) One Unified PowerBI Price Projection.
2) Combined uploaded-photo/logic section containing all secondary tables, controls,
   KNN/greedy priorities, technical boards, exports, and NY/London helpers.
"""
from __future__ import annotations

import json
from typing import Any, Dict

import pandas as pd
import streamlit as st


def install(ns: Dict[str, Any]) -> None:
    def _call(name: str, *args, **kwargs):
        fn = ns.get(name)
        if callable(fn):
            return fn(*args, **kwargs)
        raise RuntimeError(f"Missing helper: {name}")

    def _sort(df: Any) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        fn = ns.get('_dv_sort_newest_first_v20260609')
        if callable(fn):
            try:
                return fn(df)
            except Exception:
                pass
        x = df.copy()
        for c in ('time','Time','datetime','Date'):
            if c in x.columns:
                x['_t'] = pd.to_datetime(x[c], errors='coerce')
                return x.sort_values('_t', ascending=False, na_position='last').drop(columns=['_t']).reset_index(drop=True)
        return x.iloc[::-1].reset_index(drop=True)

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return default

    def _run_dv_calculation(rows_limit: int, horizon: int, min_days: int, bt_lookback: int) -> None:
        d0 = _call('_clean_lunch_visual_df', limit=int(rows_limit))
        d = _call('_dv_prepare_ohlc_v20260609', d0, limit=int(rows_limit))
        if not isinstance(d, pd.DataFrame) or d.empty or len(d) < 120:
            st.session_state['dv_two_section_error_20260611'] = 'Not enough clean OHLC data. Need at least 120 candles.'
            return
        result = _call('_five_layer_powerbi_calculate', d, horizon=int(horizon))
        predicted = _call('_dv_predict_future_candles_v20260609', d, horizon=int(horizon))
        bt_hist, bt_summary = _call('_dv_prediction_vs_actual_history_v20260609', d, lookback=int(bt_lookback), horizon=1)
        projection_history = _call('_dv_dynamic_projection_history_v20260609', d, lookback_days=10, horizon=min(6, int(horizon)))
        regime_summary, regime_hist = _call('_dv_major_regime_detector_v20260609', d, min_days=float(min_days), lookback_days=240, horizon=int(horizon))
        light_fn = ns.get('_dv_build_lightblue_path_v20260609')
        last_fn = ns.get('_dv_last_continuous_days_v20260609')
        lightblue = pd.DataFrame()
        if callable(light_fn) and callable(last_fn):
            try:
                lightblue = light_fn(last_fn(d, days=10), predicted)
            except Exception:
                lightblue = pd.DataFrame()
        st.session_state.update({
            'lunch_bi_visual_ready': True,
            'dv_pp_df': d,
            'dv_pp_base_result': result,
            'dv_pp_predicted': predicted,
            'dv_pp_bt_hist': _sort(bt_hist),
            'dv_pp_bt_summary': bt_summary,
            'dv_pp_projection_history': projection_history,
            'dv_pp_regime_summary': regime_summary,
            'dv_pp_regime_hist': _sort(regime_hist),
            'dv_pp_lightblue_path': lightblue,
            'dv_two_section_ready_20260611': True,
            'dv_two_section_error_20260611': '',
        })

    def _render_choice_controls(prefix: str = 'dv_two'):
        c = st.columns(5)
        with c[0]:
            rows = st.selectbox('Data rows', [1500, 3000, 5000, 10000, 20000], index=3, key=f'{prefix}_rows')
        with c[1]:
            horizon = st.selectbox('Projection window', [6, 12, 24, 36, 48, 72, 96], index=3, key=f'{prefix}_horizon')
        with c[2]:
            bt = st.selectbox('Prediction vs actual test', [60, 120, 180, 300, 500], index=2, key=f'{prefix}_bt')
        with c[3]:
            min_days = st.selectbox('Regime smooth days', [3, 5, 7, 10, 14, 21], index=1, key=f'{prefix}_mindays')
        with c[4]:
            density = st.selectbox('View density', ['Phone Safe', 'Balanced', 'Detailed'], key=f'{prefix}_density')
        return int(rows), int(horizon), int(min_days), int(bt), density

    def _render_metrics(result: Dict[str, Any], bt: Dict[str, Any], regime: Dict[str, Any]):
        c = st.columns(6)
        c[0].metric('Master Score', f"{result.get('master_score','-')}/10" if isinstance(result, dict) else '-')
        c[1].metric('Bull Probability', f"{result.get('bull_probability','-')}%" if isinstance(result, dict) else '-')
        c[2].metric('Current Regime', regime.get('current_regime','-') if isinstance(regime, dict) else '-')
        c[3].metric('Direction Accuracy', f"{bt.get('direction_accuracy_pct','-')}%" if isinstance(bt, dict) else '-')
        c[4].metric('Avg Close Error', f"{bt.get('avg_abs_close_error_pct','-')}%" if isinstance(bt, dict) else '-')
        c[5].metric('Days In Regime', regime.get('days_since_last_change', regime.get('days_since_change','-')) if isinstance(regime, dict) else '-')

    def _render_main_powerbi_section(density: str):
        d = st.session_state.get('dv_pp_df', pd.DataFrame())
        result = st.session_state.get('dv_pp_base_result', {}) or {}
        predicted = st.session_state.get('dv_pp_predicted', pd.DataFrame())
        bt_hist = st.session_state.get('dv_pp_bt_hist', pd.DataFrame())
        projection_history = st.session_state.get('dv_pp_projection_history', pd.DataFrame())
        bt = st.session_state.get('dv_pp_bt_summary', {}) or {}
        regime = st.session_state.get('dv_pp_regime_summary', {}) or {}
        _render_metrics(result, bt, regime)
        try:
            _call('_dv_render_candle_powerbi_chart_v20260609', d, predicted, bt_hist, projection_history)
        except Exception as exc:
            st.warning(f'Unified PowerBI chart skipped safely: {exc}')
        max_h = 180 if density == 'Phone Safe' else 260 if density == 'Balanced' else 360
        show = st.multiselect('Extra chart tables', ['Future candles', 'Prediction vs actual close error', 'Dynamic projection history'], default=['Prediction vs actual close error'], key='dv_two_extra_tables')
        if 'Future candles' in show and isinstance(predicted, pd.DataFrame) and not predicted.empty:
            st.dataframe(_sort(predicted), use_container_width=True, hide_index=True, height=max_h)
        if 'Prediction vs actual close error' in show and isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
            st.dataframe(_sort(bt_hist), use_container_width=True, hide_index=True, height=max_h)
        if 'Dynamic projection history' in show and isinstance(projection_history, pd.DataFrame) and not projection_history.empty:
            st.dataframe(_sort(projection_history), use_container_width=True, hide_index=True, height=max_h)

    def _render_restored_technical_metrics(d: Any, result: Dict[str, Any], predicted: Any, density: str) -> None:
        """Restore the st.metric boards that existed before the two-section wrapper.

        This stays inside the new combined section, so the public Data Visualization
        tab still has only two open/close sections. It does not train models or
        change existing calculations; it only reuses stored results from Run Calculating.
        """
        tech_compute = ns.get('_u11_compute_technical_logic')
        if callable(tech_compute) and isinstance(d, pd.DataFrame) and not d.empty:
            try:
                horizon = int(st.session_state.get('dv_two_horizon', st.session_state.get('dv_pp_horizon_v6', 24)) or 24)
                pack = tech_compute(d, result, predicted, horizon=horizon)
                st.session_state['technical_logic_upgrade_v20260611'] = pack
                s = pack.get('summary', {}) if isinstance(pack, dict) else {}
                st.markdown('#### 🧠 Restored Technical Logic Metrics')
                c = st.columns(4)
                c[0].metric('Priority #1', str(s.get('Priority #1','-')))
                c[1].metric('Market Quality 0–100', s.get('Market Quality Score','-'))
                c[2].metric('Conflict Engine', 'CONFLICT' if s.get('Conflict') else 'OK', s.get('Counter Trend Label','-'))
                c[3].metric('Forecast Agreement', f"{s.get('Forecast Agreement Score','-')}%")
                e = st.columns(3)
                e[0].metric('Next 1H Reasonable Expectation', str(s.get('Next 1H','-')))
                e[1].metric('Today Reasonable Expectation', str(s.get('Today','-')))
                e[2].metric('MTF Regime', f"{s.get('Regime Direction','-')} vs {s.get('Prediction Direction','-')}", f"MTF {s.get('MTF Agreement %','-')}%")
                with st.expander('Open / Close — Restored technical tables inside combined section', expanded=False):
                    mtf = pack.get('mtf_table') if isinstance(pack, dict) else None
                    forecast = pack.get('forecast_table') if isinstance(pack, dict) else None
                    rel = pack.get('reliability_history') if isinstance(pack, dict) else None
                    cone = pack.get('probability_cone') if isinstance(pack, dict) else None
                    st.json(s)
                    max_h = 180 if density == 'Phone Safe' else 260 if density == 'Balanced' else 340
                    for label, df in [('MTF H1/H4/D1', mtf), ('Forecast agreement', forecast), ('Reliability history', rel), ('Probability cone', cone)]:
                        if isinstance(df, pd.DataFrame) and not df.empty:
                            st.markdown(f'##### {label}')
                            st.dataframe(_sort(df), use_container_width=True, hide_index=True, height=max_h)
            except Exception as exc:
                st.caption(f'Restored technical metrics skipped safely: {exc}')

    def _render_restored_important_fact_metrics(density: str) -> None:
        mfn = ns.get('_advanced_efficiency_metrics_20260611')
        m = mfn() if callable(mfn) else (st.session_state.get('advanced_efficiency_metrics_20260611') or {})
        if not isinstance(m, dict) or not m:
            return
        st.session_state['advanced_efficiency_metrics_20260611'] = m
        st.markdown('#### ⭐ Restored Important Fact Metrics')
        facts = [
            ('Best Current Opportunity', m.get('Best Current Opportunity','-')),
            ('Current Regime', m.get('Current Regime','-')),
            ('Regime Gate Status', m.get('Regime Gate Status','-')),
            ('KNN Priority', m.get('KNN Priority','-')),
            ('Greedy Priority', m.get('Greedy Priority','-')),
            ('Forecast Agreement', f"{m.get('Forecast Agreement','-')}%"),
            ('Forecast Confidence', m.get('Forecast Confidence','-')),
            ('Market Health', f"{m.get('Market Health','-')}/100"),
            ('Execution Quality', f"{m.get('Execution Quality','-')}/100 {m.get('Execution Label','')}"),
            ('Survival Score', f"{m.get('Survival Score','-')}/100"),
            ('Tail Risk', f"{m.get('Tail Risk','-')}/100 {m.get('Tail Risk Label','')}"),
            ('Drawdown Cluster Status', m.get('Drawdown Cluster Status','-')),
            ('Forecast Freshness', f"{m.get('Forecast Freshness','-')} ({m.get('Forecast Age','-')})"),
            ('Volatility State', m.get('Volatility State','-')),
            ('Highest Risk Warning', m.get('Highest Risk Warning','-')),
        ]
        cols = st.columns(3)
        for i, (k, v) in enumerate(facts):
            cols[i % 3].metric(k, v)
        with st.expander('Open / Close — Restored advanced metric boards inside combined section', expanded=False):
            max_h = 180 if density == 'Phone Safe' else 260 if density == 'Balanced' else 340
            st.markdown('##### Regime Gate + Decision Vote Board')
            st.dataframe(pd.DataFrame([{'Regime Gate':m.get('Regime Gate Status'), 'Permission':m.get('Regime Permission'), 'BUY Votes':m.get('BUY Votes'), 'SELL Votes':m.get('SELL Votes'), 'WAIT Votes':m.get('WAIT Votes'), 'Final Label':m.get('Final Label'), 'Conflict Votes':m.get('Conflict Votes')}]), use_container_width=True, hide_index=True, height=max_h)
            st.markdown('##### Profit Factor + Survival / Cost / Tail Risk')
            st.dataframe(pd.DataFrame([{'PF 50':m.get('PF 50'), 'PF 100':m.get('PF 100'), 'PF 200':m.get('PF 200'), 'PF 500':m.get('PF 500'), 'PF Agreement':m.get('PF Agreement'), 'Profit Factor Consensus Score':m.get('Profit Factor Consensus Score'), 'Survival Score':m.get('Survival Score'), 'Cost/Friction Risk':m.get('Cost/Friction Risk'), 'Tail Risk':m.get('Tail Risk'), 'Tail Risk Label':m.get('Tail Risk Label')}]), use_container_width=True, hide_index=True, height=max_h)
            st.markdown('##### Forecast Greeks + Forecast Aging')
            st.dataframe(pd.DataFrame([{'Delta Score':m.get('Delta Score'), 'Gamma Score':m.get('Gamma Score'), 'Theta Score':m.get('Theta Score'), 'Vega Score':m.get('Vega Score'), 'Direction Sensitivity':m.get('Direction Sensitivity'), 'Forecast Stability':m.get('Forecast Stability'), 'Forecast Freshness':m.get('Forecast Freshness'), 'Forecast Age':m.get('Forecast Age'), 'Forecast Decay %':m.get('Forecast Decay %')}]), use_container_width=True, hide_index=True, height=max_h)
            st.markdown('##### Volatility Surface + Expected Move')
            row = {'H1 Volatility':m.get('H1 Volatility'), 'H4 Volatility':m.get('H4 Volatility'), 'D1 Volatility':m.get('D1 Volatility'), 'W1 Volatility':m.get('W1 Volatility'), 'Volatility State':m.get('Volatility State'), 'Volatility Regime Score':m.get('Volatility Regime Score'), 'Compression Detector':m.get('Volatility Compression')}
            if isinstance(m.get('Expected Move'), dict):
                row.update(m.get('Expected Move'))
            st.dataframe(pd.DataFrame([row]), use_container_width=True, hide_index=True, height=max_h)

    def _render_combined_section(density: str):
        d = st.session_state.get('dv_pp_df', pd.DataFrame())
        result = st.session_state.get('dv_pp_base_result', {}) or {}
        predicted = st.session_state.get('dv_pp_predicted', pd.DataFrame())
        bt_hist = st.session_state.get('dv_pp_bt_hist', pd.DataFrame())
        bt = st.session_state.get('dv_pp_bt_summary', {}) or {}
        regime = st.session_state.get('dv_pp_regime_summary', {}) or {}
        regime_hist = st.session_state.get('dv_pp_regime_hist', pd.DataFrame())
        projection_history = st.session_state.get('dv_pp_projection_history', pd.DataFrame())
        lightblue = st.session_state.get('dv_pp_lightblue_path', pd.DataFrame())
        mfn = ns.get('_advanced_efficiency_metrics_20260611')
        m = mfn() if callable(mfn) else {}
        c = st.columns(5)
        c[0].metric('Combined Rows', len(d) if isinstance(d, pd.DataFrame) else 0)
        c[1].metric('Market Quality', m.get('Market Health', '-'))
        c[2].metric('Forecast Agreement', f"{m.get('Forecast Agreement','-')}%" if m else '-')
        c[3].metric('Correct Data Check', 'OK' if isinstance(d, pd.DataFrame) and len(d) >= 120 else '-')
        c[4].metric('Migrate Section', 'Visible')
        st.info('All previous Data Visualization secondary sections are combined here. Heavy logic runs only after the Run Calculating button above.')
        _render_restored_technical_metrics(d, result, predicted, density)
        _render_restored_important_fact_metrics(density)
        tabs = st.tabs(['Priority', 'ML tables', 'Regime + reliability', 'NY/London + history', 'JSON export'])
        with tabs[0]:
            facts = {
                'Best Current Opportunity': m.get('Best Current Opportunity','-'),
                'KNN Priority': m.get('KNN Priority','-'),
                'Greedy Priority': m.get('Greedy Priority','-'),
                'Execution Quality': m.get('Execution Quality','-'),
                'Tail Risk': m.get('Tail Risk','-'),
                'Highest Risk Warning': m.get('Highest Risk Warning','-'),
            }
            st.dataframe(pd.DataFrame([facts]), use_container_width=True, hide_index=True)
        with tabs[1]:
            frames = []
            if isinstance(result, dict):
                for key, label in [('vote_df','Ensemble Vote Table'), ('deep_df','Deep AI Table'), ('forecast_df','Forecast Table'), ('history','PowerBI History')]:
                    df = result.get(key)
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        st.markdown(f'##### {label}')
                        st.dataframe(_sort(df), use_container_width=True, hide_index=True, height=220)
                        frames.append(label)
            if not frames:
                st.info('No ML table is available yet. Press Run Calculating first.')
        with tabs[2]:
            _render_metrics(result, bt, regime)
            if isinstance(regime_hist, pd.DataFrame) and not regime_hist.empty:
                st.dataframe(_sort(regime_hist), use_container_width=True, hide_index=True, height=280)
            if isinstance(bt_hist, pd.DataFrame) and not bt_hist.empty:
                st.markdown('##### Prediction vs actual close error / dynamic projection')
                st.dataframe(_sort(bt_hist), use_container_width=True, hide_index=True, height=280)
        with tabs[3]:
            st.caption('NY/London helper uses stored calculated OHLC only; it does not train or alter models.')
            if isinstance(d, pd.DataFrame) and not d.empty and 'time' in d.columns:
                start_hour = st.selectbox('Start threshold hour', list(range(24)), index=21, key='dv_two_ny_start')
                hours = [int((start_hour + i) % 24) for i in range(6)]
                x = d.copy(); x['Hour'] = pd.to_datetime(x['time'], errors='coerce').dt.hour; x['Day'] = pd.to_datetime(x['time'], errors='coerce').dt.date
                show = x[x['Hour'].isin(hours)].tail(25*24).copy()
                if not show.empty:
                    show['Window Order'] = show['Hour'].map({h:i+1 for i,h in enumerate(hours)})
                    show['Score /10'] = (5 + (pd.to_numeric(show.get('close'), errors='coerce').pct_change().fillna(0)*10000).clip(-3,3)).round(2)
                    show['Decision'] = show['Score /10'].apply(lambda v: 'ALLOWED' if v>=6.2 else 'NO TRADE' if v<=3.8 else 'WAIT / PULLBACK')
                    cols = [c for c in ['Day','Hour','Window Order','open','high','low','close','Score /10','Decision'] if c in show.columns]
                    st.dataframe(_sort(show[cols]), use_container_width=True, hide_index=True, height=280)
                else:
                    st.info('No rows found for selected next 6 hours.')
            else:
                st.info('Run Calculating first to populate NY/London helper.')
        with tabs[4]:
            payload = {
                'export_type':'DATA_VISUALIZATION_TWO_SECTION_CLEAN_20260611',
                'summary': {'advanced_metrics': m, 'prediction_backtest_summary': bt, 'regime_summary': regime},
                'future_blue_predicted_candles': _sort(predicted).to_dict('records') if isinstance(predicted, pd.DataFrame) else [],
                'prediction_vs_actual_close_error': _sort(bt_hist).head(250).to_dict('records') if isinstance(bt_hist, pd.DataFrame) else [],
                'dynamic_projection_history': _sort(projection_history).head(250).to_dict('records') if isinstance(projection_history, pd.DataFrame) else [],
                'current_lightblue_path': _sort(lightblue).to_dict('records') if isinstance(lightblue, pd.DataFrame) else [],
            }
            st.session_state['lunch_visualization_export'] = json.dumps(payload, indent=2, default=str)
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button('Copy Data Visualization Combined Export', st.session_state['lunch_visualization_export'], 'copy_dv_two_section_20260611')
            except Exception:
                st.json(payload)

    def _render_dv_two_section():
        st.markdown('### 📊 Data Visualization')
        rows, horizon, min_days, bt, density = _render_choice_controls()
        run = st.button('▶ Run Calculating — Data Visualization + Combined Section', use_container_width=True, key='dv_two_run_calculating_20260611')
        if run:
            with st.spinner('Running Data Visualization calculation once, then reusing stored result for all combined sections…'):
                _run_dv_calculation(rows, horizon, min_days, bt)
        err = st.session_state.get('dv_two_section_error_20260611','')
        if err:
            st.warning(err)
        if not st.session_state.get('dv_two_section_ready_20260611'):
            st.info('Press Run Calculating. The tab now stays clean and heavy work does not start automatically.')
            return
        with st.expander('📈 Open / Close — Data Visualization — One Unified PowerBI Price Projection', expanded=True):
            _render_main_powerbi_section(density)
        with st.expander('🧩 Open / Close — Combined Uploaded Photo Sections + KNN/Greedy Logic', expanded=False):
            _render_combined_section(density)
        copybar = ns.get('_render_lunch_copy_refresh_bar')
        if callable(copybar):
            copybar()

    ns['_render_lunch_data_visualization_inner_tab'] = _render_dv_two_section
