"""Regime inner tab upgrade for Home/Lunch.

Display-only and run-gated. It consolidates regime-related interpretation into
one Home inner tab without altering any existing prediction/model output.
"""
from __future__ import annotations

import json
import math
import time
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd
import streamlit as st

UNIQUE = "20260614_regime_inner"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        if isinstance(v, str):
            v = v.replace("%", "").replace(",", "").strip()
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _clip(x: Any, lo: float = 0, hi: float = 100) -> float:
    return float(max(lo, min(hi, _num(x, lo))))


def _norm(s: Any) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _flatten(obj: Any, prefix: str = "", depth: int = 0) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if depth > 4:
        return out
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                out.update(_flatten(v, key, depth + 1))
            elif not isinstance(v, (pd.DataFrame, list, tuple)):
                out[key] = v
    return out


def _flat_state() -> Dict[str, Any]:
    keys = [
        "dv_pp_regime_summary", "dv_pp_bt_summary", "dv_pp_base_result",
        "lunch_5layer_powerbi_result", "final_synced_research_merge_pack_20260612",
        "final_merged_intelligence_pack_20260612", "research_context_20260614",
        "powerbi_projection_upgrade_20260614", "eurusd_h1_matrix_export",
        "nylo_unified_home_sync_20260612", "technical_logic_upgrade_lunch_v20260611",
        "technical_logic_upgrade_v20260611", "dv_research_alignment_pack_20260612",
    ]
    flat: Dict[str, Any] = {}
    for key in keys:
        obj = st.session_state.get(key, {})
        if isinstance(obj, dict):
            flat.update(_flatten(obj, key))
    for k, v in st.session_state.items():
        if not isinstance(v, (pd.DataFrame, dict, list, tuple)):
            flat[str(k)] = v
    return flat


def _find(flat: Dict[str, Any], aliases: Iterable[str], default: Any = None) -> Any:
    nmap = {_norm(k): v for k, v in flat.items()}
    for a in aliases:
        if _norm(a) in nmap:
            return nmap[_norm(a)]
    for k, v in nmap.items():
        for a in aliases:
            na = _norm(a)
            if na and na in k:
                return v
    return default


def _df() -> pd.DataFrame:
    for key in ["dv_pp_df", "last_df", "custom_h1_df", "home_df", "full_metric_history_df"]:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            d = obj.copy().tail(7000).reset_index(drop=True)
            break
    else:
        return pd.DataFrame()
    cols = {_norm(c): c for c in d.columns}
    for src, dst in {"datetime": "time", "timestamp": "time", "date": "time", "c": "close", "o": "open", "h": "high", "l": "low"}.items():
        if src in cols and dst not in d.columns:
            d = d.rename(columns={cols[src]: dst})
    if "time" not in d.columns:
        d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
    if "close" not in d.columns:
        return pd.DataFrame()
    for c in ["open", "high", "low", "close"]:
        if c not in d.columns:
            d[c] = d["close"]
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def _regime_series(d: pd.DataFrame, flat: Dict[str, Any]) -> pd.Series:
    if d.empty:
        return pd.Series(dtype=str)
    cols = {_norm(c): c for c in d.columns}
    for name in ["regime", "currentregime", "h1regime", "majorregime"]:
        if name in cols:
            return d[cols[name]].astype(str).fillna("RANGE_NORMAL")
    ret24 = d["close"].pct_change(24).fillna(0)
    vol = d["close"].pct_change().rolling(24, min_periods=4).std().fillna(0)
    med = float(vol.tail(500).median()) if len(vol) else 0.0005
    side = np.where(ret24 > 0.001, "BULL", np.where(ret24 < -0.001, "BEAR", "RANGE"))
    state = np.where(vol > med * 1.35, "HIGH_VOL", np.where(vol < med * .7, "COMPRESSION", "NORMAL"))
    return pd.Series([f"{a}_{b}" for a, b in zip(side, state)], index=d.index)


def _dir(regime: Any) -> str:
    s = str(regime or "").upper()
    if "BULL" in s:
        return "BUY"
    if "BEAR" in s:
        return "SELL"
    return "WAIT"


def _segments(d: pd.DataFrame, r: pd.Series) -> pd.DataFrame:
    if d.empty or r.empty:
        return pd.DataFrame(columns=["Regime", "Start", "End", "Duration Hours", "Outcome pips", "Rising Hours", "Falling Hours"])
    groups = (r != r.shift()).cumsum()
    rows: List[Dict[str, Any]] = []
    for _, idx in d.groupby(groups).groups.items():
        part = d.loc[list(idx)]
        if part.empty:
            continue
        diff = part["close"].diff().fillna(0)
        rows.append({
            "Regime": str(r.loc[part.index[0]]),
            "Start": part["time"].iloc[0],
            "End": part["time"].iloc[-1],
            "Duration Hours": int(len(part)),
            "Outcome pips": round((float(part["close"].iloc[-1]) - float(part["close"].iloc[0])) * 10000, 2),
            "Rising Hours": int((diff > 0).sum()),
            "Falling Hours": int((diff < 0).sum()),
        })
    return pd.DataFrame(rows).tail(80).reset_index(drop=True)


def _model_forecast_dir(flat: Dict[str, Any], d: pd.DataFrame) -> str:
    bull = _num(_find(flat, ["bull_probability", "bull_prob", "forecast_bull_probability"], 50), 50)
    if bull > 10:
        if bull >= 54:
            return "BUY"
        if bull <= 46:
            return "SELL"
    pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
    if isinstance(pred, pd.DataFrame) and not pred.empty and "close" in pred.columns and not d.empty:
        pc = _num(pd.to_numeric(pred["close"], errors="coerce").dropna().tail(1).iloc[0], _num(d["close"].iloc[-1]))
        return "BUY" if pc > _num(d["close"].iloc[-1]) else "SELL" if pc < _num(d["close"].iloc[-1]) else "WAIT"
    return "WAIT"


def build_regime_context(force: bool = False) -> Dict[str, Any]:
    if not force and isinstance(st.session_state.get("regime_context_20260614"), dict):
        return st.session_state["regime_context_20260614"]
    flat, d = _flat_state(), _df()
    r = _regime_series(d, flat)
    seg = _segments(d, r)
    # Prefer the same regime authority used by Data Visualization and Lunch unified sync.
    cur_regime = str(_find(flat, [
        "nylo_unified_home_sync_20260612.summary.current_powerbi_regime",
        "final_merged_intelligence_pack_20260612.master_regime",
        "final_synced_research_merge_pack_20260612.master_regime",
        "dv_pp_regime_summary.current_regime",
        "lunch_5layer_powerbi_result.current_regime",
        "current_regime", "h1_regime", "major_regime", "regime",
    ], r.iloc[-1] if not r.empty else "RANGE_NORMAL"))
    if cur_regime in ["", "None", "nan"] and not r.empty:
        cur_regime = str(r.iloc[-1])
    regime_source = "Data Visualization / Lunch Unified Sync" if _find(flat, ["dv_pp_regime_summary.current_regime", "nylo_unified_home_sync_20260612.summary.current_powerbi_regime"], None) is not None else "Derived from available H1 history"
    current_dir = _dir(cur_regime)
    forecast_dir = _model_forecast_dir(flat, d)
    conflict = forecast_dir in {"BUY", "SELL"} and current_dir in {"BUY", "SELL"} and forecast_dir != current_dir
    ret = d["close"].pct_change().fillna(0) if not d.empty else pd.Series(dtype=float)
    accel = float(ret.diff().tail(24).mean()) if len(ret) > 24 else 0.0
    vol24 = float(ret.tail(24).std()) if len(ret) else 0.0005
    vol120 = float(ret.tail(120).std()) if len(ret) else max(vol24, 0.0005)
    last_seg = seg.iloc[-1].to_dict() if not seg.empty else {}
    age = int(last_seg.get("Duration Hours", 0) or 0)
    expected = int(max(12, seg["Duration Hours"].tail(18).mean())) if not seg.empty else 36
    remaining = max(0, expected - age)
    transition_risk = _clip(100 - remaining / max(expected, 1) * 100 + max(0, vol24 / max(vol120, 1e-9) - 1) * 32)
    rise = _num(last_seg.get("Rising Hours"), 0)
    fall = _num(last_seg.get("Falling Hours"), 0)
    total = max(1, rise + fall)
    rising_eff = _clip(rise / total * 100)
    falling_eff = _clip(fall / total * 100)
    regime_conf = _num(_find(flat, ["regime_confidence", "hmm_confidence", "Regime Confidence %", "regime_stability_pct", "Regime Stability", "bull_probability"], 55), 55)
    if regime_conf <= 10:
        regime_conf *= 10
    accuracy = _num(_find(flat, ["dv_pp_bt_summary.direction_accuracy_pct", "direction_accuracy_pct", "direction_accuracy", "prediction_accuracy", "Random Forest Accuracy %"], 50), 50)
    stability = _clip(regime_conf * .45 + (100 - transition_risk) * .35 + max(rising_eff, falling_eff) * .2)
    efficiency = _clip(abs(rising_eff - falling_eff) + max(rising_eff, falling_eff) * .55)
    reliability = _clip(regime_conf * .35 + accuracy * .35 + stability * .30 - (20 if conflict else 0))
    priority = int(max(1, min(14, round(15 - reliability / 100 * 14 + transition_risk / 100 * 4))))
    forecast = "FOLLOW REGIME" if not conflict and current_dir != "WAIT" else "WAIT / CONFLICT" if conflict else "RANGE / WAIT"
    prediction = f"{forecast_dir} forecast vs {current_dir} regime"
    history = seg.copy()
    if not history.empty:
        history["Regime Direction"] = history["Regime"].map(_dir)
        history["Regime Accuracy Proxy %"] = np.where(
            ((history["Regime Direction"] == "BUY") & (history["Outcome pips"] > 0)) |
            ((history["Regime Direction"] == "SELL") & (history["Outcome pips"] < 0)), 100, 50,
        )
        history.insert(0, "Priority", range(1, len(history) + 1))
        history = history.sort_values(["End"], ascending=False).head(40).reset_index(drop=True)
    knn = history.copy().head(20) if isinstance(history, pd.DataFrame) else pd.DataFrame()
    if not knn.empty:
        knn["Similarity %"] = np.clip(100 - (knn["Duration Hours"] - age).abs() * 1.8, 0, 100).round(1)
        knn["KNN Regime Priority"] = range(1, len(knn) + 1)
        knn = knn.sort_values(["KNN Regime Priority"], ascending=True)
    metrics = {
        "Current Regime": cur_regime,
        "Regime Direction": current_dir,
        "Forecast Direction": forecast_dir,
        "Regime Conflict": "YES" if conflict else "NO",
        "Regime Confidence %": round(_clip(regime_conf), 1),
        "Regime Priority": priority,
        "Regime Age Hours": age,
        "Expected Duration Hours": expected,
        "Estimated Remaining Hours": remaining,
        "Transition Risk %": round(transition_risk, 1),
        "Regime Acceleration": round(accel * 10000, 4),
        "Regime Rising Efficiency %": round(rising_eff, 1),
        "Regime Falling Efficiency %": round(falling_eff, 1),
        "Regime Efficiency %": round(efficiency, 1),
        "Regime Accuracy Score": round(_clip(accuracy), 1),
        "Regime Reliable Score": round(reliability, 1),
        "Regime Stability Score": round(stability, 1),
        "Regime Forecast": forecast,
        "Regime Prediction": prediction,
        "Regime Sync Source": regime_source,
    }
    ctx = {"metrics": metrics, "history": history, "knn": knn, "built_at": str(pd.Timestamp.now()), "rows": int(len(d))}
    st.session_state["regime_context_20260614"] = ctx
    return ctx


def _metric_grid(data: Dict[str, Any], n: int = 4) -> None:
    items = list(data.items())
    for i in range(0, len(items), n):
        cols = st.columns(n)
        for col, (k, v) in zip(cols, items[i:i + n]):
            col.metric(str(k), v)


def render_regime_inner_tab() -> None:
    st.markdown("### 🧭 Regime Inner Tab — Priority #1")
    st.caption("All regime-related display is consolidated here: confidence, conflict, priority, efficiency, reliability, forecast, prediction, and history table. Display-only; predictions/models are not changed.")
    a, b, c = st.columns([1.2, .8, 1.8])
    if a.button("▶ Run Regime Sync", key=f"run_{UNIQUE}", use_container_width=True):
        st.session_state[f"ready_{UNIQUE}"] = True
        build_regime_context(True)
        try:
            from core.styles import request_close_sidebar
            request_close_sidebar()
        except Exception:
            pass
    if b.button("Clear", key=f"clear_{UNIQUE}", use_container_width=True):
        st.session_state[f"ready_{UNIQUE}"] = False
    c.caption("Run-gated for low RAM/CPU. Uses existing Home/Data Visualization/PowerBI/regime history only.")
    if not st.session_state.get(f"ready_{UNIQUE}"):
        st.info("Click Run Regime Sync to load the regime dashboard and history table.")
        return
    ctx = build_regime_context(False)
    m = ctx.get("metrics", {})
    order = [
        "Current Regime", "Regime Direction", "Forecast Direction", "Regime Conflict",
        "Regime Confidence %", "Regime Priority", "Regime Reliable Score", "Regime Accuracy Score",
        "Regime Age Hours", "Expected Duration Hours", "Estimated Remaining Hours", "Transition Risk %",
        "Regime Acceleration", "Regime Rising Efficiency %", "Regime Falling Efficiency %", "Regime Efficiency %",
        "Regime Stability Score", "Regime Forecast", "Regime Prediction", "Regime Sync Source",
    ]
    _metric_grid({k: m.get(k, "-") for k in order if k in m}, 4)
    t1, t2, t3 = st.tabs(["KNN/Greedy Regime Priority", "Regime History Data", "Copy"])
    with t1:
        knn = ctx.get("knn", pd.DataFrame())
        if isinstance(knn, pd.DataFrame) and not knn.empty:
            st.dataframe(knn, use_container_width=True, hide_index=True, height=320)
        else:
            st.info("Need more existing H1/regime history rows.")
    with t2:
        hist = ctx.get("history", pd.DataFrame())
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            st.dataframe(hist, use_container_width=True, hide_index=True, height=420)
        else:
            st.info("No regime history table available yet.")
    with t3:
        text = json.dumps({k: (v.to_dict("records") if isinstance(v, pd.DataFrame) else v) for k, v in ctx.items()}, indent=2, default=str, ensure_ascii=False)
        st.text_area("Regime sync JSON", text, height=240, key=f"copy_{UNIQUE}")
        st.download_button("Download Regime JSON", text, file_name="regime_sync_20260614.json", mime="application/json", key=f"dl_{UNIQUE}", use_container_width=True)


def install(ns: dict) -> None:
    import streamlit as st
    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    prev_data = ns.get("_render_lunch_data_visualization_inner_tab")
    prev_research = ns.get("_render_home_research_inner_20260612")
    prev_doo = ns.get("_render_doo_prime_inner_tab")
    footer = ns.get("render_tab_footer")
    build_copy = ns.get("_build_lunch_all_copy_text")
    try:
        from .ai_assistant_lite import render_ai_assistant_lite_tab
    except Exception:
        from tabs.ai_assistant_lite import render_ai_assistant_lite_tab

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from streamlit_copy_button import copy_button
            copy_button(text, label, key=key)
        except Exception:
            st.text_area(label, text, height=120, key=key + "_fallback")

    def _selector() -> str:
        choices = [("Lunch", "🍱"), ("Regime", "🧭"), ("Data Visualization", "📊"), ("AI Assistant Lite", "🤖"), ("Research", "🎓"), ("Doo Prime", "🏦")]
        current = st.session_state.get("home_inner_tab", "Lunch")
        if current not in [x[0] for x in choices]:
            current = "Lunch"
            st.session_state["home_inner_tab"] = current
        cols = st.columns(len(choices))
        for idx, (name, icon) in enumerate(choices):
            active = st.session_state.get("home_inner_tab") == name
            label = ("✅ " if active else "") + f"{icon} {name}"
            if cols[idx].button(label, use_container_width=True, key=f"home_inner_regime_{idx}_{UNIQUE}"):
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

    def _top_copy_once() -> None:
        try:
            text = build_copy() if callable(build_copy) else "Copy text is not ready yet."
        except Exception:
            text = "Copy text is not ready yet. Run Calculation first."
        if isinstance(st.session_state.get("regime_context_20260614"), dict):
            text += "\n\nREGIME CONTEXT 20260614\n" + json.dumps(st.session_state["regime_context_20260614"].get("metrics", {}), indent=2, default=str)
        _copy_button("📋 Copy Full Home H1 — includes Regime", str(text), f"copy_home_regime_full_{UNIQUE}")

    def _show() -> None:
        try:
            from core.streamlit_safe_dataframe import install_safe_dataframe_patch
            install_safe_dataframe_patch()
        except Exception:
            pass
        selected = _selector()
        _top_copy_once()
        if selected == "Lunch" and callable(prev_lunch):
            prev_lunch()
        elif selected == "Regime":
            render_regime_inner_tab()
        elif selected == "Data Visualization" and callable(prev_data):
            prev_data()
        elif selected == "AI Assistant Lite":
            render_ai_assistant_lite_tab()
        elif selected == "Research":
            if callable(prev_research):
                prev_research()
            else:
                try:
                    import tabs.research as research
                    research.show()
                except Exception as exc:
                    st.error("Research tab could not load.")
                    st.exception(exc)
        elif callable(prev_doo):
            prev_doo()
        if callable(footer) and selected != "AI Assistant Lite":
            try:
                footer("Lunch")
            except Exception:
                pass

    ns["render_regime_inner_tab_20260614"] = render_regime_inner_tab
    ns["build_regime_context_20260614"] = build_regime_context
    ns["show"] = _show
