"""2026-06-11 KNN Priority Placement upgrade.

Additive only: uses existing stored metrics/session outputs to rank rows for
visibility. It does not train, predict, alter ML outputs, or trigger heavy runs.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st


_PRIORITY_COL = "KNN Priority Score"
_LABEL_COL = "Priority Label"


def install(ns: Dict[str, Any]) -> None:
    def _num(x: Any, default: float = 0.0) -> float:
        try:
            if x is None:
                return default
            if isinstance(x, str):
                x = x.replace("%", "").replace("/10", "").strip()
            v = float(x)
            if np.isnan(v):
                return default
            return v
        except Exception:
            return default

    def _pick(row: Any, names: Iterable[str], default: float = 0.0) -> float:
        if not isinstance(row, (pd.Series, dict)):
            return default
        lower = {str(k).strip().lower(): k for k in row.keys()}
        for n in names:
            key = lower.get(str(n).strip().lower())
            if key is not None:
                return _num(row.get(key), default)
        return default

    def _text(row: Any, names: Iterable[str], default: str = "") -> str:
        if not isinstance(row, (pd.Series, dict)):
            return default
        lower = {str(k).strip().lower(): k for k in row.keys()}
        for n in names:
            key = lower.get(str(n).strip().lower())
            if key is not None:
                val = row.get(key)
                if val is not None and str(val).strip():
                    return str(val)
        return default

    def _clip(v: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, float(v)))

    def _scale10(v: float, default: float = 5.0) -> float:
        v = _num(v, default)
        if v > 10.0:
            v = v / 10.0
        return _clip(v, 0, 10)

    def _current_defaults() -> Dict[str, Any]:
        pack = st.session_state.get("technical_logic_upgrade_lunch_v20260611") or st.session_state.get("technical_logic_upgrade_v20260611") or {}
        summary = pack.get("summary", {}) if isinstance(pack, dict) else {}
        result = st.session_state.get("dv_pp_base_result", {}) or st.session_state.get("lunch_5layer_powerbi_result", {}) or {}
        bt = st.session_state.get("dv_pp_bt_summary", {}) or {}
        regime = st.session_state.get("dv_pp_regime_summary", {}) or {}
        return {"summary": summary if isinstance(summary, dict) else {}, "result": result if isinstance(result, dict) else {}, "bt": bt if isinstance(bt, dict) else {}, "regime": regime if isinstance(regime, dict) else {}}

    def _row_features(row: Any) -> Tuple[List[float], Dict[str, Any]]:
        d = _current_defaults(); s = d["summary"]; r = d["result"]; bt = d["bt"]; reg = d["regime"]
        master = _scale10(_pick(row, ["Master Score", "Master /10", "master_score"], _num(r.get("master_score", s.get("Master Score", 5)), 5)))
        entry = _scale10(_pick(row, ["Entry Score", "Entry /10", "entry_score", "Entry Strength"], _num(r.get("entry_score", s.get("Entry Score", master)), master)))
        hold = _scale10(_pick(row, ["Hold Safety", "Hold /10", "hold_score", "Hold Safety /10"], _num(r.get("hold_score", s.get("Hold Safety", master)), master)))
        exit_risk = _scale10(_pick(row, ["Exit Risk", "Exit Risk /10", "exit_risk"], _num(r.get("exit_risk", s.get("Exit Risk", max(0, 10-master))), max(0, 10-master))))
        tpq = _scale10(_pick(row, ["TP Quality", "TP /10", "tp_quality"], _num(r.get("tp_quality", s.get("TP Quality", master)), master)))
        mq = _clip(_pick(row, ["Market Quality", "Market Quality Score", "market_quality"], _num(s.get("Market Quality Score", 50), 50)), 0, 100)
        agree = _clip(_pick(row, ["Forecast Agreement", "Forecast Agreement Score"], _num(s.get("Forecast Agreement Score", 50), 50)), 0, 100)
        rel = _clip(_pick(row, ["Reliability", "Reliability Accuracy %", "direction_accuracy", "Direction Accuracy %"], _num(s.get("Reliability Accuracy %", bt.get("direction_accuracy_pct", 50)), 50)), 0, 100)
        conflict_txt = (_text(row, ["Conflict Status", "Conflict", "Regime vs Prediction Conflict"], str(s.get("Conflict Status", "OK"))) or "OK").upper()
        counter_txt = (_text(row, ["Counter Trend Label", "Counter Trend", "counter_trend_label"], str(s.get("Counter Trend Label", "ALIGNED / NEUTRAL"))) or "").upper()
        h1 = (_text(row, ["H1 Regime", "current_regime"], str(reg.get("current_regime", ""))) or "").upper()
        h4 = (_text(row, ["H4 Regime"], str(s.get("H4 Regime", ""))) or "").upper()
        d1 = (_text(row, ["D1 Regime"], str(s.get("D1 Regime", ""))) or "").upper()
        conflict_penalty = 1.0 if "CONFLICT" in conflict_txt or conflict_txt in ("TRUE", "1", "YES") else 0.0
        counter_penalty = 1.0 if "COUNTER" in counter_txt else 0.0
        regime_bad = sum(1 for x in (h1, h4, d1) if any(w in x for w in ("SHOCK", "EXHAUST", "LIMIT", "BEAR", "AVOID"))) / 3.0
        vec = [master/10, entry/10, hold/10, 1-exit_risk/10, tpq/10, mq/100, agree/100, rel/100, 1-conflict_penalty, 1-counter_penalty, 1-regime_bad]
        meta = {"master": master, "entry": entry, "hold": hold, "exit_risk": exit_risk, "tpq": tpq, "market_quality": mq, "agreement": agree, "reliability": rel, "conflict": conflict_penalty, "counter": counter_penalty, "regime_bad": regime_bad, "h1": h1, "h4": h4, "d1": d1}
        return vec, meta

    def _priority_from_row(row: Any) -> float:
        vec, meta = _row_features(row)
        # KNN-style similarity: distance to one ideal safe/important neighbour.
        ideal = np.ones(len(vec), dtype=float)
        weights = np.array([1.0, 1.0, 1.1, 1.35, 0.9, 1.25, 1.05, 1.25, 1.2, 1.0, 0.8], dtype=float)
        dist = float(np.sqrt(np.sum(((np.array(vec) - ideal) * weights) ** 2)) / np.sqrt(np.sum(weights ** 2)))
        score = (1.0 - _clip(dist, 0, 1)) * 100.0
        if meta["exit_risk"] >= 7:
            score -= 10
        if meta["conflict"]:
            score -= 12
        if meta["counter"]:
            score -= 7
        return round(_clip(score, 0, 100), 1)

    def _label(score: float) -> str:
        score = _num(score, 0)
        if score >= 82: return "A+"
        if score >= 70: return "A"
        if score >= 55: return "B"
        if score >= 40: return "C"
        return "Avoid"

    def _should_enrich(df: pd.DataFrame) -> bool:
        if not isinstance(df, pd.DataFrame) or df.empty or _PRIORITY_COL in df.columns:
            return False
        names = " ".join(str(c).lower() for c in df.columns)
        triggers = ["master", "entry", "hold", "exit", "tp", "market quality", "reliability", "conflict", "counter", "regime", "forecast", "decision", "score", "hour"]
        return any(t in names for t in triggers)

    def add_knn_priority_columns(df: Any) -> Any:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df
        if _PRIORITY_COL in df.columns and _LABEL_COL in df.columns:
            return df
        if not _should_enrich(df):
            return df
        out = df.copy()
        scores = [_priority_from_row(row) for _, row in out.iterrows()]
        out.insert(0, _LABEL_COL, [_label(x) for x in scores])
        out.insert(0, _PRIORITY_COL, scores)
        return out

    def _time_col(df: pd.DataFrame) -> str | None:
        lower = {str(c).lower(): c for c in df.columns}
        for c in ("time", "datetime", "date", "timestamp"):
            if c in lower:
                return lower[c]
        return None

    def _hour_value(row: pd.Series, df: pd.DataFrame) -> str:
        for c in ("Hour", "hour"):
            if c in df.columns:
                return str(row.get(c))
        tc = _time_col(df)
        if tc:
            try: return pd.to_datetime(row.get(tc)).strftime("%Y-%m-%d %H:00")
            except Exception: pass
        return "-"

    def _important_fact_board(df: Any, location: str = "Lunch") -> None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            st.info("Run Calculation first so KNN Priority can place important stored facts here.")
            return
        d = add_knn_priority_columns(df)
        if not isinstance(d, pd.DataFrame) or d.empty or _PRIORITY_COL not in d.columns:
            st.info("KNN Priority is ready. It will appear when metric/history rows are available.")
            return
        d = d.copy()
        for c in [_PRIORITY_COL, "Reliability", "Market Quality", "Exit Risk"]:
            if c in d.columns: d[c] = pd.to_numeric(d[c], errors="coerce")
        best = d.sort_values(_PRIORITY_COL, ascending=False).iloc[0]
        safest = d.sort_values("Exit Risk", ascending=True).iloc[0] if "Exit Risk" in d.columns else best
        reliable = d.sort_values("Reliability", ascending=False).iloc[0] if "Reliability" in d.columns else best
        market = d.sort_values("Market Quality", ascending=False).iloc[0] if "Market Quality" in d.columns else best
        low_conflict = d[~d.astype(str).agg(" ".join, axis=1).str.contains("CONFLICT", case=False, na=False)]
        low_conflict_row = low_conflict.sort_values(_PRIORITY_COL, ascending=False).iloc[0] if not low_conflict.empty else best
        text_all = d.astype(str).agg(" ".join, axis=1)
        conflict_now = "CONFLICT" if text_all.str.contains("CONFLICT", case=False, na=False).head(1).any() else "OK"
        counter_now = "COUNTER TREND" if text_all.str.contains("COUNTER", case=False, na=False).head(1).any() else "OK"
        regime_cols = [c for c in d.columns if "Regime" in str(c)]
        best_reg = worst_reg = "-"
        if regime_cols:
            g = d.groupby(d[regime_cols[0]].astype(str))[_PRIORITY_COL].mean().sort_values(ascending=False)
            if not g.empty:
                best_reg, worst_reg = str(g.index[0]), str(g.index[-1])
        st.markdown(f"### 🧠 KNN Important Fact Board — {location}")
        st.caption("Display-priority only. Uses existing stored metrics; no new ML prediction engine and no output replacement.")
        c = st.columns(3)
        c[0].metric("Best Hour", _hour_value(best, d), f"{best.get(_PRIORITY_COL, 0)} / 100")
        c[1].metric("Safest Hour", _hour_value(safest, d), f"Exit Risk {safest.get('Exit Risk', '-')}")
        c[2].metric("Highest Reliability Hour", _hour_value(reliable, d), f"{reliable.get('Reliability', '-')}%")
        c2 = st.columns(3)
        c2[0].metric("Highest Market Quality Hour", _hour_value(market, d), f"{market.get('Market Quality', '-')}%")
        c2[1].metric("Lowest Conflict Hour", _hour_value(low_conflict_row, d), str(low_conflict_row.get(_LABEL_COL, '-')))
        c2[2].metric("Best / Worst Regime", best_reg[:22], worst_reg[:22])
        if conflict_now != "OK": st.warning("Current Conflict Warning: regime and prediction are not aligned in the visible stored rows.")
        if counter_now != "OK": st.warning("Current Counter Trend Warning: counter-trend rows exist in the visible stored rows.")
        st.session_state[f"knn_priority_board_{location}"] = {"best_hour": _hour_value(best, d), "safest_hour": _hour_value(safest, d), "highest_reliability_hour": _hour_value(reliable, d), "highest_market_quality_hour": _hour_value(market, d), "lowest_conflict_hour": _hour_value(low_conflict_row, d), "current_conflict_warning": conflict_now, "current_counter_trend_warning": counter_now, "best_regime_condition": best_reg, "worst_regime_condition": worst_reg}

    def _placement_controls(df: Any, key: str) -> Any:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return df
        out = add_knn_priority_columns(df)
        if not isinstance(out, pd.DataFrame) or out.empty or _PRIORITY_COL not in out.columns:
            return out
        opts = ["Sort by KNN Priority", "Sort by Reliability", "Sort by Market Quality", "Sort by Exit Risk", "Show A+ Only", "Show Avoid Only", "Show Conflict Only", "Show Counter Trend Only"]
        choice = st.radio("KNN placement controls", opts, horizontal=True, key=key)
        if choice == "Sort by KNN Priority": out = out.sort_values(_PRIORITY_COL, ascending=False)
        elif choice == "Sort by Reliability" and "Reliability" in out.columns: out = out.sort_values("Reliability", ascending=False)
        elif choice == "Sort by Market Quality" and "Market Quality" in out.columns: out = out.sort_values("Market Quality", ascending=False)
        elif choice == "Sort by Exit Risk" and "Exit Risk" in out.columns: out = out.sort_values("Exit Risk", ascending=True)
        elif choice == "Show A+ Only": out = out[out[_LABEL_COL].astype(str).eq("A+")]
        elif choice == "Show Avoid Only": out = out[out[_LABEL_COL].astype(str).eq("Avoid")]
        elif choice == "Show Conflict Only": out = out[out.astype(str).agg(" ".join, axis=1).str.contains("CONFLICT", case=False, na=False)]
        elif choice == "Show Counter Trend Only": out = out[out.astype(str).agg(" ".join, axis=1).str.contains("COUNTER", case=False, na=False)]
        return out.reset_index(drop=True)

    # Make many existing tables receive KNN columns without replacing their original source data.
    if not st.session_state.get("knn_priority_dataframe_patch_installed_20260611", False):
        original_dataframe = st.dataframe
        def _dataframe_with_knn(data=None, *args, **kwargs):
            try:
                data = add_knn_priority_columns(data)
            except Exception:
                pass
            return original_dataframe(data, *args, **kwargs)
        st.dataframe = _dataframe_with_knn
        st.session_state["knn_priority_dataframe_patch_installed_20260611"] = True

    def _best_existing_table(location: str) -> pd.DataFrame:
        keys = [f"regime_history_table_{location}", "home_reversal_25d_scan", "ny_london_overlap_table", "ny_london_overlap_history", "dv_pp_backtest_table", "powerbi_backtest_table", "finder_alignment_table", "finder_result_table"]
        for k in keys:
            v = st.session_state.get(k)
            if isinstance(v, pd.DataFrame) and not v.empty:
                return v
        return pd.DataFrame()

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    def _render_lunch_knn():
        try:
            seed = _best_existing_table("Lunch")
            _important_fact_board(seed, "Lunch")
        except Exception as exc:
            st.warning(f"KNN Important Fact Board skipped safely: {exc}")
        if callable(prev_lunch):
            prev_lunch()
        try:
            view = _best_existing_table("Lunch")
            if isinstance(view, pd.DataFrame) and not view.empty:
                st.markdown("### 🧠 KNN Priority Cards — Lunch Tables")
                _important_fact_board(view, "Lunch Tables")
                with st.expander("Open / Close — KNN Priority Placement View", expanded=False):
                    st.dataframe(_placement_controls(view, "knn_lunch_controls_20260611"), use_container_width=True, hide_index=True, height=360)
        except Exception as exc:
            st.warning(f"KNN Lunch placement skipped safely: {exc}")
    ns["_render_metric_home_combined_inner_tab"] = _render_lunch_knn

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")
    def _render_dv_knn():
        try:
            seed = _best_existing_table("Data Visualization")
            _important_fact_board(seed, "Data Visualization")
        except Exception as exc:
            st.warning(f"KNN Data Visualization board skipped safely: {exc}")
        if callable(prev_dv):
            prev_dv()
        try:
            view = _best_existing_table("Data Visualization")
            if isinstance(view, pd.DataFrame) and not view.empty:
                st.markdown("### 🧠 KNN Priority Cards — Power BI / Backtest Tables")
                _important_fact_board(view, "Power BI Backtest")
                with st.expander("Open / Close — KNN Power BI Backtest Priority View", expanded=False):
                    st.dataframe(_placement_controls(view, "knn_dv_controls_20260611"), use_container_width=True, hide_index=True, height=360)
        except Exception as exc:
            st.warning(f"KNN Data Visualization placement skipped safely: {exc}")
    ns["_render_lunch_data_visualization_inner_tab"] = _render_dv_knn

    prev_copy = ns.get("_build_lunch_all_copy_text")
    def _build_copy_with_knn():
        base = prev_copy() if callable(prev_copy) else ""
        payload = {k: v for k, v in st.session_state.items() if str(k).startswith("knn_priority_board_")}
        return str(base) + "\n\nKNN PRIORITY PLACEMENT 2026-06-11\n" + "="*64 + "\n" + json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    ns["_build_lunch_all_copy_text"] = _build_copy_with_knn

    ns["add_knn_priority_columns"] = add_knn_priority_columns
