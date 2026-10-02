"""2026-06-11 Finder alignment upgrade.
Non-destructive wrapper: keeps existing Finder renderer, then adds a Run Calculation gated
Finder decision layer aligned with Lunch/Data Visualization metrics.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def install(ns: Dict[str, Any]) -> None:
    try:
        import streamlit as st
        import pandas as pd
        import numpy as np
    except Exception:
        return

    prev = ns.get("_render_doo_finder")

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            if v is None or (isinstance(v, float) and np.isnan(v)):
                return default
            return float(v)
        except Exception:
            return default

    def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
        return max(lo, min(hi, float(v)))

    def _as_df(obj: Any) -> "pd.DataFrame":
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.copy()
            if isinstance(obj, (list, tuple)):
                return pd.DataFrame(obj)
            if isinstance(obj, dict):
                return pd.DataFrame(obj)
        except Exception:
            pass
        return pd.DataFrame()

    def _normalize(df: "pd.DataFrame") -> "pd.DataFrame":
        d = _as_df(df)
        if d.empty:
            return d
        cols = {str(c).lower().strip(): c for c in d.columns}
        time_col = next((cols[x] for x in ("time", "datetime", "date", "timestamp") if x in cols), None)
        close_col = next((cols[x] for x in ("close", "price", "last") if x in cols), None)
        if time_col is None:
            d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
        else:
            d["time"] = pd.to_datetime(d[time_col], errors="coerce")
        if close_col is None:
            for c in d.columns:
                if pd.api.types.is_numeric_dtype(d[c]):
                    close_col = c
                    break
        if close_col is not None:
            d["close"] = pd.to_numeric(d[close_col], errors="coerce")
        for name in ("open", "high", "low"):
            if name not in d.columns:
                d[name] = d.get("close", 0)
            d[name] = pd.to_numeric(d[name], errors="coerce")
        d = d.dropna(subset=["time", "close"]).sort_values("time").reset_index(drop=True)
        return d

    def _get_candles(results: Any) -> "pd.DataFrame":
        candidates: List[Any] = []
        if isinstance(results, dict):
            for v in results.values():
                if isinstance(v, dict):
                    candidates += [v.get("context_candles"), v.get("candles"), v.get("df"), v.get("data")]
                else:
                    candidates.append(v)
        for key in ("latest_candles", "candles", "eurusd_h1_df", "powerbi_candles", "doo_candles"):
            candidates.append(st.session_state.get(key))
        best = pd.DataFrame()
        for item in candidates:
            d = _normalize(item)
            if len(d) > len(best):
                best = d
        return best

    def _direction_from_change(change: float) -> str:
        if change > 0.00002:
            return "BULL"
        if change < -0.00002:
            return "BEAR"
        return "RANGE"

    def _calc_pack(results: Any, selected_day: str, selected_hour: int) -> Dict[str, Any]:
        d = _get_candles(results)
        if d.empty:
            now = pd.Timestamp.now().floor("h")
            base = 1.1550
            d = pd.DataFrame({"time": pd.date_range(now - pd.Timedelta(hours=72), periods=73, freq="h")})
            wave = np.sin(np.arange(len(d)) / 5.0) * 0.0015
            d["close"] = base + wave
            d["open"] = d["close"].shift(1).fillna(d["close"])
            d["high"] = d[["open", "close"]].max(axis=1) + 0.0005
            d["low"] = d[["open", "close"]].min(axis=1) - 0.0005
        days = [str(x) for x in pd.to_datetime(d["time"]).dt.date.drop_duplicates().tail(30)]
        if selected_day not in days:
            selected_day = days[-1]
        target = pd.Timestamp(f"{selected_day} {int(selected_hour):02d}:00")
        row_df = d[pd.to_datetime(d["time"]).dt.floor("h") == target]
        idx = int(row_df.index[-1]) if not row_df.empty else int((pd.to_datetime(d["time"]) - target).abs().idxmin())
        row = d.iloc[idx]
        hist = d.iloc[max(0, idx - 24): idx + 1]
        last2 = d.iloc[max(0, idx - 48): idx + 1].copy()
        close = _num(row.get("close"), 1.0)
        prev_close = _num(d.iloc[max(0, idx - 1)].get("close"), close)
        change = close - prev_close
        vol = _num(hist["close"].pct_change().abs().tail(12).mean(), 0.0005)
        trend = close - _num(hist["close"].head(1).iloc[0], close)
        regime_dir = _direction_from_change(trend)
        pred_dir = _direction_from_change(change + trend * 0.18)
        conflict = "CONFLICT" if regime_dir in ("BULL", "BEAR") and pred_dir in ("BULL", "BEAR") and regime_dir != pred_dir else "ALIGNED"
        master = _clamp(50 + trend / max(close, 1e-9) * 9000 - vol * 20000)
        entry = _clamp(50 + change / max(close, 1e-9) * 14000 - (25 if conflict == "CONFLICT" else 0))
        hold = _clamp(100 - vol * 45000 - (15 if conflict == "CONFLICT" else 0))
        exit_risk = _clamp(vol * 55000 + (20 if conflict == "CONFLICT" else 5))
        tpq = _clamp((entry * 0.35) + (hold * 0.25) + (100 - exit_risk) * 0.25 + master * 0.15)
        market_quality = _clamp(100 - vol * 42000 + (10 if conflict == "ALIGNED" else -10))
        forecast_agreement = _clamp(70 + (15 if conflict == "ALIGNED" else -25) + abs(trend) / max(close, 1e-9) * 2000)
        reliability = _clamp((hold * 0.35) + (market_quality * 0.30) + (forecast_agreement * 0.20) + ((100 - exit_risk) * 0.15))
        h1 = 100 if regime_dir == pred_dir else 50
        h4 = _clamp(50 + (close - _num(hist["close"].tail(min(4, len(hist))).head(1).iloc[0], close)) / max(close, 1e-9) * 9000)
        d1 = _clamp(50 + trend / max(close, 1e-9) * 7000)
        align = _clamp(h1 * .20 + h4 * .15 + d1 * .15 + forecast_agreement * .20 + market_quality * .15 + reliability * .10 + (0 if conflict == "CONFLICT" else 5))
        if conflict == "CONFLICT" and reliability < 60:
            final = "NO TRADE"
        elif exit_risk >= 70 or market_quality < 45:
            final = "HOLD / PROTECT"
        elif conflict == "CONFLICT":
            final = "WAIT PULLBACK"
        elif align >= 65 and reliability >= 55:
            final = "ALLOWED"
        else:
            final = "WAIT PULLBACK"
        counter = "COUNTER-TREND" if conflict == "CONFLICT" else "NORMAL"
        factors = [
            ("Exit Risk", exit_risk, "Highest risk control / protect first"),
            ("Forecast Agreement", 100 - forecast_agreement, "Models disagree with the selected hour"),
            ("Conflict Engine", 90 if conflict == "CONFLICT" else 20, "Regime direction vs prediction direction"),
            ("Market Quality", 100 - market_quality, "Low quality means more noise"),
            ("Reliability", 100 - reliability, "Previous/path confidence weakness"),
        ]
        factors = sorted(factors, key=lambda x: x[1], reverse=True)[:3]
        next_1h = "Bullish continuation" if pred_dir == "BULL" and conflict == "ALIGNED" else ("Bearish pressure" if pred_dir == "BEAR" and conflict == "ALIGNED" else "Pullback / mixed range")
        today = "Aligned trend day" if align >= 65 and conflict == "ALIGNED" else ("Protective mixed day" if conflict == "CONFLICT" else "Range / wait for confirmation")
        last2 = last2.copy()
        last2["previous_predicted_path"] = last2["close"].shift(1).fillna(last2["close"]) + (last2["close"].diff().rolling(3).mean().fillna(0))
        last2["prediction_error_%"] = ((last2["previous_predicted_path"] - last2["close"]).abs() / last2["close"].replace(0, np.nan) * 100).fillna(0)
        last2["direction_correct"] = np.where(np.sign(last2["previous_predicted_path"].diff().fillna(0)) == np.sign(last2["close"].diff().fillna(0)), "CORRECT", "WRONG")
        step = np.arange(1, 7)
        slope = change if abs(change) > 0 else trend / max(len(hist), 1)
        future = close + slope * step
        band = max(vol * close * 2.5, 0.00035)
        cone = pd.DataFrame({
            "step": step,
            "blue_future_path": future,
            "yellow_previous_path": close + (slope * 0.55) * step,
            "upper_band": future + band * step,
            "lower_band": future - band * step,
        })
        return {
            "days": days, "target": target, "master": master, "entry": entry, "hold": hold,
            "exit_risk": exit_risk, "tpq": tpq, "regime": regime_dir, "prediction": pred_dir,
            "market_quality": market_quality, "forecast_agreement": forecast_agreement,
            "reliability": reliability, "conflict": conflict, "counter": counter, "align": align,
            "final": final, "next_1h": next_1h, "today": today, "factors": factors,
            "last2": last2.tail(48), "cone": cone,
        }

    def _render_upgrade(results: Any) -> None:
        del results
        st.markdown("### 🔎 Finder Alignment Engine — Canonical Full Metric Sync")
        canonical = st.session_state.get("canonical_decision_result_20260617")
        if not isinstance(canonical, dict) or not canonical:
            canonical = st.session_state.get("last_valid_canonical_decision_result_20260617")
        if not isinstance(canonical, dict) or not canonical:
            st.info("Run Calculation in Settings. Finder will then rank the same protected Full Metric candidates used by Lunch, Dinner and AI Assistant.")
            return

        final = canonical.get("final_decision", {}) if isinstance(canonical.get("final_decision"), dict) else {}
        pattern = canonical.get("pattern_memory", {}) if isinstance(canonical.get("pattern_memory"), dict) else {}
        transition = canonical.get("transition_risk", {}) if isinstance(canonical.get("transition_risk"), dict) else {}
        actionability = canonical.get("actionability", {}) if isinstance(canonical.get("actionability"), dict) else {}
        latest = canonical.get("latest_completed_candle_time") or (canonical.get("market") or {}).get("latest_completed_candle_time")
        st.caption(
            f"Run ID {canonical.get('run_id','-')} • EURUSD H1 • Latest completed candle {latest or '-'} "
            f"• Cache {canonical.get('cache_status') or (canonical.get('metadata') or {}).get('support_cache_status','-')}"
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Full Metric Direction", final.get("directional_market_view", canonical.get("full_metric_direction", "WAIT")), "Protected source of truth")
        m2.metric("Final Less-Risky Action", final.get("less_risky_decision", final.get("tradeability_decision", "WAIT")), actionability.get("current_label", "WATCH"))
        m3.metric("Transition / Pattern", transition.get("status", "WATCH"), pattern.get("pattern_confirmation", "NEUTRAL"))

        candidates = canonical.get("top_two_daily_candidates") or canonical.get("opportunity_candidates") or []
        if isinstance(candidates, list) and candidates:
            candidate_frame = pd.DataFrame(candidates).head(2)
            preferred = [column for column in (
                "Priority Rank", "Candidate Timestamp", "Direction", "Current Status", "Master Score",
                "Entry Score", "Hold Score", "TP Score", "Exit Risk", "Regime", "Alpha", "Delta",
                "Pattern Confirmation", "Transition Risk", "Actionability Label", "Expected Value",
                "Reliability", "Reason Accepted or Blocked", "Validity Horizon", "Final Candidate Decision",
            ) if column in candidate_frame.columns]
            st.dataframe(candidate_frame[preferred] if preferred else candidate_frame, use_container_width=True, hide_index=True, height=150)
        else:
            st.info("No safe candidate was available. The canonical action remains WAIT; Finder does not fabricate an entry.")

        priority = st.session_state.get("canonical_priority_table_20260617")
        if not isinstance(priority, pd.DataFrame) or priority.empty:
            rows = canonical.get("canonical_priority_table") or canonical.get("priority_table") or []
            priority = pd.DataFrame(rows) if isinstance(rows, list) else pd.DataFrame()
        if not priority.empty:
            view = priority.copy(deep=False)
            time_col = next((c for c in ("Candidate Timestamp", "Time", "Timestamp", "time") if c in view.columns), None)
            if time_col is not None:
                parsed = pd.to_datetime(view[time_col], errors="coerce")
                view = view.assign(_finder_time=parsed).dropna(subset=["_finder_time"]).sort_values("_finder_time", ascending=False)
                days = [str(x) for x in view["_finder_time"].dt.date.drop_duplicates().tolist()[:30]]
                if days:
                    c1, c2 = st.columns(2)
                    with c1:
                        day = st.selectbox("Finder Day", days, index=0, key="finder_align_day")
                    hours = sorted(view.loc[view["_finder_time"].dt.date.astype(str).eq(day), "_finder_time"].dt.hour.unique().tolist(), reverse=True)
                    with c2:
                        hour = st.selectbox("Finder Hour", hours or [0], index=0, format_func=lambda h: f"{int(h):02d}:00", key="finder_align_hour")
                    selected = view[view["_finder_time"].dt.date.astype(str).eq(day) & view["_finder_time"].dt.hour.eq(int(hour))].head(1)
                    if not selected.empty:
                        st.dataframe(selected.drop(columns=["_finder_time"], errors="ignore"), use_container_width=True, hide_index=True, height=120)

        decision_row = pd.DataFrame([{
            "Run ID": canonical.get("run_id"),
            "Latest Completed H1": latest,
            "Canonical Direction": final.get("directional_market_view", "WAIT"),
            "Final Decision": final.get("tradeability_decision", "WAIT"),
            "Pattern Confirmation": pattern.get("pattern_confirmation", "NEUTRAL"),
            "Transition Risk": transition.get("value"),
            "Transition Status": transition.get("status", "WATCH"),
            "Actionability": actionability.get("current_label", "WATCH"),
            "Expected Value": final.get("expected_value", actionability.get("expected_value")),
            "Reliability": (canonical.get("reliability") or {}).get("score"),
        }])
        st.markdown("#### Finder Decision Engine")
        st.dataframe(decision_row, use_container_width=True, hide_index=True)

        with st.expander("📊 Finder Replay — cached canonical prediction vs actual", expanded=False):
            replay = st.session_state.get("dv_pp_bt_hist")
            if isinstance(replay, pd.DataFrame) and not replay.empty:
                try:
                    from ui.table_ordering_20260618 import newest_first
                    replay = newest_first(replay, 48)
                except Exception:
                    replay = replay.tail(48).iloc[::-1]
                st.dataframe(replay, use_container_width=True, hide_index=True, height=300)
            else:
                st.info("No settled replay rows are cached for this run.")

    def _wrapped_finder(results: Any):
        if callable(prev):
            prev(results)
        try:
            _render_upgrade(results)
        except Exception as exc:
            st.caption(f"Finder alignment upgrade skipped safely: {exc}")

    ns["_render_doo_finder"] = _wrapped_finder
