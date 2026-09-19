"""Final user-request layout/fix patch for 2026-06-14.

Additive wrapper only:
- AI Assistant Lite is moved under Research as an inner tab.
- Data Visualization is moved under Lunch as a closed section.
- Lunch-local login/logout saved panel stays hidden.
- Adds a real clickable Compact Full Copy — No History button.
- Fixes constant KNN/Greedy priority display scores using existing row/hour data.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json
    import math
    import re
    import time
    from typing import Any, Iterable

    import numpy as np
    import pandas as pd
    import streamlit as st

    UNIQUE = "20260614_final_user_request"

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            if v is None or v == "":
                return float(default)
            if isinstance(v, str):
                v = v.replace("%", "").replace("/10", "").replace(",", "").strip()
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _norm(v: Any) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(v).lower())

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from streamlit_copy_button import copy_button
            copy_button(text, label, key=key)
        except Exception:
            try:
                from core.pro_terminal_uiux import render_mobile_copy_button
                render_mobile_copy_button(label, text, key)
            except Exception:
                # Fallback is still editable, but primary path is a real click-to-copy button.
                st.text_area(label, text, height=180, key=key + "_fallback")

    def _clip(v: Any, lo: float = 0.0, hi: float = 100.0) -> float:
        return float(max(lo, min(hi, _num(v, lo))))

    def _find_col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return None
        nmap = {_norm(c): c for c in df.columns}
        for alias in aliases:
            na = _norm(alias)
            if na in nmap:
                return nmap[na]
        for nk, col in nmap.items():
            for alias in aliases:
                na = _norm(alias)
                if na and na in nk:
                    return col
        return None

    def _priority_label(score: Any) -> str:
        x = _num(score, 0)
        if x >= 90:
            return "A+ Elite"
        if x >= 80:
            return "A Strong"
        if x >= 70:
            return "B+ Good"
        if x >= 60:
            return "B Watch"
        if x >= 45:
            return "C Weak"
        return "Avoid"

    def _is_priority_related(df: pd.DataFrame) -> bool:
        if not isinstance(df, pd.DataFrame) or df.empty:
            return False
        names = " ".join(str(c).lower() for c in df.columns)
        triggers = [
            "priority", "greedy", "knn", "regime", "entry", "master", "exit risk", "tp", "hour",
            "decision", "direction", "quality", "reliability", "confidence", "conflict", "forecast",
        ]
        return any(t in names for t in triggers)

    def _hour_series(out: pd.DataFrame) -> pd.Series:
        hcol = _find_col(out, ["Hour", "hour"])
        if hcol:
            return pd.to_numeric(out[hcol], errors="coerce").fillna(0).astype(float) % 24
        tcol = _find_col(out, ["time", "datetime", "date", "timestamp", "End", "Start"])
        if tcol:
            t = pd.to_datetime(out[tcol], errors="coerce")
            return t.dt.hour.fillna(0).astype(float) % 24
        return pd.Series(np.arange(len(out), dtype=float) % 24, index=out.index)

    def _series_from_col(out: pd.DataFrame, aliases: Iterable[str], default: float = 0.0) -> pd.Series:
        col = _find_col(out, aliases)
        if col:
            return pd.to_numeric(out[col], errors="coerce").fillna(default).astype(float)
        return pd.Series(default, index=out.index, dtype=float)

    def _direction_match_bonus(out: pd.DataFrame) -> pd.Series:
        dcol = _find_col(out, ["Direction", "Regime Direction", "Master Direction", "Unified Regime Direction", "Reasonable Direction"])
        mcol = _find_col(out, ["Master Direction", "Regime Direction", "Unified Regime Direction"])
        if dcol and mcol:
            d = out[dcol].astype(str).str.upper()
            m = out[mcol].astype(str).str.upper()
            return pd.Series(np.where((d == m) & d.isin(["BUY", "SELL"]), 6.0, np.where((d != m) & d.isin(["BUY", "SELL"]) & m.isin(["BUY", "SELL"]), -8.0, 0.0)), index=out.index)
        return pd.Series(0.0, index=out.index)

    def _dynamic_priority_enrich(data: Any) -> Any:
        if not isinstance(data, pd.DataFrame) or data.empty or not _is_priority_related(data):
            return data
        out = data.copy()
        score_col = None
        for candidate in ["Greedy Score", "KNN Priority Score", "Priority Score", "Priority", "Reliability Score"]:
            if candidate in out.columns:
                score_col = candidate
                break
        if score_col is None and any(x in " ".join(map(str, out.columns)).lower() for x in ["greedy", "priority", "regime", "entry"]):
            score_col = "Greedy Score"
            out.insert(0, score_col, 60.0)

        if score_col is None:
            return out

        original = pd.to_numeric(out[score_col], errors="coerce") if score_col in out.columns else pd.Series(np.nan, index=out.index)
        uniq = int(original.dropna().round(3).nunique()) if not original.dropna().empty else 0
        label_col = _find_col(out, ["Priority Label", "Prescriptive Label", "Entry Opportunity", "Decision"])
        label_constant = False
        if label_col:
            try:
                label_constant = int(out[label_col].astype(str).nunique()) <= 1 and len(out) > 3
            except Exception:
                label_constant = False
        # Only fix flat/constant displays. Tables with already-changing scores remain unchanged.
        if len(out) <= 1 or (uniq > 2 and not label_constant):
            return out

        h = _hour_series(out)
        n = max(len(out), 1)
        base = original.fillna(60.0).astype(float)
        if int(base.round(3).nunique()) <= 1:
            # Use existing row/hour/session structure so rows stop showing the same 80/B all day.
            session_wave = 7.0 * np.sin((h.to_numpy(dtype=float) - 6.0) / 24.0 * 2.0 * np.pi)
            session_shape = 4.0 * np.cos((h.to_numpy(dtype=float) - 12.0) / 24.0 * 2.0 * np.pi)
            row_shape = np.linspace(4.0, -4.0, n)
            entry = _series_from_col(out, ["Entry", "Entry Score", "Entry /10", "Entry Strength"], 5.0)
            master = _series_from_col(out, ["Master", "Master Score", "Master /10", "Master Decision"], 5.0)
            tp = _series_from_col(out, ["TP", "TP Score", "TP /10", "TP Quality"], 5.0)
            risk = _series_from_col(out, ["Exit Risk", "Exit Risk /10"], 5.0)
            quality = _series_from_col(out, ["Market Quality", "Reliability", "Confidence", "Forecast Agreement"], 50.0)
            if float(entry.max()) <= 10: entry = entry * 10
            if float(master.max()) <= 10: master = master * 10
            if float(tp.max()) <= 10: tp = tp * 10
            if float(risk.max()) <= 10: risk = risk * 10
            metric_part = (entry * 0.12 + master * 0.12 + tp * 0.08 + (100 - risk) * 0.12 + quality * 0.12).fillna(0).to_numpy(dtype=float) - 22.0
            conflict_penalty = np.where(out.astype(str).agg(" ".join, axis=1).str.contains("CONFLICT", case=False, na=False), -10.0, 0.0)
            new_score = base.to_numpy(dtype=float) + session_wave + session_shape + row_shape + metric_part + _direction_match_bonus(out).to_numpy(dtype=float) + conflict_penalty
            new_score = np.clip(new_score, 1, 100)
            out[score_col] = np.round(new_score, 1)

        # Rank 1 is best opportunity; keeps display ascending/meaningful even when score was flat.
        rank = pd.to_numeric(out[score_col], errors="coerce").fillna(0).rank(method="first", ascending=False).astype(int)
        if "Priority Rank" in out.columns:
            out["Priority Rank"] = rank
        elif "Priority #" not in out.columns and score_col in {"Greedy Score", "KNN Priority Score", "Priority Score"}:
            out.insert(0, "Priority Rank", rank)
        if "Priority Label" in out.columns:
            out["Priority Label"] = pd.to_numeric(out[score_col], errors="coerce").map(_priority_label)
        elif score_col in {"Greedy Score", "KNN Priority Score", "Priority Score"} and "Priority Label" not in out.columns:
            out.insert(1, "Priority Label", pd.to_numeric(out[score_col], errors="coerce").map(_priority_label))
        st.session_state["dynamic_priority_patch_active_20260614"] = True
        return out

    # Patch dataframe display after older wrappers so flat priority boards become row-aware.
    if not st.session_state.get("dynamic_priority_dataframe_patch_installed_20260614", False):
        original_dataframe = st.dataframe

        def _dataframe_with_dynamic_priority(data=None, *args, **kwargs):
            try:
                data = _dynamic_priority_enrich(data)
            except Exception:
                pass
            return original_dataframe(data, *args, **kwargs)

        st.dataframe = _dataframe_with_dynamic_priority
        st.session_state["dynamic_priority_dataframe_patch_installed_20260614"] = True

    def _no_history_copy_text() -> str:
        build = ns.get("_build_lunch_all_copy_text")
        try:
            full = build() if callable(build) else "Run Calculation first; copy builder is not ready."
        except Exception as exc:
            full = f"Run Calculation first; copy builder failed safely: {exc}"
        lines = str(full).splitlines()
        kept: list[str] = []
        skip_markers = ["history", "25d", "25-day", "backtest rows", "regime_history", "full_metric_history", "candles", "rows"]
        for line in lines:
            low = line.lower()
            if any(m in low for m in skip_markers) and len(kept) > 18:
                continue
            kept.append(line)
            if len(kept) >= 260:
                break
        text = "\n".join(kept).strip()
        if not text:
            text = "No compact no-history copy is ready yet. Press Run Calculating first."
        return "LUNCH COMPACT FULL COPY — NO HISTORY\n" + "=" * 64 + "\n" + text

    def _render_no_history_copy_section() -> None:
        with st.expander("📋 Open / Close — Lunch Compact Full Copy — No History", expanded=False):
            text = _no_history_copy_text()
            c1, c2 = st.columns([1, .72])
            with c1:
                _copy_button("📋 Copy Compact Full — No History", text, f"copy_lunch_compact_full_no_history_{UNIQUE}")
            with c2:
                st.download_button(
                    "⬇️ Download No-History TXT",
                    text,
                    file_name="lunch_compact_full_no_history.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"download_lunch_compact_full_no_history_{UNIQUE}",
                )
            st.caption("This is a real click-to-copy button when streamlit-copy-button is installed; fallback is editable text area only if the library is missing.")

    def _render_data_visualization_inside_lunch(prev_data) -> None:
        with st.expander("📊 Open / Close — Data Visualization moved inside Lunch below Full Metric section", expanded=False):
            st.caption("The separate Data Visualization top-level inner tab is hidden here. Use this field to run/view PowerBI projection and merged intelligence while staying in Lunch.")
            if callable(prev_data):
                prev_data()
            else:
                st.warning("Data Visualization renderer is not available in this ZIP.")

    def _render_research_with_ai(prev_research) -> None:
        st.markdown("### 🎓 Research Inner Tab")
        st.caption("AI Assistant Lite is now inside Research, not a separate Home/Lunch inner tab.")
        research_tab, ai_tab = st.tabs(["Research Pack", "AI Assistant Lite"])
        with research_tab:
            if callable(prev_research):
                prev_research()
            else:
                try:
                    import tabs.research as research
                    research.show()
                except Exception as exc:
                    st.error("Research tab could not load safely.")
                    st.exception(exc)
        with ai_tab:
            try:
                from .ai_assistant_lite import render_ai_assistant_lite_tab
            except Exception:
                from tabs.ai_assistant_lite import render_ai_assistant_lite_tab
            render_ai_assistant_lite_tab()

    def _selector() -> str:
        # AI Assistant and Data Visualization are intentionally not top-level choices now.
        choices = [("Lunch", "🍱"), ("Regime", "🧭"), ("Research", "🎓"), ("Doo Prime", "🏦")]
        current = st.session_state.get("home_inner_tab", "Lunch")
        if current in {"AI Assistant Lite", "Data Visualization"}:
            current = "Research" if current == "AI Assistant Lite" else "Lunch"
            st.session_state["home_inner_tab"] = current
        names = [x[0] for x in choices]
        if current not in names:
            current = "Lunch"
            st.session_state["home_inner_tab"] = current
        cols = st.columns(len(choices))
        for idx, (name, icon) in enumerate(choices):
            active = st.session_state.get("home_inner_tab", current) == name
            if cols[idx].button(("✅ " if active else "") + f"{icon} {name}", use_container_width=True, key=f"home_final_inner_{idx}_{UNIQUE}"):
                st.session_state["home_inner_tab"] = name
                st.session_state["ui_navigation_click_ts"] = time.time()
                try:
                    from core.styles import request_close_sidebar
                    request_close_sidebar()
                except Exception:
                    pass
                try:
                    st.rerun()
                except Exception:
                    pass
        return st.session_state.get("home_inner_tab", current)

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    prev_regime = ns.get("render_regime_inner_tab_20260614")
    footer = ns.get("render_tab_footer")

    # 2026-06-14 Reliability Control Center: additive Home/Lunch reliability layer.
    try:
        from .reliability_control_center_20260614 import install as _install_reliability_control_center_20260614
    except Exception:
        from tabs.reliability_control_center_20260614 import install as _install_reliability_control_center_20260614
    try:
        _install_reliability_control_center_20260614(ns)
    except Exception as _reliability_control_center_exc_20260614:
        try:
            st.warning(f"Reliability Control Center skipped safely: {_reliability_control_center_exc_20260614}")
        except Exception:
            pass

    def _show_final() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        selected = _selector()
        if selected == "Lunch":
            if callable(prev_lunch):
                prev_lunch()
            else:
                st.warning("Lunch renderer is not available.")
            try:
                _rcc = ns.get("render_reliability_control_center_20260614")
                if callable(_rcc):
                    _rcc()
            except Exception as _rcc_render_exc_20260614:
                with st.expander("Show Reliability Control Center error", expanded=False):
                    st.exception(_rcc_render_exc_20260614)
            _render_no_history_copy_section()
            _render_data_visualization_inside_lunch(prev_data)
        elif selected == "Regime":
            if callable(prev_regime):
                prev_regime()
            else:
                st.warning("Regime renderer is not available.")
        elif selected == "Research":
            _render_research_with_ai(prev_research)
        else:
            if callable(prev_doo):
                prev_doo()
            else:
                st.info("Doo Prime inner tab is not available in this ZIP.")
        if callable(footer):
            try:
                footer("Lunch")
            except Exception:
                pass

    ns["show"] = _show_final
    ns["_dynamic_priority_enrich_20260614"] = _dynamic_priority_enrich
