"""2026-06-11 Advanced Efficiency / Reliability Control Center.

Additive display/ranking layer only. It reads existing session results, stored
history tables, forecast/regime summaries and OHLC candles. It never trains a
new ML model, never changes original predictions, and never runs on hidden data
unless the user has already clicked the original Run Calculation buttons.
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st


def install(ns: Dict[str, Any]) -> None:
    def _num(v: Any, default: float = 0.0) -> float:
        try:
            if v is None:
                return float(default)
            if isinstance(v, str):
                v = v.replace('%', '').replace('/10', '').replace(',', '').strip()
            x = float(v)
            if np.isfinite(x):
                return x
        except Exception:
            pass
        return float(default)

    def _clip(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, float(v)))

    def _label_score(score: float, labels: Tuple[str, str, str, str]) -> str:
        s = _num(score, 0)
        if s >= 75: return labels[0]
        if s >= 55: return labels[1]
        if s >= 35: return labels[2]
        return labels[3]

    def _pack() -> Dict[str, Any]:
        p = (st.session_state.get('technical_logic_upgrade_lunch_v20260611') or
             st.session_state.get('technical_logic_upgrade_v20260611') or {})
        return p if isinstance(p, dict) else {}

    def _summary() -> Dict[str, Any]:
        p = _pack(); s = p.get('summary', {}) if isinstance(p, dict) else {}
        return s if isinstance(s, dict) else {}

    def _result() -> Dict[str, Any]:
        r = (st.session_state.get('dv_pp_base_result') or
             st.session_state.get('lunch_5layer_powerbi_result') or {})
        return r if isinstance(r, dict) else {}

    def _regime() -> Dict[str, Any]:
        r = st.session_state.get('dv_pp_regime_summary') or {}
        return r if isinstance(r, dict) else {}

    def _bt() -> Dict[str, Any]:
        b = st.session_state.get('dv_pp_bt_summary') or {}
        return b if isinstance(b, dict) else {}

    def _existing_df(limit: int = 2500) -> pd.DataFrame:
        for key in ('dv_pp_df', 'lunch_5layer_powerbi_df', 'last_df'):
            df = st.session_state.get(key)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df.tail(limit).copy()
        clean = ns.get('_clean_lunch_visual_df')
        if callable(clean):
            try:
                df = clean(limit=limit)
                if isinstance(df, pd.DataFrame):
                    return df.tail(limit).copy()
            except Exception:
                pass
        return pd.DataFrame()

    def _prep(df: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return pd.DataFrame()
        x = df.copy()
        lower = {str(c).lower(): c for c in x.columns}
        ren = {}
        for want in ('time','open','high','low','close','volume'):
            if want in lower and lower[want] != want:
                ren[lower[want]] = want
        x = x.rename(columns=ren)
        if 'close' not in x.columns:
            return pd.DataFrame()
        for c in ('open','high','low','close','volume'):
            if c in x.columns:
                x[c] = pd.to_numeric(x[c], errors='coerce')
        if 'open' not in x.columns: x['open'] = x['close'].shift(1).fillna(x['close'])
        if 'high' not in x.columns: x['high'] = x[['open','close']].max(axis=1)
        if 'low' not in x.columns: x['low'] = x[['open','close']].min(axis=1)
        if 'time' not in x.columns: x['time'] = pd.date_range(end=pd.Timestamp.now(), periods=len(x), freq='h')
        x['time'] = pd.to_datetime(x['time'], errors='coerce')
        x = x.dropna(subset=['time','open','high','low','close']).sort_values('time').drop_duplicates('time', keep='last')
        x['ret'] = x['close'].pct_change().replace([np.inf,-np.inf], np.nan).fillna(0.0)
        x['range'] = (x['high'] - x['low']).abs()
        return x.reset_index(drop=True)

    def _vol_pct(x: pd.DataFrame, bars: int) -> float:
        if x.empty or len(x) < 5: return 0.0
        r = x['ret'].tail(max(5, min(int(bars), len(x))))
        return round(float(r.std() * math.sqrt(max(1, bars)) * 100.0), 5) if len(r) else 0.0

    def _base_metrics() -> Dict[str, Any]:
        s, r, reg, bt = _summary(), _result(), _regime(), _bt()
        df = _prep(_existing_df())
        master = _num(r.get('master_score', s.get('Master Score', 5)), 5)
        bull = _num(r.get('bull_probability', 50), 50)
        agreement = _num(s.get('Forecast Agreement Score', r.get('forecast_confidence', 50)), 50)
        reliability = _num(s.get('Reliability Accuracy %', bt.get('direction_accuracy_pct', 50)), 50)
        mtf = _num(s.get('MTF Agreement %', 50), 50)
        market_quality = _num(s.get('Market Quality Score', 0.34*agreement + .30*reliability + .24*mtf), 50)
        conflict = bool(s.get('Conflict', False))
        if str(s.get('Conflict Status', '')).upper().find('CONFLICT') >= 0:
            conflict = True
        exit_risk = _clip(100 - market_quality + (18 if conflict else 0))
        survival = _clip(0.40*market_quality + 0.30*reliability + 0.20*agreement + 10 - (18 if conflict else 0))
        execution = _clip(0.35*market_quality + 0.25*reliability + 0.25*agreement + 15 - (16 if conflict else 0))
        tail = _clip(100 - survival + _vol_pct(df, 24)*6)
        h1v, h4v, d1v, w1v = _vol_pct(df, 24), _vol_pct(df, 96), _vol_pct(df, 24*5), _vol_pct(df, 24*20)
        vol_score = _clip(50 + (h1v - d1v) * 10) if d1v else _clip(50 + h1v * 8)
        compression = 'Shock' if h1v > max(d1v*1.55, .35) else 'Expansion' if h1v > max(d1v*1.10, .20) else 'Compression' if h1v < max(d1v*.72, .08) else 'Normal'
        pf50 = _clip(40 + market_quality*.34 + reliability*.18 - tail*.08)
        pf100 = _clip(42 + market_quality*.30 + agreement*.20 - tail*.08)
        pf200 = _clip(45 + mtf*.25 + reliability*.22 - tail*.07)
        pf500 = _clip(48 + agreement*.18 + reliability*.20 + market_quality*.12 - tail*.06)
        pf_consensus = round((pf50+pf100+pf200+pf500)/4, 1)
        votes_buy = int(bull >= 54) + int(master >= 5.3) + int(agreement >= 60) + int(market_quality >= 58) + int(pf_consensus >= 58)
        votes_sell = int(bull <= 46) + int(master <= 4.7) + int(str(s.get('Prediction Direction','')).upper() == 'SELL')
        votes_wait = int(conflict) + int(tail >= 65) + int(market_quality < 45) + int(reliability < 45)
        if votes_wait >= 3: final = 'No Trade'
        elif votes_buy >= 4 and votes_wait == 0: final = 'Strong Buy'
        elif votes_buy >= 3 and votes_wait <= 1: final = 'Buy'
        elif votes_sell >= 3 and votes_wait <= 1: final = 'Sell'
        elif votes_sell >= 4 and votes_wait == 0: final = 'Strong Sell'
        else: final = 'Wait / Protect'
        gate = 'BLOCKED' if conflict or tail >= 75 or market_quality < 38 else 'CAUTION' if market_quality < 58 or reliability < 50 else 'ALLOWED'
        permission = 'NO TRADE' if gate == 'BLOCKED' else 'REDUCE SIZE' if gate == 'CAUTION' else 'ALLOW'
        age_text = 'Unknown'; freshness = 'Fresh'; decay = 0.0
        try:
            last_time = pd.to_datetime(reg.get('last_time') or r.get('last_time') or (df['time'].iloc[-1] if not df.empty else pd.Timestamp.now()))
            age_hours = max(0.0, (pd.Timestamp.now(tz=None) - pd.Timestamp(last_time).tz_localize(None)).total_seconds()/3600.0)
            age_text = f'{age_hours:.1f}h'
            decay = round(_clip(age_hours / 24 * 100), 1)
            freshness = 'Fresh' if age_hours <= 2 else 'Good' if age_hours <= 8 else 'Aging' if age_hours <= 24 else 'Expired'
        except Exception:
            pass
        drift = 'HIGH DRIFT' if conflict or (not df.empty and abs(float(df['ret'].tail(24).mean())) > max(float(df['ret'].tail(240).std()), 1e-7)) else 'MEDIUM DRIFT' if market_quality < 55 else 'LOW DRIFT'
        stability = 'Unstable' if drift == 'HIGH DRIFT' or compression == 'Shock' else 'Shifting' if drift == 'MEDIUM DRIFT' or compression == 'Expansion' else 'Stable'
        drawdown_cluster = 'Warning' if tail >= 72 or reliability < 38 else 'Elevated' if tail >= 55 or reliability < 50 else 'Normal'
        expected = {}
        last_close = float(df['close'].iloc[-1]) if not df.empty else 0.0
        for h in (1,4,6,24):
            mv = last_close * max(_vol_pct(df, max(5,h*12))/100.0, 0.0002) * math.sqrt(h/24.0) if last_close else 0.0
            expected[f'Next {h} Hour' if h == 1 else f'Next {h} Hours'] = round(mv, 6)
        return {
            'Best Current Opportunity': final,
            'Current Regime': reg.get('current_regime', r.get('current_regime', '-')),
            'Regime Gate Status': gate,
            'Regime Permission': permission,
            'KNN Priority': st.session_state.get('knn_priority_latest', '-'),
            'Greedy Priority': final,
            'Forecast Agreement': round(agreement, 1),
            'Forecast Confidence': r.get('forecast_confidence', round(agreement,1)),
            'Market Health': round(market_quality, 1),
            'Execution Quality': round(execution, 1),
            'Execution Label': _label_score(execution, ('Excellent','Good','Average','Weak')),
            'Survival Score': round(survival, 1),
            'Survival Label': _label_score(survival, ('Strong Survival','Moderate Survival','Weak Survival','Weak Survival')),
            'Tail Risk': round(tail, 1),
            'Tail Risk Label': _label_score(100-tail, ('Low Risk','Moderate Risk','High Risk','Extreme Risk')),
            'Drawdown Cluster Status': drawdown_cluster,
            'Forecast Freshness': freshness,
            'Forecast Age': age_text,
            'Forecast Decay %': decay,
            'Volatility State': compression,
            'Highest Risk Warning': 'BLOCKED: conflict/tail risk' if gate == 'BLOCKED' else 'CAUTION: use filters' if gate == 'CAUTION' else 'Normal',
            'H1 Volatility': h1v, 'H4 Volatility': h4v, 'D1 Volatility': d1v, 'W1 Volatility': w1v,
            'Volatility Regime Score': round(vol_score,1), 'Volatility Compression': compression,
            'PF 50': round(pf50,1), 'PF 100': round(pf100,1), 'PF 200': round(pf200,1), 'PF 500': round(pf500,1),
            'Profit Factor Consensus Score': pf_consensus,
            'PF Agreement': f"{sum(v>=55 for v in (pf50,pf100,pf200,pf500))}/4 Agreement",
            'BUY Votes': votes_buy, 'SELL Votes': votes_sell, 'WAIT Votes': votes_wait, 'Conflict Votes': int(conflict), 'Final Label': final,
            'Delta Score': round(_clip(abs(bull-50)*2),1),
            'Gamma Score': round(_clip(abs(_vol_pct(df, 4) - _vol_pct(df, 24))*15),1),
            'Theta Score': decay,
            'Vega Score': round(_clip(vol_score),1),
            'Direction Sensitivity': 'High' if abs(bull-50) >= 15 else 'Medium' if abs(bull-50) >= 7 else 'Low',
            'Forecast Stability': 'Stable' if agreement >= 70 and not conflict else 'Moderately Stable' if agreement >= 50 else 'Unstable',
            'Market Stability State': stability,
            'Drift Warning': drift,
            'Cost/Friction Risk': round(_clip(100-execution + _vol_pct(df, 24)*2), 1),
            'Expected Move': expected,
        }

    def _render_fact_center(location: str) -> None:
        m = _base_metrics()
        st.session_state['advanced_efficiency_metrics_20260611'] = m
        st.markdown(f'### ⭐ Important Fact Control Center — {location}')
        st.caption('Display/ranking layer only. It uses existing calculations and stored history; it does not change the original ML predictions.')
        facts = [
            ('Best Current Opportunity', m['Best Current Opportunity']), ('Current Regime', m['Current Regime']),
            ('Regime Gate Status', m['Regime Gate Status']), ('KNN Priority', m['KNN Priority']), ('Greedy Priority', m['Greedy Priority']),
            ('Forecast Agreement', f"{m['Forecast Agreement']}%"), ('Forecast Confidence', m['Forecast Confidence']),
            ('Market Health', f"{m['Market Health']}/100"), ('Execution Quality', f"{m['Execution Quality']}/100 {m['Execution Label']}"),
            ('Survival Score', f"{m['Survival Score']}/100"), ('Tail Risk', f"{m['Tail Risk']}/100 {m['Tail Risk Label']}"),
            ('Drawdown Cluster Status', m['Drawdown Cluster Status']), ('Forecast Freshness', f"{m['Forecast Freshness']} ({m['Forecast Age']})"),
            ('Volatility State', m['Volatility State']), ('Highest Risk Warning', m['Highest Risk Warning']),
        ]
        cols = st.columns(3)
        for i, (k, v) in enumerate(facts):
            cols[i % 3].metric(k, v)

    def _render_advanced_tables(location: str) -> None:
        m = st.session_state.get('advanced_efficiency_metrics_20260611') or _base_metrics()
        with st.expander('Open / Close — Regime Gate + Decision Vote Board', expanded=False):
            c = st.columns(5)
            c[0].metric('Regime Gate', m['Regime Gate Status'])
            c[1].metric('Permission', m['Regime Permission'])
            c[2].metric('BUY Votes', m['BUY Votes'])
            c[3].metric('SELL Votes', m['SELL Votes'])
            c[4].metric('WAIT Votes', m['WAIT Votes'])
            st.dataframe(pd.DataFrame([{'Final Label':m['Final Label'], 'Conflict Votes':m['Conflict Votes'], 'Market Health':m['Market Health'], 'Execution Quality':m['Execution Quality'], 'Survival Score':m['Survival Score'], 'Tail Risk':m['Tail Risk']}]), use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Profit Factor Consensus + Survival / Cost / Tail Risk', expanded=False):
            st.dataframe(pd.DataFrame([{'PF 50':m['PF 50'], 'PF 100':m['PF 100'], 'PF 200':m['PF 200'], 'PF 500':m['PF 500'], 'PF Agreement':m['PF Agreement'], 'Profit Factor Consensus Score':m['Profit Factor Consensus Score'], 'Survival Score':m['Survival Score'], 'Cost/Friction Risk':m['Cost/Friction Risk'], 'Tail Risk':m['Tail Risk'], 'Tail Risk Label':m['Tail Risk Label']}]), use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Forecast Greeks + Forecast Aging', expanded=False):
            st.dataframe(pd.DataFrame([{'Delta Score':m['Delta Score'], 'Gamma Score':m['Gamma Score'], 'Theta Score':m['Theta Score'], 'Vega Score':m['Vega Score'], 'Direction Sensitivity':m['Direction Sensitivity'], 'Forecast Stability':m['Forecast Stability'], 'Forecast Freshness':m['Forecast Freshness'], 'Forecast Age':m['Forecast Age'], 'Forecast Decay %':m['Forecast Decay %']}]), use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Volatility Surface + Expected Move Dashboard', expanded=False):
            row = {'H1 Volatility':m['H1 Volatility'], 'H4 Volatility':m['H4 Volatility'], 'D1 Volatility':m['D1 Volatility'], 'W1 Volatility':m['W1 Volatility'], 'Volatility State':m['Volatility State'], 'Volatility Regime Score':m['Volatility Regime Score'], 'Compression Detector':m['Volatility Compression']}
            row.update(m.get('Expected Move', {}))
            st.dataframe(pd.DataFrame([row]), use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Drawdown Cluster + Non-Stationary Warning', expanded=False):
            st.dataframe(pd.DataFrame([{'Drawdown Cluster Status':m['Drawdown Cluster Status'], 'Market Stability State':m['Market Stability State'], 'Drift Warning':m['Drift Warning'], 'Forecast Stability':m['Forecast Stability'], 'Rule':'Do not force signals; if gate is blocked, WAIT / PROTECT.'}]), use_container_width=True, hide_index=True)
        with st.expander('Open / Close — Edge Location Map + Grid Placement Helper', expanded=False):
            df = _prep(_existing_df())
            if df.empty:
                st.info('Run Calculation first to populate edge/location helpers.')
            else:
                tmp = df.tail(25*24).copy(); tmp['Hour'] = tmp['time'].dt.hour
                tmp['NY/London Overlap'] = tmp['Hour'].isin([12,13,14,15,16])
                by_hour = tmp.groupby('Hour').agg({'ret':'mean','range':'mean'}).reset_index()
                by_hour['Edge Quality'] = (50 + by_hour['ret'].rank(pct=True)*30 + by_hour['range'].rank(pct=True)*20).round(1)
                st.dataframe(by_hour[['Hour','Edge Quality']], use_container_width=True, hide_index=True, height=260)
                st.dataframe(pd.DataFrame([{'Conservative Zone':'Inside lower expected-move band', 'Neutral Zone':'Near current forecast path', 'Aggressive Zone':'Outer expected-move band', 'Risk Band':'Use original chart risk bands only', 'Expected Move Band':json.dumps(m.get('Expected Move', {}))}]), use_container_width=True, hide_index=True)

    def _run_after_prev(prev: Any, location: str) -> None:
        if callable(prev):
            prev()
        try:
            _render_fact_center(location)
            _render_advanced_tables(location)
        except Exception as exc:
            st.warning(f'Advanced efficiency control skipped safely: {exc}')

    prev_lunch = ns.get('_render_metric_home_combined_inner_tab')
    def _render_lunch_adv():
        _run_after_prev(prev_lunch, 'Lunch Tab')
    ns['_render_metric_home_combined_inner_tab'] = _render_lunch_adv

    prev_dv = ns.get('_render_lunch_data_visualization_inner_tab')
    def _render_dv_adv():
        _run_after_prev(prev_dv, 'Data Visualization Tab')
    ns['_render_lunch_data_visualization_inner_tab'] = _render_dv_adv

    prev_finder = ns.get('_render_doo_finder')
    def _render_finder_adv(results=None):
        if callable(prev_finder):
            try:
                prev_finder(results)
            except TypeError:
                prev_finder()
        try:
            _render_fact_center('Finder Tab')
            _render_advanced_tables('Finder Tab')
        except Exception as exc:
            st.caption(f'Finder advanced control skipped safely: {exc}')
    ns['_render_doo_finder'] = _render_finder_adv

    prev_copy = ns.get('_build_lunch_all_copy_text')
    def _build_copy_adv():
        base = prev_copy() if callable(prev_copy) else ''
        m = st.session_state.get('advanced_efficiency_metrics_20260611') or _base_metrics()
        payload = {
            'Important Fact Control Center': {k: m.get(k) for k in ['Best Current Opportunity','Current Regime','Regime Gate Status','KNN Priority','Greedy Priority','Forecast Agreement','Forecast Confidence','Market Health','Execution Quality','Survival Score','Tail Risk','Drawdown Cluster Status','Forecast Freshness','Volatility State','Highest Risk Warning']},
            'KNN Priority': m.get('KNN Priority'), 'Greedy Priority': m.get('Greedy Priority'), 'Best Current Opportunity': m.get('Best Current Opportunity'),
            'Regime Gate': {'Status':m.get('Regime Gate Status'), 'Permission':m.get('Regime Permission')},
            'Profit Factor Consensus': {k:m.get(k) for k in ['PF 50','PF 100','PF 200','PF 500','PF Agreement','Profit Factor Consensus Score']},
            'Decision Vote Board': {k:m.get(k) for k in ['BUY Votes','SELL Votes','WAIT Votes','Conflict Votes','Final Label']},
            'Execution Quality': m.get('Execution Quality'), 'Market Health': m.get('Market Health'), 'Survival Score': m.get('Survival Score'),
            'Cost/Friction Risk': m.get('Cost/Friction Risk'), 'Tail Risk': {'Score':m.get('Tail Risk'), 'Label':m.get('Tail Risk Label')},
            'Drawdown Cluster': m.get('Drawdown Cluster Status'), 'Market Stability State': m.get('Market Stability State'),
            'Forecast Agreement': m.get('Forecast Agreement'), 'Forecast Stability': m.get('Forecast Stability'),
            'Forecast Greeks': {k:m.get(k) for k in ['Delta Score','Gamma Score','Theta Score','Vega Score','Direction Sensitivity']},
            'Forecast Aging': {k:m.get(k) for k in ['Forecast Age','Forecast Freshness','Forecast Decay %']},
            'Volatility Surface': {k:m.get(k) for k in ['H1 Volatility','H4 Volatility','D1 Volatility','W1 Volatility','Volatility State','Volatility Regime Score','Volatility Compression']},
            'Expected Move': m.get('Expected Move'),
            'Edge Location Summary': 'Available in the lazy Edge Location Map expander after Run Calculation.'
        }
        return str(base) + '\n\nADVANCED EFFICIENCY CONTROL 2026-06-11\n' + '='*64 + '\n' + json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    ns['_build_lunch_all_copy_text'] = _build_copy_adv

    ns['_advanced_efficiency_metrics_20260611'] = _base_metrics
