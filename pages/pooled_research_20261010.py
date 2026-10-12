"""Pooled-exits research 2026-10-10 — named scenario page.

New Streamlit page (additive; no existing page or render module is modified).
Shows the named selectable scenarios (baseline vs pooled_exits_research), the
Table-1 pooled exits, entry gate, strategy status rows (all 240 + 27 disabled
rebuilt combinations), readiness flags and download builders.

Entry logic is untouched: this page only reads the frozen equation registry
and the pooled scenario bundle (data/pooled_scenario_20261010.json).
"""
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:  # pragma: no cover — page runs in the Streamlit app env
    _HAS_ST = False

PAGE_VERSION = "pooled-research-page-20261010-v1"

if _HAS_ST:  # pragma: no cover
    st.set_page_config(page_title="Pooled Exits Research 2026-10-10", layout="wide")
    st.title("Pooled exits — named research scenario (2026-10-10)")
    st.caption("Research only. live_enabled = False. live_approved stays FALSE "
               "everywhere. Entry equations unchanged.")

    from core import exit_engine_20261010 as eng

    cfg_path = APP_ROOT / "config" / "research_improve_20261010.json"
    scen_path = APP_ROOT / "data" / "pooled_scenario_20261010.json"
    if not scen_path.exists():
        st.error("data/pooled_scenario_20261010.json not found.")
        st.stop()
    import json
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    bundle = json.loads(scen_path.read_text())

    st.header("Scenarios")
    st.write("**baseline_current_exits** — original stored exits from the signal "
             "frame (mode A), 48h cap, legacy admission gate. The 'before' leg.")
    st.write("**pooled_exits_research** — pooled TP/SL from the command Table 1, "
             "entry gate (TP−3)/(SL+3) ≥ 0.5, all other pairs rejected. The named "
             "experiment (live_enabled=false).")
    st.code(f"engine: {eng.ENGINE_VERSION_EXIT}\nconfig hash: {eng.config_hash()[:16]}…",
            language="text")

    st.header("Pooled exits (Table 1)")
    rows = []
    for sym, c in bundle["pooled_config"].items():
        if c["basis"] == "FIXED_PIPS":
            rows.append({"pair": sym, "TP": f"{c['tp_pips']:.0f} pips",
                         "SL": f"{c['sl_pips']:.0f} pips", "basis": c["basis"]})
        else:
            rows.append({"pair": sym,
                         "TP": f"3 × ATR14, clip {c['tp_clip_pips'][0]:.0f}–{c['tp_clip_pips'][1]:.0f}",
                         "SL": f"2 × ATR14, clip {c['sl_clip_pips'][0]:.0f}–{c['sl_clip_pips'][1]:.0f}",
                         "basis": c["basis"]})
    st.table(pd.DataFrame(rows))
    st.caption("GBPJPY uses the pre-entry available ATR (completed bar, availability "
               "≤ check). Missing/nonpositive ATR rejects the entry with a reason code. "
               "No silent fallbacks.")

    st.header("Strategy status (all 240 + 27 disabled rebuilt)")
    mapping = pd.DataFrame(bundle["s_mapping"])
    st.write(f"DEVELOPMENT_CANDIDATE: {(mapping['status'] == 'DEVELOPMENT_CANDIDATE').sum()} | "
             f"REJECTED: {(mapping['status'] == 'REJECTED').sum()} | "
             f"rebuilt disabled: {len(bundle['rebuilt_family_disabled'])}")
    st.dataframe(mapping, use_container_width=True)
    st.caption("A symbol-level pooled screen is not a statistical approval of its 12 "
               "monthly strategies. The pooled configuration passes ONLY "
               "development_screen_passed: its CI includes losses and its 5-pip cost "
               "result is negative. live_approved = FALSE for every row.")

    st.header("Readiness flags")
    st.write(", ".join(bundle["readiness_flags"]))

    st.download_button("Download scenario bundle (JSON)",
                       data=scen_path.read_bytes(),
                       file_name="pooled_scenario_20261010.json",
                       mime="application/json")
