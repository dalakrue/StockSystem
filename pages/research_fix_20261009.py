"""Research fix 2026-10-09 — exit registry, validation states and exports.

New Streamlit page (additive; no existing page or render module is modified).
Shows the 240-row exit registry, validation states, active config, costs,
execution assumptions, disabled/rejected reasons and unknown outcomes, with
downloads that match the displayed settings.

Entry logic is untouched: this page only reads the frozen equations and the
prebuilt registry JSON (data/exit_registry_240.json).
"""
from pathlib import Path

import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]

try:
    import streamlit as st
    _HAS_ST = True
except ImportError:  # pragma: no cover — page runs in the Streamlit app env
    _HAS_ST = False

if _HAS_ST:  # pragma: no cover
    st.set_page_config(page_title="Research Fix 2026-10-09 — Exit Registry", layout="wide")
    st.title("Exit Registry — research fix 2026-10-09")
    st.caption("Read-only with respect to entry logic. All exits are research-only; "
               "Strict_Valid = NO for all 240 equations. Nothing here is live-validated.")

    from core import exit_registry_20261009 as reg
    from core import validation_states_20261009 as vs
    from core import cost_model_20261009 as cm
    from core import exports_20261009 as ex

    reg_path = APP_ROOT / "data" / "exit_registry_240.json"
    if not reg_path.exists():
        st.error("data/exit_registry_240.json not found — build it with the registry builder first.")
        st.stop()
    registry = reg.load_registry(reg_path)

    cfg_path = APP_ROOT / "config" / "research_fix_20261009.json"
    import json as _json
    criteria = _json.loads(cfg_path.read_text()) if cfg_path.exists() else {}

    st.header("1. 240-row exit registry")
    frame_rows = []
    for e in registry["entries"]:
        d = e["exit_modes"]["D_active_compatible"]
        c = e["exit_modes"]["C_compatible_research"]
        frame_rows.append({
            "S": e["s_column"], "Equation": e["equation_id"], "Symbol": e["symbol"],
            "Month": e["month"], "Dir": e["direction"], "Status": e["status"],
            "Validation": e["validation_state"],
            "C TP": c.get("tp_pips"), "C SL": c.get("sl_pips"),
            "C Trades": c.get("compatible_training_trades"),
            "D Active": d["available"], "D Rejection": d.get("rejection_reason"),
        })
    df = pd.DataFrame(frame_rows)
    col1, col2, col3 = st.columns(3)
    status_f = col1.multiselect("Status", sorted(df["Status"].unique()), default=sorted(df["Status"].unique()))
    val_f = col2.multiselect("Validation state", sorted(df["Validation"].unique()), default=sorted(df["Validation"].unique()))
    dact_f = col3.multiselect("Mode D", ["active", "rejected"], default=["active", "rejected"])
    show = df[df["Status"].isin(status_f) & df["Validation"].isin(val_f)]
    show = show[show["D Active"].map({True: "active", False: "rejected"}).isin(dact_f)]
    st.dataframe(show, use_container_width=True, height=420)
    st.caption(f"Showing {len(show)} / {len(df)} rows. Mode D = compatible exits passing ALL active risk checks.")

    rej = reg.rejected_summary(registry)
    st.subheader("Mode-D risk-gate rejections")
    st.write(f"Total rejected: {rej['total_rejected']} — by reason: {rej['by_reason']}")
    if rej["rows"]:
        st.dataframe(pd.DataFrame(rej["rows"]), use_container_width=True)

    st.header("2. Validation states")
    st.write("States: " + ", ".join(vs.STATES))
    manifest = vs.build_validation_manifest(
        strategy_version=registry["engine_identity"],
        exit_params_version=registry["exit_params_version"],
        test_period="2025-10-01 → 2026-10-05 (REUSED — not fresh)",
        sample_trades=0,
        requested_by="research-fix page")
    st.json(manifest)
    st.caption("Live promotion requires a recorded manifest. Status: pending — no fresh data.")

    st.header("3. Active config, costs, execution")
    st.subheader("Criteria (config/research_fix_20261009.json)")
    st.json(criteria.get("criteria", {}))
    st.subheader("Cost model")
    st.json(cm.describe())
    st.subheader("Execution assumptions")
    st.write({
        "intrabar_priority": "SL_FIRST (default); TP_FIRST is an explicitly-labelled legacy comparison mode",
        "evaluation_order": "open-price checks → Friday close → hold cap → bias-flip/danger → intrabar barriers",
        "adverse_gaps": "fill at the observed open, never a fabricated stop quote",
        "censorship": "research_release_unknown — censored intervals keep UNKNOWN P/L, never zero profit",
        "price_basis_labels": "INDICATIVE (completed candle) / RESEARCH FILL (next H1 open) / "
                              "EXECUTABLE (broker bid/ask) — never label indicative as executable",
        "month_selection": "equation month = Myanmar (Asia/Rangoon) month of the check",
        "k_tp_lookup": "mode B/E k_tp uses UTC month of the check (legacy semantics, documented)",
    })
    st.subheader("Frequency experiments (config only — research, never auto-promoted)")
    st.json(criteria.get("frequency_experiments", {}))
    st.caption("App/live defaults are UNCHANGED (K_ENTRIES_PER_CHECK = 4, UTC 06/07/10/11/12/13).")

    st.header("4. Disabled equations")
    dis = [e for e in registry["entries"] if e["status"] == "DISABLED"]
    st.write(f"{len(dis)} equations DISABLED — all by the worst-6 symbol exclusion "
             f"({reg.WORST6_PROVENANCE}). Training losers are NOT hardcoded as live removals.")
    st.dataframe(pd.DataFrame([{"S": e["s_column"], "Equation": e["equation_id"],
                                "Symbol": e["symbol"], "Month": e["month"],
                                "Reason": e["status_reason"]} for e in dis]),
                 use_container_width=True, height=280)

    st.header("5. Exports (match displayed settings)")
    name, data, mime = ex.registry_csv(registry)
    st.download_button("240-row registry CSV", data, file_name=name, mime=mime)
    name, data, mime = ex.active_config_json(criteria)
    st.download_button("Active config JSON", data, file_name=name, mime=mime)
    name, data, mime = ex.validation_manifest_json(manifest)
    st.download_button("Validation manifest", data, file_name=name, mime=mime)
    name, text, mime = ex.exit_reason_glossary()
    st.download_button("Exit-reason glossary", text.encode(), file_name=name, mime=mime)
    name, text, mime = ex.performance_definitions()
    st.download_button("Performance definitions", text.encode(), file_name=name, mime=mime)
