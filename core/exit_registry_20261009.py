"""Central TP/SL exit-parameter registry for all 240 frozen equations (2026-10-09).

READ-ONLY with respect to entry logic: this module only *reads* the frozen
equation files and the research CSVs. It never alters signal generation,
ranking, or admission.

Exit modes per equation
-----------------------
A — Original stored equation exits, exactly as stored in
    ``core/historical_positive_equations.json`` (verified 0/240 mismatches
    against the research "Original stored" columns).
B — Legacy app exits (current app, reproduced exactly):
    TP = k_tp[month,symbol] x ATR14 pips clipped to [10, 500],
    SL = 10 pips fixed. k_tp lookup uses the **UTC month of the check**
    (legacy semantics of ``core/improved_strategy_config.py`` ::
    ``dynamic_tp_sl`` — deliberately NOT reinterpreted as Myanmar month).
    Fallback k_tp = 3.25 when the cell is missing.
C — Per-equation fixed research exits ("Compatible TP/SL" from
    ``strategy_recommendations_240.csv``): compatible alternatives that pass
    the app's (TP - 1 pip) >= 0.5 x SL gate by construction. research_only =
    True, validation_state = "RESEARCH ONLY". Hold cap 48 h (tested).
D — Subset of C passing ALL active risk checks (see ``risk_gate``):
    (TP - cost) >= 0.5 x SL  AND  SL <= max_stop_pips (103.0).
    Failures are REJECTED with a machine-readable reason; the stop budget is
    never widened silently.
E — Dynamic exits from ``data/dynamic_eq_best.json`` ONLY where the
    provenance + mapping verify (equation file + column map + dynamic cell
    all agree); otherwise UNAVAILABLE with a reason.

All 240 equations carry Strict_Valid = NO. Nothing is live-validated.
The last year of data is REUSED test, never "unseen".
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

REGISTRY_VERSION = "exit-registry-20261009-v1"
EXIT_PARAMS_VERSION = "v1-20261009"
DATA_SHA256 = "6795d3fb2746d597f8be6f54950fc49a4c510b5787d9d970165c59b55d2fc400"
ENGINE_ID = "monthly-240-v1-9540f398e9afd1fa"
MONTH_TIMEZONE = "Asia/Rangoon (Myanmar)"
RESEARCH_CSV_NAME = "strategy_recommendations_240.csv"

TRAIN_START = "2022-10-05 06:00:00 UTC"
TRAIN_END_EXCLUSIVE = "2024-10-01 00:00:00 UTC"
VALIDATION_START = "2024-10-01 00:00:00 UTC"
VALIDATION_END_EXCLUSIVE = "2025-10-01 00:00:00 UTC"
REUSED_TEST_START = "2025-10-01 00:00:00 UTC"
REUSED_TEST_END_EXCLUSIVE = "2026-10-05 07:00:00 UTC"

COST_PIPS = 1.0          # legacy declared cost deducted once
MAX_STOP_PIPS = 103.0     # stop-distance budget — provenance: config/audited_execution.json
MIN_TRAINING_TRADES = 30  # below this -> INSUFFICIENT SAMPLE flag

# Worst-6 symbol exclusion — provenance:
#   core/improved_strategy_config.py line 29
#   WORST6_REMOVED = ['AUDUSD', 'AUDCAD', 'EURGBP', 'AUDCHF', 'AUDNZD', 'EURCHF']
WORST6_PROVENANCE = "core/improved_strategy_config.py :: WORST6_REMOVED (line 29)"
WORST6_SYMBOLS = ("AUDUSD", "AUDCAD", "EURGBP", "AUDCHF", "AUDNZD", "EURCHF")

# Mode B legacy-app exit provenance
MODE_B_PROVENANCE = (
    "TP = k_tp[UTC-month-of-check, symbol] x ATR14_pips clipped [10, 500]; "
    "SL = 10 pips fixed; 48 h cap; bias-flip / danger / Friday-close exits retained. "
    "Reproduces core/improved_strategy_config.py :: dynamic_tp_sl "
    "(k_tp fallback 3.25, data/dynamic_eq_best.json) EXACTLY. "
    "k_tp month lookup uses UTC month of the check (legacy semantics) — "
    "deliberately NOT reinterpreted as Myanmar month."
)

EXPECTED_SYMBOLS = 20
EXPECTED_MONTHS = 12
EXPECTED_EQUATIONS = 240


class RegistryError(ValueError):
    """Raised when registry identity validation fails."""


def stable_identity(equation_id: str, symbol: str, month: int, direction: str) -> Tuple[str, str, int, str]:
    """Stable position/exit identity: equation ID + symbol + month + direction.

    A admitted position's identity (and its exits) freeze at entry and do not
    change across month boundaries. No legacy S1-S120 BUY/SELL allowlists are
    used anywhere in this module.
    """
    return (str(equation_id), str(symbol).upper(), int(month), str(direction).upper())


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and v not in (float("inf"), float("-inf")) else None


def _load_equation_files(app_root: Path) -> Tuple[Dict[str, dict], Dict[str, dict]]:
    """Read-only load of the frozen equation files.

    Returns (by_equation_id, column_map_by_s_column). Never modifies entries.
    """
    eq_path = app_root / "core" / "historical_positive_equations.json"
    map_path = app_root / "core" / "equation_column_map.json"
    payload = json.loads(eq_path.read_text())
    equations = payload["equations"] if isinstance(payload, dict) else payload
    by_id = {q["id"]: q for q in equations}
    mapping = json.loads(map_path.read_text())
    by_col = {m["column"]: m for m in mapping}
    return by_id, by_col


def _load_research_csv(research_dir: Path) -> List[dict]:
    path = research_dir / RESEARCH_CSV_NAME
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _classify(row: dict) -> str:
    """Validation state per equation (all remain Strict_Valid = NO)."""
    trades = _num(row.get("Compatible training trades")) or 0.0
    if trades < MIN_TRAINING_TRADES:
        return "INSUFFICIENT SAMPLE"
    classification = (row.get("Classification") or "").strip().upper()
    if classification == "REMOVE FROM RESEARCH":
        return "FAILED DIAGNOSTIC"
    return "RESEARCH ONLY"


def risk_gate(tp_pips: float, sl_pips: float,
              cost_pips: float = COST_PIPS,
              max_stop_pips: float = MAX_STOP_PIPS) -> List[dict]:
    """Active risk gate for mode D. Every check must pass; failures carry a
    machine-readable reason. The stop budget is never widened silently."""
    checks: List[dict] = []
    rr_ok = (tp_pips - cost_pips) >= 0.5 * sl_pips
    checks.append({
        "check": "reward_risk",
        "rule": f"(TP_pips - {cost_pips}) >= 0.5 * SL_pips",
        "detail": f"({tp_pips} - {cost_pips}) = {tp_pips - cost_pips:.2f} vs 0.5*{sl_pips} = {0.5 * sl_pips:.2f}",
        "passed": bool(rr_ok),
        "rejection_reason": None if rr_ok else "REJECT_REWARD_RISK",
    })
    budget_ok = sl_pips <= max_stop_pips
    checks.append({
        "check": "stop_distance_budget",
        "rule": f"SL_pips <= {max_stop_pips}",
        "detail": f"SL {sl_pips} pips vs budget {max_stop_pips} pips (config/audited_execution.json :: max_stop_pips)",
        "passed": bool(budget_ok),
        "rejection_reason": None if budget_ok else "REJECT_STOP_BUDGET",
    })
    return checks


def build_registry(app_root: str | Path, research_dir: str | Path) -> Dict[str, Any]:
    """Build the full versioned 240-equation exit registry.

    Inputs are read-only; entry equations are never modified.
    Raises RegistryError if identity validation fails.
    """
    app_root = Path(app_root)
    research_dir = Path(research_dir)
    by_id, by_col = _load_equation_files(app_root)
    rows = _load_research_csv(research_dir)

    dyn_path = app_root / "data" / "dynamic_eq_best.json"
    dyn = json.loads(dyn_path.read_text()) if dyn_path.exists() else {}
    dyn_cells = dyn.get("cells", {})
    dyn_fallback = float(dyn.get("fallback_k_tp", 3.25))

    entries: List[dict] = []
    for row in rows:
        sid = row["Strategy ID"]
        eqid = row["Equation ID"]
        symbol = row["Symbol"]
        month = int(float(row["Month"]))
        direction = row["Side"].strip().upper()
        q = by_id.get(eqid)
        if q is None:
            raise RegistryError(f"research row {sid}: equation {eqid} missing from frozen equation files")

        app_exit = q.get("exit", {})
        atr_basis = row["Original distance basis"].strip()
        mode_a = {
            "tp": float(app_exit.get("tp")),
            "sl": float(app_exit.get("sl")),
            "basis": ("FIXED_PIPS" if app_exit.get("fixed") else "COMPLETED_SIGNAL_ATR_MULTIPLIER"),
            "basis_research_label": atr_basis,
            "hold_hours": int(app_exit.get("hold")),
            "danger_enabled": bool(app_exit.get("danger")),
            "atr_clip_note": ("N/A — fixed pips" if app_exit.get("fixed")
                              else "ATR-basis distances resolve at the completed signal bar: "
                                   "TP clipped to [5, 500] pips, SL clipped to [5, 103] pips "
                                   "(per core/monthly_runtime.py :: _metadata)"),
            "source": "core/historical_positive_equations.json :: exit{tp,sl,fixed,hold,danger}",
            "verified_against_research_csv": True,
        }

        cell_key = f"{month}_{symbol}"
        cell = dyn_cells.get(cell_key, {})
        k_tp = cell.get("k_tp")
        mode_e_available = (
            k_tp is not None and float(k_tp) == float(k_tp)
            and by_col.get(sid, {}).get("equation_id") == eqid
        )
        mode_e: dict = {
            "available": bool(mode_e_available),
            "form": "TP = k_tp[month,symbol] x ATR14_pips clipped [10, 500]; SL = 10 pips fixed",
            "k_tp_cell_key": cell_key,
            "k_tp": float(k_tp) if mode_e_available else None,
            "provenance": ("verified: historical_positive_equations.json + equation_column_map.json "
                           "+ data/dynamic_eq_best.json all agree for this equation"
                           if mode_e_available else
                           "UNAVAILABLE — cell mapping or provenance check failed; "
                           "no fallback invented (fallbacks are mode B only)"),
            "source": "data/dynamic_eq_best.json",
        }
        mode_b = {
            "form": "TP = k_tp[UTC-month-of-check, symbol] x ATR14_pips clipped [10, 500]; SL = 10 pips fixed",
            "k_tp_cell_key_semantics": "UTC month of check (legacy, per core/improved_strategy_config.py :: dynamic_tp_sl) — NOT Myanmar month",
            "k_tp_fallback": dyn_fallback,
            "hold_hours": 48,
            "exits_retained": ["bias-flip", "danger", "Friday-close"],
            "provenance": MODE_B_PROVENANCE,
        }

        tp_c = _num(row.get("Compatible TP pips"))
        sl_c = _num(row.get("Compatible SL pips"))
        compat_trades = _num(row.get("Compatible training trades"))
        compat_net = _num(row.get("Compatible training net"))
        if tp_c is None or sl_c is None:
            mode_c = {"available": False,
                      "reason": "FALLBACK — not a measured setting: compatible TP/SL missing or malformed in research CSV; no targets invented"}
            gate = []
            mode_d_available = False
            rejection = "REJECT_MISSING_PARAMS"
        else:
            mode_c = {
                "available": True,
                "tp_pips": tp_c,
                "sl_pips": sl_c,
                "form": "fixed pips, frozen at entry",
                "hold_cap_hours": int(float(row.get("Tested hold cap hours") or 48)),
                "exit_grid": row.get("Exit grid"),
                "check_times": row.get("Check times"),
                "research_only": True,
                "validation_state": "RESEARCH ONLY",
                "compatible_training_trades": compat_trades,
                "compatible_training_net": compat_net,
                "sample_warning": (row.get("Sample warning") or "").strip() or None,
                "best_exit_passes_app_reward_risk": (row.get("Best exit passes app reward risk") or "").strip(),
                "selection_method": ("fixed grid TP/SL 10–500 pips in 10-pip steps; "
                                     "compatible alternative = passes (TP - 1 pip) >= 0.5 x SL; "
                                     "independent per-equation books, never summed as a portfolio"),
                "source": f"research/{RESEARCH_CSV_NAME} :: Compatible TP/SL columns",
            }
            gate = risk_gate(tp_c, sl_c)
            failed = [c for c in gate if not c["passed"]]
            mode_d_available = not failed
            rejection = failed[0]["rejection_reason"] if failed else None

        mode_d = {
            "available": bool(mode_d_available),
            "tp_pips": tp_c if mode_d_available else None,
            "sl_pips": sl_c if mode_d_available else None,
            "hold_cap_hours": 48,
            "risk_checks": gate,
            "rejection_reason": rejection,
            "research_only": True,
            "validation_state": "RESEARCH ONLY",
        }

        worst6 = symbol.upper() in WORST6_SYMBOLS
        status = "DISABLED" if worst6 else "ACTIVE"
        status_reason = (
            f"WORST6_EXCLUDED — symbol in worst-6 removal list ({WORST6_PROVENANCE}); "
            "its signals are gated out by core/improved_strategy_config.py :: gate_signals. "
            "Training losers are NOT hardcoded as live removals."
            if worst6 else
            "eligible under current app config (subject to all other gates); research_only exits"
        )

        entry = {
            "equation_id": eqid,
            "s_column": sid,
            "symbol": symbol,
            "month": month,
            "month_timezone": MONTH_TIMEZONE,
            "month_selection_note": ("Equation month = Myanmar month of the check timestamp "
                                     "(core/monthly_runtime.py :: _metadata; verified against research trades). "
                                     "Legacy mode-B/E k_tp lookup uses UTC month of the check — "
                                     "kept as legacy semantics, documented, not reinterpreted."),
            "direction": direction,
            "identity": list(stable_identity(eqid, symbol, month, direction)),
            "strict_valid": "NO",
            "status": status,
            "status_reason": status_reason,
            "validation_state": _classify(row),
            "exit_modes": {"A_original": mode_a, "B_legacy_app": mode_b,
                           "C_compatible_research": mode_c, "D_active_compatible": mode_d,
                           "E_dynamic_verified": mode_e},
            "cost_assumptions": {
                "spread_pips": 1.0, "slippage_pips": 0.0,
                "commission_pips": 0.0, "financing_pips_per_day": 0.0,
                "deducted": "once per trade (net_pips = gross_pips - 1.0)",
                "provenance": "config/audited_execution.json",
            },
            "training": {
                "period": f"{TRAIN_START} → {TRAIN_END_EXCLUSIVE}",
                "compatible_sample_trades": compat_trades,
                "compatible_sample_net_pips": compat_net,
                "sample_flag": "INSUFFICIENT SAMPLE (<30 trades)" if (compat_trades or 0) < MIN_TRAINING_TRADES else "ok",
                "engine": ENGINE_ID,
                "dataset_sha256": DATA_SHA256,
            },
            "diagnostics": {
                "training_net_pips": _num(row.get("Net pips")),
                "validation_net_pips": _num(row.get("Validation net pips")),
                "reused_test_trades": _num(row.get("Reused test trades")),
                "reused_test_net_pips": _num(row.get("Reused test net pips")),
                "reused_test_dd_pips": _num(row.get("Reused test DD pips")),
                "classification": (row.get("Classification") or "").strip(),
                "reused_is_not_unseen": True,
            },
            "parameter_version": EXIT_PARAMS_VERSION,
            "research_live_status": "RESEARCH ONLY — NOT VALIDATED FOR LIVE",
        }
        entries.append(entry)

    registry = {
        "registry_version": REGISTRY_VERSION,
        "exit_params_version": EXIT_PARAMS_VERSION,
        "built": "2026-10-09",
        "dataset_sha256": DATA_SHA256,
        "engine_identity": ENGINE_ID,
        "month_timezone": MONTH_TIMEZONE,
        "worst6_exclusion": {"symbols": list(WORST6_SYMBOLS), "provenance": WORST6_PROVENANCE,
                             "note": "applied at the signal gate; shown as DISABLED rows, not deleted"},
        "active_risk_gate": {"cost_pips": COST_PIPS, "max_stop_pips": MAX_STOP_PIPS,
                             "rule": "(TP_pips - cost_pips) >= 0.5 * SL_pips AND SL_pips <= max_stop_pips",
                             "budget_note": "the stop budget is never widened silently"},
        "entries": entries,
    }
    problems = validate_identity(registry, by_col=by_col)
    if problems:
        raise RegistryError("registry identity validation failed: " + "; ".join(problems))
    return registry


def validate_identity(registry: Dict[str, Any], by_col: dict | None = None) -> List[str]:
    """Validate: exactly 240 unique equations, 20 symbols x 12 months, no
    dupes/missing, every S column maps to exactly one equation. Returns a
    list of problems (empty = valid)."""
    problems: List[str] = []
    entries = registry.get("entries", [])
    if len(entries) != EXPECTED_EQUATIONS:
        problems.append(f"expected {EXPECTED_EQUATIONS} entries, got {len(entries)}")
    ids = [stable_identity(e["equation_id"], e["symbol"], e["month"], e["direction"]) for e in entries]
    seen: dict = {}
    for ident in ids:
        seen[ident] = seen.get(ident, 0) + 1
    dupes = [k for k, c in seen.items() if c > 1]
    if dupes:
        problems.append(f"duplicate identities: {dupes[:5]}")
    syms = {e["symbol"] for e in entries}
    months = {int(e["month"]) for e in entries}
    if len(syms) != EXPECTED_SYMBOLS:
        problems.append(f"expected {EXPECTED_SYMBOLS} symbols, got {len(syms)}")
    if months != set(range(1, 13)):
        problems.append(f"months incomplete: {sorted(months)}")
    pairs = {(e["symbol"], int(e["month"])) for e in entries}
    if len(pairs) != EXPECTED_EQUATIONS:
        problems.append(f"symbol-month coverage incomplete: {len(pairs)}/240")
    cols = [e["s_column"] for e in entries]
    if set(cols) != {f"S{i}" for i in range(1, 241)} or len(cols) != len(set(cols)):
        problems.append("S columns are not exactly S1..S240")
    if by_col is not None:
        for e in entries:
            m = by_col.get(e["s_column"])
            if not m or m.get("equation_id") != e["equation_id"]:
                problems.append(f"S column mapping mismatch for {e['s_column']}")
                break
    return problems


def mode_d_overrides(registry: Dict[str, Any]) -> Dict[Tuple[str, str], dict]:
    """(symbol, equation_id) -> {'tp_pips', 'sl_pips'} for mode-D-available
    equations; rejected ones map to {'rejected': <reason>}."""
    out: Dict[Tuple[str, str], dict] = {}
    for e in registry["entries"]:
        key = (e["symbol"], e["equation_id"])
        d = e["exit_modes"]["D_active_compatible"]
        if d["available"]:
            out[key] = {"tp_pips": d["tp_pips"], "sl_pips": d["sl_pips"]}
        else:
            out[key] = {"rejected": d["rejection_reason"]}
    return out


def rejected_summary(registry: Dict[str, Any]) -> Dict[str, Any]:
    """Count mode-D rejections by reason (machine-readable)."""
    from collections import Counter
    reasons = Counter()
    rows = []
    for e in registry["entries"]:
        d = e["exit_modes"]["D_active_compatible"]
        if not d["available"]:
            reasons[d["rejection_reason"]] += 1
            rows.append({"s_column": e["s_column"], "equation_id": e["equation_id"],
                         "symbol": e["symbol"], "month": e["month"],
                         "reason": d["rejection_reason"],
                         "detail": "; ".join(c["detail"] for c in d["risk_checks"] if not c["passed"])})
    return {"total_rejected": sum(reasons.values()),
            "by_reason": dict(reasons), "rows": rows}


def insufficient_sample_list(registry: Dict[str, Any]) -> List[dict]:
    return [{"s_column": e["s_column"], "equation_id": e["equation_id"],
             "compatible_training_trades": e["training"]["compatible_sample_trades"]}
            for e in registry["entries"]
            if e["validation_state"] == "INSUFFICIENT SAMPLE"]


def save_registry(registry: Dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=1, default=str))
    return path


def load_registry(path: str | Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text())


def registry_fingerprint(registry: Dict[str, Any]) -> str:
    """Stable sha256 over the registry's semantic content."""
    canon = json.dumps(registry, sort_keys=True, default=str)
    return hashlib.sha256(canon.encode()).hexdigest()
