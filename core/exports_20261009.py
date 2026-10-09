"""Export functions for the 2026-10-09 research-fix page.

Every export is generated from the DISPLAYED settings/registry — downloads
match what the page shows. No hardcoded totals; everything recomputes from
data.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

APP_ROOT = Path(__file__).resolve().parents[1]


def _registry_frame(registry: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for e in registry["entries"]:
        d = e["exit_modes"]["D_active_compatible"]
        c = e["exit_modes"]["C_compatible_research"]
        a = e["exit_modes"]["A_original"]
        ev = e["exit_modes"]["E_dynamic_verified"]
        rows.append({
            "S Column": e["s_column"], "Equation ID": e["equation_id"],
            "Symbol": e["symbol"], "Month": e["month"],
            "Month TZ": e["month_timezone"], "Direction": e["direction"],
            "Status": e["status"], "Status Reason": e["status_reason"],
            "Validation State": e["validation_state"], "Strict Valid": e["strict_valid"],
            "Mode A TP": a["tp"], "Mode A SL": a["sl"], "Mode A Basis": a["basis"],
            "Mode A Hold h": a["hold_hours"],
            "Mode C TP pips": c.get("tp_pips"), "Mode C SL pips": c.get("sl_pips"),
            "Mode C Training Trades": c.get("compatible_training_trades"),
            "Mode C Training Net": c.get("compatible_training_net"),
            "Mode D Active": d["available"], "Mode D TP": d.get("tp_pips"),
            "Mode D SL": d.get("sl_pips"), "Mode D Rejection": d.get("rejection_reason"),
            "Mode E Available": ev["available"],
            "Research/Live": e["research_live_status"],
            "Param Version": e["parameter_version"],
        })
    return pd.DataFrame(rows)


def registry_csv(registry: Dict[str, Any]) -> tuple[str, bytes, str]:
    return ("exit_registry_240.csv",
            _registry_frame(registry).to_csv(index=False).encode(),
            "text/csv")


def active_config_json(config: Dict[str, Any]) -> tuple[str, bytes, str]:
    return ("active_config_research_fix_20261009.json",
            json.dumps(config, indent=1, default=str).encode(),
            "application/json")


def validation_manifest_json(manifest: Dict[str, Any]) -> tuple[str, bytes, str]:
    return ("validation_manifest_20261009.json",
            json.dumps(manifest, indent=1, default=str).encode(),
            "application/json")


def trade_ledger_csv(trades: pd.DataFrame) -> tuple[str, bytes, str]:
    return ("trade_log_compat_exits.csv", trades.to_csv(index=False).encode(), "text/csv")


def exit_reason_glossary() -> tuple[str, str, str]:
    text = (
        "EXIT REASON GLOSSARY (2026-10-09 research fix)\n"
        "==============================================\n"
        "TP            — take-profit barrier touched intrabar (or gapped through at the open).\n"
        "SL            — stop-loss barrier touched intrabar, or gapped through at the open\n"
        "                (adverse gaps fill at the OBSERVED open, never a fabricated stop quote;\n"
        "                flagged stop_gap=True).\n"
        "HOLD_CAP      — elapsed holding time reached max_hold_hours; closed at the bar open.\n"
        "BIAS_FLIP     — completed-bar bias flipped against the position side.\n"
        "DANGER        — danger exit: prior-bar range > 3x ATR with adverse body < -0.5x ATR\n"
        "                (only when danger is enabled for the equation).\n"
        "FRIDAY_CLOSE  — Friday 16:00 New-York bar; closed at the bar close.\n"
        "CENSORED      — no executable exit observed before the data/p Replay boundary;\n"
        "                outcome is UNRESOLVED_UNKNOWN with unknown P/L — never zero profit.\n"
        "\n"
        "INTRABAR PRIORITY\n"
        "SL_FIRST (default) — when one H1 candle touches both barriers, the stop wins.\n"
        "TP_FIRST (legacy comparison) — the target wins; explicitly labelled, never the default.\n"
        "Ambiguous trades are flagged (ambiguous=True) and carry P/L under EACH priority\n"
        "(net_pips_sl_first / net_pips_tp_first).\n"
        "\n"
        "OUTCOME STATES\n"
        "CLOSED_KNOWN      — finite exit price, P/L known.\n"
        "UNRESOLVED_UNKNOWN— censored; P/L unknown, excluded from realized totals, reported alongside.\n"
        "OPEN_MARKED       — live-book taxonomy only; replay never leaves positions open.\n"
    )
    return ("exit_reason_glossary_20261009.txt", text, "text/plain")


def performance_definitions() -> tuple[str, str, str]:
    text = (
        "PERFORMANCE DEFINITIONS (2026-10-09 research fix)\n"
        "=================================================\n"
        "All profit is summed PIPS, not cash or account return. Different pairs have\n"
        "different pip values and shared currency risk; no sizing/margin model is supplied.\n"
        "Summed pips are NEVER presented as cash/return.\n"
        "\n"
        "Net pips            — gross_pips minus declared cost deducted exactly once\n"
        "                      (legacy 1-pip scenario; 3-pip scenario is sensitivity only).\n"
        "Realized DD         — max drawdown of the cumulative realized (closed-trade) pip equity.\n"
        "MtM DD (H1 closes)  — drawdown of mark-to-H1-close equity; LIMITS: intra-hour\n"
        "                      extremes are unobservable from H1 OHLC.\n"
        "Max combined floating loss — worst timestamped sum of concurrent H1-close floating P/L.\n"
        "Max single-position floating loss — worst single-trade H1-close floating P/L.\n"
        "Max completed loss  — worst single closed-trade net pips.\n"
        "Max concurrent holdings — peak number of simultaneously held positions.\n"
        "Unknown/unpriced exposure — censored trades with unknown P/L; reported alongside totals.\n"
        "Win rate            — % of completed trades with net_pips > 0.\n"
        "Profit factor       — gross winning pips / gross losing pips.\n"
        "EV                  — mean net pips per completed trade.\n"
        "RoMAD               — net pips / |realized max DD| ('n.a.' when DD is zero).\n"
        "Pip-Sharpe proxy    — sqrt(252) x mean/sd of daily realized pips, zero business\n"
        "                      days included, weekend settlements rolled to next weekday.\n"
        "                      NOT a capital-return Sharpe; no risk-free subtraction; no\n"
        "                      correction for selection or serial dependence. There is NO\n"
        "                      'Sharpe > 5 = overfit' rule.\n"
        "Approx. Kelly       — win_prob - loss_prob / (avg_win/avg_loss): an approximate\n"
        "                      HISTORICAL statistic; never auto-sizes live.\n"
        "Validation status   — REUSED-TEST DIAGNOSTIC ONLY: the 'test' year (2025-10-01 →\n"
        "                      2026-10-05) was already used to select the entry equations.\n"
        "                      Strict_Valid = NO for all 240 equations.\n"
    )
    return ("performance_definitions_20261009.txt", text, "text/plain")


def comparison_row_csv(row: Dict[str, Any]) -> tuple[str, bytes, str]:
    cols = ["Configuration", "Exit mode", "Check schedule", "Entry limit",
            "Completed trades", "Net pips", "Realized DD", "Observed floating loss",
            "Win rate", "Profit factor", "Average hold", "EV", "RoMAD",
            "Ambiguous trades", "Unknown outcomes", "Validation status"]
    df = pd.DataFrame([{c: row.get(c) for c in cols}])
    return ("rows_compat.csv", df.to_csv(index=False).encode(), "text/csv")
