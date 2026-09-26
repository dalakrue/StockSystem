"""2026-06-04 V12 causal 10-reversal patch.

Fixes repainting history: every Home/Finder history row is calculated only from
closed candles available at that hour.  No future/after candles are used.
Core comparison becomes: previous history window -> current closed hour, with
extra prev / prev2 / prev3 ratio+derivative fields added to the 10-point engine.
"""
from __future__ import annotations


def install(g: dict) -> None:
    import math
    import pandas as pd
    import streamlit as st

    base_eval = g.get('_evaluate_reversal_driver_from_values')
    _normalize_local = g.get('_normalize_local')
    _finder_market_snapshot = g.get('_finder_market_snapshot')
    _finder_actual_interval_minutes = g.get('_finder_actual_interval_minutes')
    _format_reversal_period_label = g.get('_format_reversal_period_label', lambda ts: str(ts))
    _loaded_reversal_history_df = g.get('_loaded_reversal_history_df')
    _render_reversal_engine_panel = g.get('_render_reversal_engine_panel')

    def _num(v, default=0.0):
        try:
            x = float(v)
            if math.isnan(x) or math.isinf(x):
                return default
            return x
        except Exception:
            return default

    def _norm(df):
        if not callable(_normalize_local):
            return pd.DataFrame()
        try:
            d = _normalize_local(df).dropna(subset=['time','close']).copy()
            d['time'] = pd.to_datetime(d['time'], errors='coerce')
            d = d.dropna(subset=['time']).sort_values('time').reset_index(drop=True)
            return d
        except Exception:
            return pd.DataFrame()

    def _interval(d):
        try:
            return _finder_actual_interval_minutes(d) if callable(_finder_actual_interval_minutes) else 'unknown'
        except Exception:
            return 'unknown'

    def _hour_block(d, h):
        h = pd.Timestamp(h).floor('h')
        return d[(d['time'] >= h) & (d['time'] < h + pd.Timedelta(hours=1))].copy()

    def _history_window(d, h, hours=3):
        h = pd.Timestamp(h).floor('h')
        return d[(d['time'] >= h - pd.Timedelta(hours=hours)) & (d['time'] < h)].copy()

    def _causal_pair_for_target(data, target_start):
        """Return previous closed context vs the target closed hour only.

        This is the key anti-repaint rule.  The target hour is allowed only after
        it has candle data inside [hour, hour+1h).  Later hours are never read.
        """
        d = _norm(data)
        if d.empty or len(d) < 4:
            return pd.DataFrame(), pd.DataFrame(), 'none'
        h = pd.Timestamp(target_start).floor('h')
        current = _hour_block(d, h)
        previous = _history_window(d, h, hours=3)
        if len(previous) >= 2 and len(current) >= 2:
            return previous, current, 'V12_CAUSAL_prev3h_vs_closed_hour_no_future'

        # H1/sparse fallback: current candle/near block plus only candles before it.
        idxs = d.index[(d['time'] >= h) & (d['time'] < h + pd.Timedelta(hours=1))].tolist()
        if not idxs:
            idxs = d.index[d['time'].dt.floor('h') == h].tolist()
        if not idxs:
            return pd.DataFrame(), pd.DataFrame(), _interval(d)
        idx0 = int(idxs[0])
        cur_end = int(idxs[-1]) + 1
        before = d.iloc[max(0, idx0 - 12):idx0].copy()
        current = d.iloc[idx0:cur_end].copy()
        if len(current) < 2 and idx0 > 0:
            # duplicate one previous row into current context only to make metrics non-zero,
            # but never read rows after the target hour.
            current = d.iloc[max(0, idx0 - 1):cur_end].copy()
        if len(before) >= 2 and len(current) >= 2:
            return before, current, 'V12_CAUSAL_sparse_previous_only_vs_target'
        return pd.DataFrame(), pd.DataFrame(), _interval(d)

    def _window_snapshot(d):
        if callable(_finder_market_snapshot):
            return _finder_market_snapshot(d)
        return {}

    def _pct_ratio(now, prev):
        prev = _num(prev)
        now = _num(now)
        if abs(prev) < 1e-9:
            return 999.0 if now > 0 else (-999.0 if now < 0 else 0.0)
        return now / prev

    def _last_closed_hour(data):
        d = _norm(data)
        if d.empty:
            return None
        max_t = pd.to_datetime(d['time'], errors='coerce').max()
        if pd.isna(max_t):
            return None
        h = pd.Timestamp(max_t).floor('h')
        # current incomplete hour must not rewrite/repaint history.
        if pd.Timestamp(max_t) < h + pd.Timedelta(minutes=55):
            h -= pd.Timedelta(hours=1)
        return h

    def _causal_eval(before, current):
        if not callable(base_eval):
            return {}
        eng = dict(base_eval(before or {}, current or {}))
        b = before or {}; a = current or {}
        bm, am = _num(b.get('move_%')), _num(a.get('move_%'))
        bdve, adve = _num(b.get('dve_%')), _num(a.get('dve_%'))
        bbuy, abuy = _num(b.get('buy_%')), _num(a.get('buy_%'))
        bsell, asell = _num(b.get('sell_%')), _num(a.get('sell_%'))
        bfat, afat = _num(b.get('fat_tail_z')), _num(a.get('fat_tail_z'))
        bk, ak = _num(b.get('kurtosis')), _num(a.get('kurtosis'))

        move_ratio = _pct_ratio(am, bm)
        dve_ratio = _pct_ratio(adve, bdve)
        buy_ratio = _pct_ratio(abuy, bbuy)
        sell_ratio = _pct_ratio(asell, bsell)
        pressure_before = bbuy - bsell
        pressure_now = abuy - asell
        pressure_delta = pressure_now - pressure_before
        old_side = 'BUY' if bbuy >= bsell else 'SELL'
        old_side_weak = (old_side == 'BUY' and abuy <= bbuy - 4) or (old_side == 'SELL' and asell <= bsell - 4)
        opposite_growth = (old_side == 'BUY' and asell >= bsell + 4) or (old_side == 'SELL' and abuy >= bbuy + 4)
        direction_derivative = abs(am - bm)
        ratio_shock = abs(move_ratio) >= 1.45 or (bm * am < 0 and abs(am - bm) >= 0.08)
        derivative_shock = direction_derivative >= 0.18 or abs(pressure_delta) >= 8
        tail_now = abs(afat) >= 1.05 or abs(ak) >= 2.5 or abs(afat - bfat) >= 0.25
        causal_exhaustion = old_side_weak and (opposite_growth or derivative_shock)
        causal_reversal_core = causal_exhaustion and (ratio_shock or derivative_shock or tail_now)

        active = int(_num(eng.get('active_count'), 0))
        weighted = float(_num(eng.get('weighted_score'), 0))
        raw = int(_num(eng.get('raw_active_count', active), active))

        # Promote only causal non-future evidence.  This prevents "no data every day"
        # while still requiring genuine now-vs-prev change.
        if causal_reversal_core and raw >= 5:
            active = max(active, 7)
            weighted = max(weighted, 72.0)
        if causal_reversal_core and tail_now and raw >= 6:
            active = max(active, 8)
            weighted = max(weighted, 82.0)
        # Demote if the engine only likes future/persistence style confirmation but
        # causal ratio/derivative does not support it.
        if active >= 7 and not causal_reversal_core:
            active = min(active, 6)
            weighted = min(weighted, 68.0)

        status = 'EXTREME' if active >= 9 else ('DANGER' if active >= 7 else ('WARNING' if active >= 5 else 'NORMAL'))
        title = 'EXTREME CAUSAL REVERSAL DANGER' if active >= 9 else ('IMPORTANT CAUSAL REVERSAL DANGER' if active >= 7 else ('EARLY CAUSAL REVERSAL WARNING' if active >= 5 else 'NORMAL / NO STRONG CAUSAL REVERSAL'))
        deltas = dict(eng.get('deltas', {}) or {})
        deltas.update({
            'V12_move_ratio_now_vs_prev': round(move_ratio, 4),
            'V12_dve_ratio_now_vs_prev': round(dve_ratio, 4),
            'V12_buy_ratio_now_vs_prev': round(buy_ratio, 4),
            'V12_sell_ratio_now_vs_prev': round(sell_ratio, 4),
            'V12_pressure_delta_now_vs_prev': round(pressure_delta, 3),
            'V12_direction_derivative': round(direction_derivative, 5),
        })
        drivers = list(eng.get('drivers', []) or [])
        drivers.extend([
            {'rank': 'V12-1', 'driver': 'Causal Ratio Shock', 'triggered': 'YES' if ratio_shock else 'NO', 'value_or_change': round(move_ratio, 4), 'impact': 'Very High', 'meaning': 'now hour changes strongly versus previous closed data', 'light': '🟢' if ratio_shock else '⚪'},
            {'rank': 'V12-2', 'driver': 'Causal Pressure Derivative', 'triggered': 'YES' if derivative_shock else 'NO', 'value_or_change': round(pressure_delta, 3), 'impact': 'Very High', 'meaning': 'BUY/SELL pressure changes sharply now versus previous data', 'light': '🟢' if derivative_shock else '⚪'},
            {'rank': 'V12-3', 'driver': 'Old Side Weakening', 'triggered': 'YES' if old_side_weak else 'NO', 'value_or_change': old_side, 'impact': 'High', 'meaning': 'dominant side from previous data loses control in the closed hour', 'light': '🟢' if old_side_weak else '⚪'},
        ])
        eng.update({
            'active_count': int(active),
            'probability_pct': int(max(0, min(100, active * 10))),
            'weighted_score': round(max(0, min(100, weighted)), 2),
            'status': status,
            'title': title,
            'deltas': deltas,
            'drivers': drivers[:13],
            'source_frame': 'V12_CAUSAL_CLOSED_CANDLE_NO_FUTURE',
            'anti_repaint_rule': 'History rows use only previous closed data + selected closed hour; no after/future candles.',
            'causal_reversal_core': bool(causal_reversal_core),
            'causal_exhaustion': bool(causal_exhaustion),
            'causal_ratio_shock': bool(ratio_shock),
            'causal_derivative_shock': bool(derivative_shock),
            'causal_tail_now': bool(tail_now),
            'old_side': old_side,
        })
        return eng

    def _engine_from_hour(data, h):
        pre, cur, mode = _causal_pair_for_target(data, h)
        if len(pre) < 2 or len(cur) < 2:
            return None
        eng = _causal_eval(_window_snapshot(pre), _window_snapshot(cur))
        h = pd.Timestamp(h).floor('h')
        eng.update({
            'period_label': _format_reversal_period_label(h),
            'period_time': h.strftime('%Y-%m-%d %H:%M'),
            'period_day': h.strftime('%A'),
            'scan_mode': mode,
            'pre_rows': int(len(pre)),
            'post_rows': int(len(cur)),
            'current_rows': int(len(cur)),
            'used_future_rows': 0,
            'is_exact_threshold_match': int(eng.get('active_count', 0)) >= 7,
        })
        return eng

    def _evaluate_latest(df=None):
        if df is None:
            df = st.session_state.get('last_df')
        h = _last_closed_hour(df)
        if h is None:
            return None
        eng = _engine_from_hour(df, h)
        if eng:
            eng['period_label'] = f"Latest closed hour {h.strftime('%Y-%m-%d %H:00')}"
            st.session_state['last_reversal_engine'] = eng
        return eng

    def _find_last(df=None, min_count=7, days=25, return_best=True):
        data = _loaded_reversal_history_df(df=df, days=days) if callable(_loaded_reversal_history_df) else _norm(df)
        data = _norm(data)
        if data.empty:
            return None
        latest_completed = _last_closed_hour(data)
        if latest_completed is None:
            return None
        hours = data['time'].dt.floor('h').drop_duplicates().sort_values().tolist()
        hours = [pd.Timestamp(h) for h in hours if pd.Timestamp(h) <= latest_completed]
        best = None
        for h in reversed(hours):
            eng = _engine_from_hour(data, h)
            if not eng:
                continue
            eng['scan_days'] = int(days)
            eng['scan_rows'] = int(len(data))
            key = (int(eng.get('active_count', 0)), float(eng.get('weighted_score', 0)), h.timestamp())
            if best is None or key > best[0]:
                best = (key, eng)
            if int(eng.get('active_count', 0)) >= int(min_count):
                return eng
        return best[1] if (return_best and best) else None

    def _scan_reversal_history_table(df=None, days=25, selected_date=None):
        if selected_date is None:
            data = _loaded_reversal_history_df(df=df, days=days) if callable(_loaded_reversal_history_df) else _norm(df)
        else:
            data = _norm(df)
        data = _norm(data)
        if data.empty:
            return pd.DataFrame(), []
        latest_completed = _last_closed_hour(data)
        if latest_completed is None:
            return pd.DataFrame(), []
        if selected_date is not None:
            start = pd.Timestamp(selected_date).normalize()
            hours = [start + pd.Timedelta(hours=i) for i in range(24)]
            hours = [h for h in hours if h <= latest_completed and not _hour_block(data, h).empty]
        else:
            hours = data['time'].dt.floor('h').drop_duplicates().sort_values().tolist()
            hours = [pd.Timestamp(h) for h in hours if pd.Timestamp(h) <= latest_completed]
        rows, engines = [], []
        for h in hours:
            eng = _engine_from_hour(data, h)
            if not eng:
                continue
            d = eng.get('deltas', {}) or {}
            yes = [str(r.get('driver')) for r in eng.get('drivers', []) if str(r.get('triggered', '')).upper() == 'YES']
            rows.append({
                'date': h.strftime('%Y-%m-%d'),
                'day': h.strftime('%A'),
                'hour': h.strftime('%H:00'),
                '10_reverse_decision': f"{int(eng.get('active_count',0))}/10",
                'raw_drivers': f"{int(eng.get('raw_active_count', eng.get('active_count',0)))}/10",
                'probability_%': int(eng.get('probability_pct',0)),
                'weighted_score': round(_num(eng.get('weighted_score')),2),
                'status': eng.get('status','NORMAL'),
                '7_out_of_10_found': 'YES' if int(eng.get('active_count',0)) >= 7 else 'NO',
                'causal_core': bool(eng.get('causal_reversal_core', False)),
                'old_side': eng.get('old_side','-'),
                'move_ratio_now_prev': d.get('V12_move_ratio_now_vs_prev',0),
                'pressure_delta_now_prev': d.get('V12_pressure_delta_now_vs_prev',0),
                'direction_derivative': d.get('V12_direction_derivative',0),
                'used_future_rows': 0,
                'scan_mode': eng.get('scan_mode','-'),
                'pre_rows': eng.get('pre_rows',0),
                'current_rows': eng.get('current_rows', eng.get('post_rows',0)),
                'main_causes': ' | '.join(yes[:6]),
            })
            engines.append(eng)
        table = pd.DataFrame(rows)
        if not table.empty:
            table = table.sort_values(['date','hour'], ascending=[False,False]).reset_index(drop=True)
            st.session_state['home_reversal_25d_scan'] = table
        return table, engines

    def _finder_detector(results, target_start, target_end):
        rows = []
        for key, res in (results or {}).items():
            label = str(res.get('label', key))
            context = res.get('context_candles')
            if not isinstance(context, pd.DataFrame) or context.empty:
                context = res.get('candles')
            d = _norm(context)
            if d.empty:
                continue
            eng = _engine_from_hour(d, pd.Timestamp(target_start))
            if not eng:
                continue
            b, a, de = eng.get('before',{}), eng.get('after',{}), eng.get('deltas',{}) or {}
            rows.append({
                'frame': label,
                'actual_interval': _interval(d),
                'pre_rows': eng.get('pre_rows',0),
                'current_rows': eng.get('current_rows',0),
                'used_future_rows': 0,
                'scan_mode': eng.get('scan_mode','-'),
                'before_move_%': b.get('move_%',0), 'now_move_%': a.get('move_%',0),
                'move_ratio_now_prev': de.get('V12_move_ratio_now_vs_prev',0),
                'pressure_delta_now_prev': de.get('V12_pressure_delta_now_vs_prev',0),
                'direction_derivative': de.get('V12_direction_derivative',0),
                'before_buy_%': b.get('buy_%',0), 'now_buy_%': a.get('buy_%',0),
                'before_sell_%': b.get('sell_%',0), 'now_sell_%': a.get('sell_%',0),
                'reversal_strength': eng.get('weighted_score',0),
                'active_10_count': int(eng.get('active_count',0)),
                'probability_%': int(eng.get('probability_pct',0)),
                'status': eng.get('status','NORMAL'),
                'causal_core': bool(eng.get('causal_reversal_core', False)),
                'cause': ' | '.join([str(r.get('driver')) for r in eng.get('drivers',[]) if str(r.get('triggered','')).upper() == 'YES'][:6]),
            })
        return pd.DataFrame(rows)

    def _render_home_banner():
        engine = _evaluate_latest()
        if not engine:
            engine = st.session_state.get('last_reversal_engine')
        if not engine:
            return
        st.markdown('### 🚨 V12 Causal Reversal Early Warning Engine')
        st.caption('Anti-repaint: history uses previous closed candles + selected closed hour only. Future/after candles are not used, so old rows should not change after the hour closes.')
        last7 = _find_last(min_count=7, days=25, return_best=True)
        m1, m2, m3 = st.columns(3)
        m1.metric('Current Closed-Hour Reversal', f"{int(engine.get('active_count',0))}/10", f"{int(engine.get('probability_pct',0))}%")
        if last7:
            label = 'Last Locked Time ≥ 7/10' if bool(last7.get('is_exact_threshold_match', False)) else 'Best Locked Time in 25D'
            m2.metric(label, str(last7.get('period_label','-')), f"{int(last7.get('active_count',0))}/10")
        else:
            m2.metric('25D Locked Scan', 'Need more candles', 'connect/refresh')
        m3.metric('Source', 'V12 no future data', str(engine.get('status','NORMAL')))
        if callable(_render_reversal_engine_panel):
            _render_reversal_engine_panel(engine, location='Home V12')

    g['_reversal_pair_for_target'] = _causal_pair_for_target
    g['_evaluate_reversal_driver_from_values'] = _causal_eval
    g['evaluate_latest_reversal_engine'] = _evaluate_latest
    g['_find_last_reversal_threshold_time'] = _find_last
    g['_scan_reversal_history_table'] = _scan_reversal_history_table
    g['_finder_reversal_detector'] = _finder_detector
    g['render_reversal_home_banner'] = _render_home_banner
