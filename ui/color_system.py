"""Central Field 10/Dinner color and label system.

All functions return pandas Styler-compatible CSS but every visual status also
keeps a text/icon label, so mobile and color-blind users are not forced to read
color only.
"""
from __future__ import annotations
from typing import Any
import pandas as pd

BUY_LABEL = "↑ BUY"
SELL_LABEL = "↓ SELL"
WAIT_LABEL = "WAIT"
CAUTION_LABEL = "! CAUTION"
BLOCKED_LABEL = "BLOCKED"
PARTIAL_LABEL = "PARTIAL_READY"
FAILED_LABEL = "FAILED"
SUCCESS_LABEL = "COMPLETE"


def normalize_status_label(value: Any) -> str:
    text = str(value or "").strip().upper()
    if "BUY" in text: return BUY_LABEL
    if "SELL" in text: return SELL_LABEL
    if "BLOCK" in text or "NO TRADE" in text: return BLOCKED_LABEL
    if "FAIL" in text or "ERROR" in text: return FAILED_LABEL
    if "PARTIAL" in text: return PARTIAL_LABEL
    if "CAUTION" in text or "WARN" in text or "CHECK" in text: return CAUTION_LABEL
    if "COMPLETE" in text or "READY" in text or "PUBLISHED" in text or "SUCCESS" in text: return SUCCESS_LABEL
    if "WAIT" in text: return WAIT_LABEL
    return str(value or "UNKNOWN")


def style_bias_cell(value: Any) -> str:
    label = normalize_status_label(value)
    if label == BUY_LABEL: return "background-color:#d8f3dc;color:#14532d;font-weight:800"
    if label == SELL_LABEL: return "background-color:#ffd6d6;color:#7f1d1d;font-weight:800"
    if label == BLOCKED_LABEL: return "background-color:#7f1d1d;color:#ffffff;font-weight:800"
    if label == CAUTION_LABEL: return "background-color:#ffe8b6;color:#78350f;font-weight:750"
    if label == FAILED_LABEL: return "background-color:#fee2e2;color:#991b1b;font-weight:800;border:1px solid #991b1b"
    if label == SUCCESS_LABEL: return "background-color:#dcfce7;color:#166534;font-weight:750"
    return "background-color:#f3f4f6;color:#374151"


def style_risk_cell(value: Any) -> str:
    try:
        n = float(value)
    except Exception:
        return "background-color:#f3f4f6;color:#374151"
    if n < 30: return "background-color:#dcfce7;color:#166534"
    if n < 60: return "background-color:#fef3c7;color:#92400e"
    if n < 80: return "background-color:#fee2e2;color:#991b1b"
    return "background-color:#7f1d1d;color:#ffffff;font-weight:800"


def style_quality_cell(value: Any) -> str:
    text = str(value or "").upper()
    if text.startswith("A"): return "background-color:#dcfce7;color:#14532d;font-weight:800"
    if text.startswith("B"): return "background-color:#e0f2fe;color:#075985;font-weight:750"
    if text.startswith("C"): return "background-color:#fef3c7;color:#92400e;font-weight:750"
    if text.startswith("D") or text.startswith("F") or "FAIL" in text: return "background-color:#fee2e2;color:#991b1b;font-weight:800"
    return "background-color:#f3f4f6;color:#374151"


def style_provider_cell(value: Any) -> str:
    text = str(value or "").upper()
    if "FAILED" in text or "NONE" in text or "UNAVAILABLE" in text: return style_bias_cell("FAILED")
    if "CACHE" in text: return style_bias_cell("CAUTION")
    if text.strip(): return style_bias_cell("READY")
    return "background-color:#f3f4f6;color:#374151"


def style_sync_cell(value: Any) -> str:
    return style_bias_cell(value)


def style_rank_row(row: pd.Series) -> list[str]:
    try:
        rank = int(float(row.get("Rank") or row.get("Final Rank") or 999))
    except Exception:
        rank = 999
    if rank == 1: return ["background-color:#ecfdf5;color:#064e3b;font-weight:850"] * len(row)
    if rank == 2: return ["background-color:#f0fdf4;color:#14532d;font-weight:800"] * len(row)
    if rank == 3: return ["background-color:#fefce8;color:#713f12;font-weight:750"] * len(row)
    if rank == 4: return ["background-color:#eff6ff;color:#1e3a8a;font-weight:750"] * len(row)
    return [""] * len(row)


def style_top4_rows(frame: pd.DataFrame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    return frame.style.apply(style_rank_row, axis=1)


def style_mobile_table(frame: pd.DataFrame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    styler = style_top4_rows(frame)
    for cols, fn in (
        ([c for c in frame.columns if "Bias" in c or "Permission" in c or "Status" in c], style_bias_cell),
        ([c for c in frame.columns if "Risk" in c], style_risk_cell),
        ([c for c in frame.columns if "Quality" in c or "Grade" in c], style_quality_cell),
        ([c for c in frame.columns if "Provider" in c], style_provider_cell),
        ([c for c in frame.columns if "Sync" in c or "Publication" in c], style_sync_cell),
    ):
        if cols:
            if hasattr(styler, "map"):
                styler = styler.map(fn, subset=cols)
            else:
                styler = styler.applymap(fn, subset=cols)
    return styler

__all__ = ["normalize_status_label","style_bias_cell","style_risk_cell","style_quality_cell","style_provider_cell","style_sync_cell","style_rank_row","style_top4_rows","style_mobile_table"]
