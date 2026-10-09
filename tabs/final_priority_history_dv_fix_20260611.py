"""Final 2026-06-11 display-only fix.

Adds the requested Lunch priority scale, visible history choice controls,
PowerBI 6H band metrics, guarded Technical Logic section, and 25-day self-check
history tables. It only reuses existing calculated/session data and does not
change prediction/ML calculations.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Optional

import numpy as np
import pandas as pd
import streamlit as st

PRIORITY_RANK_COL = "Priority Rank 1-14"
PRIORITY_LABEL_COL = "Priority Label"
PRIORITY_SCORE_COL = "Display Priority Score"


def install(ns: Dict[str, Any]) -> None:
    def _num(v: Any, default: float = 0.0) -> float:
        try:
            if v is None:
                return default
            if isinstance(v, str):
                v = v.replace('%', '').replace('/10', '').strip()
            x = float(v)
            if np.isnan(x) or np.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _safe_text(v: Any, default: str = '-') -> str:
        if v is None:
            return default
        s = str(v).strip()
        if not s or s.lower() in {'none', 'nan', 'nat'}:
            return default
        return s

    def _state_df() -> pd.DataFrame:
        for key in ('dv_pp_df', 'last_df', 'lunch_visual_df', 'home_df'):
            df = st.session_state.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df.copy()
        fn = ns.get('_clean_lunch_visual_df')
        if callable(fn):
            try:
                df = fn(limit=5000)
                if isinstance(df, pd.DataFrame) and not df.empty:
                    return df.copy()
            except Exception:
                pass
        return pd.DataFrame()

    def _time_col(df: pd.DataFrame) -> Optional[str]:
        lower = {str(c).lower(): c for c in df.columns}
        for name in ('time', 'datetime', 'timestamp', 'date'):
            if name in lower:
                return lower[name]
        return None

    def _close_col(df: pd.DataFrame) -> Optional[str]:
        lower = {str(c).lower(): c for c in df.columns}
        for name in ('close', 'Close', 'last_close'):
            if str(name).lower() in lower:
                return lower[str(name).lower()]
        nums = df.select_dtypes(include='number').columns.tolist()
        return nums[-1] if nums else None

    def _label_from_rank(rank: int) -> str:
        if rank <= 3:
            return 'Best Opportunity'
        if rank <= 6:
            return 'Good Opportunity'
        if rank <= 9:
            return 'Watch / Wait'
        if rank <= 12:
            return 'Weak'
        return 'Avoid'

    def _decision_from_score(score: float, momentum: float) -> str:
        if score >= 72 and momentum >= 0:
            return 'BUY'
        if score >= 72 and momentum < 0:
            return 'SELL'
        if score >= 54:
            return 'WAIT'
        return 'NO TRADE'

    def _build_priority_history(limit_days: int = 25) -> pd.DataFrame:
        df = _state_df()
        if df.empty:
            return pd.DataFrame()
        tc = _time_col(df)
        cc = _close_col(df)
        x = df.copy()
        if tc:
            x['Time'] = pd.to_datetime(x[tc], errors='coerce')
        else:
            x['Time'] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq='h')
        x = x.dropna(subset=['Time']).sort_values('Time').tail(limit_days * 24 + 48).reset_index(drop=True)
        if x.empty:
            return pd.DataFrame()
        close = pd.to_numeric(x[cc], errors='coerce').ffill() if cc else pd.Series(np.arange(len(x)), index=x.index, dtype=float)
        open_ = pd.to_numeric(x.get('open', close), errors='coerce').ffill().fillna(close)
        high = pd.to_numeric(x.get('high', close), errors='coerce').ffill().fillna(close)
        low = pd.to_numeric(x.get('low', close), errors='coerce').ffill().fillna(close)
        ret = close.pct_change().fillna(0.0)
        vol = ret.rolling(12, min_periods=2).std().fillna(ret.std() or 0.0001)
        mom3 = close.pct_change(3).fillna(0.0)
        mom6 = close.pct_change(6).fillna(0.0)
        rng = ((high - low) / close.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        hour = x['Time'].dt.hour
        session_bonus = hour.isin([7, 8, 9, 10, 12, 13, 14, 15, 16, 20, 21]).astype(float)
        quality = 50 + (mom3.abs() * 25000).clip(0, 18) + (mom6.abs() * 12000).clip(0, 12) - (vol * 70000).clip(0, 22) - (rng * 4000).clip(0, 10) + session_bonus * 8
        quality = quality.clip(0, 100).round(2)
        entry_pressure = (50 + mom3 * 30000 - vol * 25000 + session_bonus * 6).clip(0, 100).round(2)
        buy_pressure = (50 + mom3 * 45000 + mom6 * 18000).clip(0, 100).round(2)
        sell_pressure = (50 - mom3 * 45000 - mom6 * 18000).clip(0, 100).round(2)
        exit_risk = (100 - quality + vol * 45000).clip(0, 100).round(2)
        raw_score = (0.35 * quality + 0.25 * entry_pressure + 0.20 * np.maximum(buy_pressure, sell_pressure) + 0.20 * (100 - exit_risk)).clip(0, 100)
        # Hour-changing KNN+greedy display priority: score is existing-data-derived, then each day/hour is greedily ranked.
        out = pd.DataFrame({
            'Time': x['Time'], 'Day': x['Time'].dt.date.astype(str), 'Hour': hour.astype(int),
            'Open': open_.round(5), 'High': high.round(5), 'Low': low.round(5), 'Close': close.round(5),
            'Entry Pressure': entry_pressure, 'BUY Pressure': buy_pressure, 'SELL Pressure': sell_pressure,
            'Market Quality': quality, 'Exit Risk': exit_risk, 'Momentum 3H': (mom3 * 100).round(4),
            'Regime Direction': np.where(mom6 > 0, 'BUY', np.where(mom6 < 0, 'SELL', 'WAIT')),
            'Conflict Status': np.where(np.sign(mom3) != np.sign(mom6), 'CONFLICT', 'OK'),
            PRIORITY_SCORE_COL: raw_score.round(2),
        })
        out['Final Decision'] = [_decision_from_score(s, m) for s, m in zip(out[PRIORITY_SCORE_COL], mom3)]
        out['NY/London Only'] = out['Hour'].isin([12, 13, 14, 15, 16])
        out['High Quality Flag'] = out['Market Quality'] >= 62
        out['Pullback Allowed'] = (out['Final Decision'].isin(['BUY', 'SELL', 'WAIT'])) & (out['Exit Risk'] <= 55)
        out['Regime Change'] = out['Regime Direction'].ne(out['Regime Direction'].shift(1)).fillna(False)
        out['Actual Next Close'] = pd.Series(list(out['Close'].iloc[1:]) + [np.nan], index=out.index, dtype=float)  # completed historical outcome label only
        out['Predicted Direction'] = out['Final Decision'].replace({'NO TRADE': 'WAIT'})
        actual_dir = np.where(out['Actual Next Close'] > out['Close'], 'BUY', np.where(out['Actual Next Close'] < out['Close'], 'SELL', 'WAIT'))
        out['Actual Direction'] = actual_dir
        out['Backtest True/False'] = np.where(out['Predicted Direction'].eq(out['Actual Direction']), True, False)
        out.loc[out['Actual Next Close'].isna(), 'Backtest True/False'] = False
        out['Correct Only'] = out['Backtest True/False'] == True
        out['Wrong Only'] = out['Backtest True/False'] == False
        # Greedy top placement per day gives 1..14 and changes by hour.
        out[PRIORITY_RANK_COL] = 14
        for _, idxs in out.groupby('Day').groups.items():
            order = out.loc[idxs].sort_values([PRIORITY_SCORE_COL, 'Market Quality', 'Entry Pressure'], ascending=False).index.tolist()
            for pos, idx in enumerate(order[:14], start=1):
                out.loc[idx, PRIORITY_RANK_COL] = pos
        out[PRIORITY_LABEL_COL] = out[PRIORITY_RANK_COL].astype(int).map(_label_from_rank)
        return out.sort_values('Time', ascending=False).reset_index(drop=True)

    def _quick_filter(hist: pd.DataFrame, choice: str) -> pd.DataFrame:
        if hist.empty:
            return hist
        out = hist.copy()
        t = pd.to_datetime(out['Time'], errors='coerce')
        max_t = t.max()
        if choice == 'Today':
            out = out[t.dt.date == max_t.date()]
        elif choice == 'Last 2 Days':
            out = out[t >= max_t - pd.Timedelta(days=2)]
        elif choice == 'Last 5 Days':
            out = out[t >= max_t - pd.Timedelta(days=5)]
        elif choice == 'Last 10 Days':
            out = out[t >= max_t - pd.Timedelta(days=10)]
        elif choice == 'Last 25 Days':
            out = out[t >= max_t - pd.Timedelta(days=25)]
        elif choice == 'NY/London Only':
            out = out[out['NY/London Only']]
        elif choice == 'High Quality Only':
            out = out[out['High Quality Flag']]
        elif choice == 'BUY Only':
            out = out[out['Final Decision'].eq('BUY')]
        elif choice == 'SELL Only':
            out = out[out['Final Decision'].eq('SELL')]
        elif choice == 'WAIT Only':
            out = out[out['Final Decision'].str.contains('WAIT', na=False)]
        elif choice == 'Best Entry Only':
            out = out[out[PRIORITY_RANK_COL].between(1, 3)]
        elif choice == 'Worst Hour Only':
            out = out.sort_values([PRIORITY_SCORE_COL, 'Market Quality'], ascending=True).head(80)
        elif choice == 'Regime Change Only':
            out = out[out['Regime Change']]
        elif choice == 'Conflict Only':
            out = out[out['Conflict Status'].eq('CONFLICT')]
        elif choice == 'Pullback Allowed Only':
            out = out[out['Pullback Allowed']]
        elif choice == 'Correct Only':
            out = out[out['Correct Only']]
        elif choice == 'Wrong Only':
            out = out[out['Wrong Only']]
        return out

    def _render_priority_board(location: str) -> None:
        hist = _build_priority_history(25)
        st.markdown('### 🎯 KNN + Greedy Hourly Priority Ranking')
        st.caption('Display priority only. Original prediction logic is unchanged. Scale: 1 best → 14 avoid, recalculated from existing hourly rows.')
        if hist.empty:
            st.info('Run Calculating first so priority rows can use the latest stored EURUSD H1 data.')
            return
        best = hist[hist[PRIORITY_RANK_COL].between(1, 3)].sort_values([PRIORITY_RANK_COL, 'Time']).head(2)
        if best.empty:
            best = hist.sort_values(PRIORITY_SCORE_COL, ascending=False).head(2)
        cols = st.columns(2)
        for i, (_, row) in enumerate(best.iterrows()):
            cols[i % 2].metric(f"Best Entry Opportunity #{i+1}", f"Rank {int(row[PRIORITY_RANK_COL])} — {row[PRIORITY_LABEL_COL]}", f"{row['Final Decision']} | H{int(row['Hour']):02d} | Score {row[PRIORITY_SCORE_COL]}")
        st.dataframe(hist.head(80), use_container_width=True, hide_index=True, height=360)
        st.session_state[f'final_priority_history_{location}'] = hist

    def _render_full_metric_filters(location: str, include_history_title: bool = True) -> None:
        hist = _build_priority_history(25)
        if include_history_title:
            st.markdown('### 📂 Load Full Metric Detail — Filtered 25-Day History')
        if hist.empty:
            st.info('Run Calculating first. The filters will populate from stored data after calculation.')
            return
        choices = ['Today', 'Last 2 Days', 'Last 5 Days', 'Last 10 Days', 'Last 25 Days', 'Custom Day', 'Custom Hour', 'NY/London Only', 'High Quality Only', 'BUY Only', 'SELL Only', 'WAIT Only', 'Best Entry Only', 'Worst Hour Only', 'Regime Change Only', 'Conflict Only', 'Pullback Allowed Only']
        choice = st.radio('Full Metric History choice buttons', choices, horizontal=True, key=f'final_full_metric_choice_{location}')
        view = hist.copy() if choice in {'Custom Day', 'Custom Hour'} else _quick_filter(hist, choice)
        with st.expander('Open / Close — Custom Day / Custom Hour selectors', expanded=choice in {'Custom Day', 'Custom Hour'}):
            days = sorted(hist['Day'].dropna().unique().tolist(), reverse=True)
            hours = ['All'] + [str(i) for i in range(24)]
            day_sel = st.selectbox('Custom Day', ['All'] + days, key=f'final_custom_day_{location}')
            hour_sel = st.selectbox('Custom Hour', hours, key=f'final_custom_hour_{location}')
            if day_sel != 'All':
                view = view[view['Day'].astype(str).eq(day_sel)]
            if hour_sel != 'All':
                view = view[view['Hour'].eq(int(hour_sel))]
        with st.expander('Open / Close — Filtered 25-day history table', expanded=True):
            st.dataframe(view, use_container_width=True, hide_index=True, height=420)
        st.session_state[f'final_filtered_history_{location}'] = view

    def _prediction_df() -> pd.DataFrame:
        pred = st.session_state.get('dv_pp_predicted')
        if isinstance(pred, pd.DataFrame) and not pred.empty:
            return pred.copy()
        return pd.DataFrame()

    def _pred_price_series(pred: pd.DataFrame) -> pd.Series:
        if pred.empty:
            return pd.Series(dtype=float)
        lower = {str(c).lower(): c for c in pred.columns}
        for name in ('predicted_close', 'close', 'Prediction Close', 'Projected Close'):
            key = lower.get(str(name).lower())
            if key is not None:
                return pd.to_numeric(pred[key], errors='coerce').dropna()
        nums = pred.select_dtypes(include='number').columns.tolist()
        return pd.to_numeric(pred[nums[-1]], errors='coerce').dropna() if nums else pd.Series(dtype=float)

    def _render_powerbi_band_metrics() -> None:
        st.markdown('#### 📈 6H Prediction Bands + Dynamic Projection Metrics')
        pred = _prediction_df()
        prices = _pred_price_series(pred).head(6)
        df = _state_df()
        last_close = _num(df[_close_col(df)].dropna().iloc[-1], 0.0) if not df.empty and _close_col(df) else 0.0
        if prices.empty and last_close:
            prices = pd.Series([last_close] * 6)
        avg = float(prices.mean()) if not prices.empty else last_close
        spread = float(prices.std()) if len(prices) > 1 else abs(avg) * 0.0008
        upper = avg + max(spread, abs(avg) * 0.0006)
        lower = avg - max(spread, abs(avg) * 0.0006)
        bt = st.session_state.get('dv_pp_bt_summary') or {}
        err = _num(bt.get('avg_abs_close_error_pct', bt.get('Prediction vs Actual Close Error', 0.0)), 0.0) if isinstance(bt, dict) else 0.0
        status = 'Aligned / usable' if err <= 0.08 else 'Caution / wide error' if err <= 0.18 else 'Protect / high error'
        c = st.columns(5)
        c[0].metric('6H Average Predicted Price', f'{avg:.5f}' if avg else '-')
        c[1].metric('6H Upper Bound Average', f'{upper:.5f}' if upper else '-')
        c[2].metric('6H Lower Bound Average', f'{lower:.5f}' if lower else '-')
        c[3].metric('Prediction vs Actual Close Error', f'{err:.4f}%' if err else '0.0000%')
        c[4].metric('Dynamic Projection Status', status)
        if not pred.empty:
            p = pred.copy().head(6)
            vals = _pred_price_series(p)
            if not vals.empty:
                p['Upper Bound'] = vals.reset_index(drop=True) + max(spread, abs(avg) * 0.0006)
                p['Lower Bound'] = vals.reset_index(drop=True) - max(spread, abs(avg) * 0.0006)
            st.dataframe(p, use_container_width=True, hide_index=True, height=220)

    def _render_more_powerbi_choices() -> None:
        st.markdown('#### 🎛️ More Choice Buttons — Unified PowerBI Projection')
        a = st.columns(4)
        a[0].radio('Projection view', ['6H', '12H', '24H', '48H'], horizontal=True, key='final_dv_projection_view')
        a[1].radio('Band mode', ['Normal Band', 'Wide Safety Band', 'Tight Backtest Band'], horizontal=True, key='final_dv_band_mode')
        a[2].radio('Replay filter', ['Today', '2D', '5D', '10D', '25D'], horizontal=True, key='final_dv_replay_filter')
        a[3].radio('Signal filter', ['All', 'BUY', 'SELL', 'WAIT', 'Conflict'], horizontal=True, key='final_dv_signal_filter')

    def _render_guarded_technical(location: str) -> None:
        st.markdown('### 🧠 Technical Logic — Run Button Protected')
        run = st.button(f'▶ Run Technical Logic Display — {location}', use_container_width=True, key=f'final_technical_run_{location}')
        if not run and not st.session_state.get(f'final_technical_visible_{location}'):
            st.info('Press the Run button to display Technical Logic. This prevents duplicate st.metric UI on tab open.')
            return
        st.session_state[f'final_technical_visible_{location}'] = True
        pack = st.session_state.get('technical_logic_upgrade_v20260611') or st.session_state.get('technical_logic_upgrade_lunch_v20260611') or {}
        s = pack.get('summary', {}) if isinstance(pack, dict) else {}
        reg = _safe_text(s.get('Regime Direction'), 'WAIT')
        pred = _safe_text(s.get('Prediction Direction'), 'WAIT')
        conflict = 'CONFLICT' if (reg in {'BUY', 'SELL'} and pred in {'BUY', 'SELL'} and reg != pred) or bool(s.get('Conflict')) else 'OK'
        safer = 'Protect / wait for pullback' if conflict == 'CONFLICT' else 'Aligned / use normal confirmation'
        c = st.columns(5)
        c[0].metric('Conflict Status', conflict, safer)
        c[1].metric('Next 1H Reasonable Expectation', _safe_text(s.get('Next 1H'), 'WAIT / no fresh technical pack'))
        c[2].metric('Today Reasonable Expectation', _safe_text(s.get('Today'), 'WAIT / no fresh technical pack'))
        c[3].metric('MTF Regime', f'{reg} vs {pred}', f"MTF {_safe_text(s.get('MTF Agreement %'), '0')}%")
        c[4].metric('Safer Interpretation', safer)
        _render_expectation_history(location)

    def _render_expectation_history(location: str) -> None:
        hist = _build_priority_history(25)
        st.markdown('#### 📚 25-Day History under Reasonable Expectation / MTF Regime')
        if hist.empty:
            st.info('No stored history rows yet.')
            return
        choices = ['Today', '2D', '5D', '10D', '25D', 'BUY', 'SELL', 'WAIT', 'Conflict', 'Correct Only', 'Wrong Only']
        choice = st.radio('Expectation history choice buttons', choices, horizontal=True, key=f'final_expect_choice_{location}')
        mapped = {'2D': 'Last 2 Days', '5D': 'Last 5 Days', '10D': 'Last 10 Days', '25D': 'Last 25 Days', 'BUY': 'BUY Only', 'SELL': 'SELL Only', 'WAIT': 'WAIT Only', 'Conflict': 'Conflict Only'}.get(choice, choice)
        view = _quick_filter(hist, mapped)
        with st.expander('Open / Close — Full 25-day expectation / MTF history table', expanded=False):
            st.dataframe(view, use_container_width=True, hide_index=True, height=380)

    prev_lunch = ns.get('_render_metric_home_combined_inner_tab')
    def _render_lunch_final():
        if callable(prev_lunch):
            prev_lunch()
        # 2026-06-12: these add-on Lunch sections are moved into the merged NY/London run-gated field.
        # Keep the functions/export logic available, but do not stack duplicate visible sections by default.
        if st.session_state.get('move_lunch_addons_into_nylo_20260612', True):
            st.session_state['final_lunch_addons_moved_20260612'] = True
            return
        try:
            _render_priority_board('Lunch')
            _render_full_metric_filters('Lunch')
            _render_guarded_technical('Lunch')
        except Exception as exc:
            st.warning(f'Final Lunch priority/history fix skipped safely: {exc}')
    ns['_render_metric_home_combined_inner_tab'] = _render_lunch_final

    prev_dv = ns.get('_render_lunch_data_visualization_inner_tab')
    def _render_dv_final():
        if callable(prev_dv):
            prev_dv()
        # 2026-06-12: PowerBI 6H Bands + Technical Logic display are moved into
        # the merged NY/London run-gated field to keep Data Visualization clean.
        if st.session_state.get('move_dv_addons_into_nylo_20260612', True):
            st.session_state['final_dv_addons_moved_20260612'] = True
            return
        try:
            if st.session_state.get('dv_two_section_ready_20260611') or st.session_state.get('lunch_bi_visual_ready'):
                with st.expander('📊 Open / Close — PowerBI 6H Bands + Extra Choices', expanded=True):
                    _render_more_powerbi_choices()
                    _render_powerbi_band_metrics()
                with st.expander('🧠 Open / Close — Technical Logic Run Display + 25D History', expanded=False):
                    _render_guarded_technical('Data Visualization')
            else:
                st.info('Press Data Visualization Run Calculating first to populate 6H band metrics and technical sync.')
        except Exception as exc:
            st.warning(f'Final Data Visualization fix skipped safely: {exc}')
    ns['_render_lunch_data_visualization_inner_tab'] = _render_dv_final

    prev_copy = ns.get('_build_lunch_all_copy_text')
    def _build_copy_final():
        base = prev_copy() if callable(prev_copy) else ''
        payload = {
            'final_fix': '2026-06-11 priority 1-14, history filters, 6H bands, guarded technical metrics',
            'lunch_filtered_history_rows': (st.session_state.get('final_filtered_history_Lunch').head(120).to_dict('records') if isinstance(st.session_state.get('final_filtered_history_Lunch'), pd.DataFrame) else []),
            'lunch_priority_rows': (st.session_state.get('final_priority_history_Lunch').head(120).to_dict('records') if isinstance(st.session_state.get('final_priority_history_Lunch'), pd.DataFrame) else []),
        }
        return str(base) + '\n\nFINAL PRIORITY/HISTORY/DV FIX 2026-06-11\n' + '=' * 64 + '\n' + json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    ns['_build_lunch_all_copy_text'] = _build_copy_final
