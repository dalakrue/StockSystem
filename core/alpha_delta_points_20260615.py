"""Display-only alpha/delta/data-point calculations for projection paths.

This does not replace or train any forecast engine. It reads existing blue/red
projection points and creates a small diagnostic table: difference, ratio,
divergence mean, alpha now/previous, delta point, and combined data point.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import math
import pandas as pd
import numpy as np
import streamlit as st


def _num(v: Any, default: float = float('nan')) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _find_col(df: pd.DataFrame, aliases) -> Optional[str]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return None
    low = {str(c).lower().strip(): c for c in df.columns}
    for a in aliases:
        if str(a).lower() in low:
            return low[str(a).lower()]
    for c in df.columns:
        n = str(c).lower().replace('_', ' ')
        for a in aliases:
            aa = str(a).lower().replace('_', ' ')
            if aa in n:
                return c
    return None


def _extract_path(df: Any, label: str) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame(columns=["idx", "time", label])
    tcol = _find_col(df, ["time", "datetime", "future time", "date", "timestamp"])
    ycol = _find_col(df, [
        "Accuracy Adjusted Price", "accuracy adjusted close", "close", "predicted close", "projected close",
        "estimated_price_close", "path", "price", "expected_path", "Projected Path",
    ])
    if ycol is None:
        numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        ycol = numeric[0] if numeric else None
    if ycol is None:
        return pd.DataFrame(columns=["idx", "time", label])
    out = pd.DataFrame({label: pd.to_numeric(df[ycol], errors="coerce")})
    out["idx"] = range(1, len(out) + 1)
    if tcol:
        out["time"] = pd.to_datetime(df[tcol], errors="coerce")
    else:
        out["time"] = pd.NaT
    return out.dropna(subset=[label]).reset_index(drop=True)


def build_alpha_delta_points(blue_path: Any, red_path: Any, *, blue_label: str = "Blue Path", red_label: str = "Red Path") -> pd.DataFrame:
    b = _extract_path(blue_path, blue_label)
    r = _extract_path(red_path, red_label)
    if b.empty or r.empty:
        return pd.DataFrame()
    n = min(len(b), len(r))
    b = b.head(n).copy().reset_index(drop=True)
    r = r.head(n).copy().reset_index(drop=True)
    out = pd.DataFrame({
        "Point": range(1, n + 1),
        "time": r["time"].where(r["time"].notna(), b["time"]),
        blue_label: b[blue_label].astype(float),
        red_label: r[red_label].astype(float),
    })
    out["Difference"] = out[red_label] - out[blue_label]
    out["Difference pips"] = out["Difference"] * 10000.0
    out["Ratio Red/Blue"] = out[red_label] / out[blue_label].replace(0, np.nan)
    out["Ratio Drift pips"] = (out["Ratio Red/Blue"] - 1.0) * 10000.0
    out["Divergence Mean pips"] = out["Difference pips"].abs().expanding().mean()
    # Alpha is now explicitly based on blue-vs-red difference, ratio, and
    # divergence mean. Delta compares Alpha Now against Alpha Prev.
    out["Alpha Now"] = out["Difference pips"]
    out["Alpha Prev"] = out["Alpha Now"].shift(1).fillna(0.0)
    out["Alpha Difference Now-Prev"] = out["Alpha Now"] - out["Alpha Prev"]
    out["Alpha Ratio Now/Prev"] = out["Alpha Now"] / out["Alpha Prev"].replace(0, np.nan)
    out["Alpha Ratio Drift"] = (out["Alpha Ratio Now/Prev"] - 1.0).replace([np.inf, -np.inf], np.nan)
    out["Alpha Divergence Mean Now-Prev"] = out["Alpha Difference Now-Prev"].abs().expanding().mean()
    out["Delta Point"] = out["Alpha Difference Now-Prev"]
    out["Data Point Score"] = (
        out["Alpha Now"].fillna(0)
        + out["Delta Point"].fillna(0)
        + out["Ratio Drift pips"].fillna(0)
        + out["Alpha Divergence Mean Now-Prev"].fillna(0)
    ) / 4.0
    out["Divergence Direction"] = np.where(out["Difference"] > 0, "RED ABOVE BLUE", np.where(out["Difference"] < 0, "RED BELOW BLUE", "EQUAL"))
    for c in [blue_label, red_label, "Difference", "Ratio Red/Blue", "Alpha Ratio Now/Prev", "Alpha Ratio Drift"]:
        out[c] = out[c].round(6)
    for c in ["Difference pips", "Ratio Drift pips", "Divergence Mean pips", "Alpha Now", "Alpha Prev", "Alpha Difference Now-Prev", "Alpha Divergence Mean Now-Prev", "Delta Point", "Data Point Score"]:
        out[c] = out[c].round(3)
    return out


def summarize_alpha_delta(df: pd.DataFrame) -> Dict[str, Any]:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {"available": False, "message": "No matching blue/red path points available."}
    last = df.iloc[-1]
    return {
        "available": True,
        "points": int(len(df)),
        "alpha_now_pips": float(last.get("Alpha Now", 0)),
        "alpha_prev_pips": float(last.get("Alpha Prev", 0)),
        "delta_point": float(last.get("Delta Point", 0)),
        "alpha_ratio_now_prev": float(last.get("Alpha Ratio Now/Prev", 0)) if pd.notna(last.get("Alpha Ratio Now/Prev", float('nan'))) else 0.0,
        "alpha_divergence_now_prev": float(last.get("Alpha Divergence Mean Now-Prev", 0)),
        "divergence_mean_pips": float(last.get("Divergence Mean pips", 0)),
        "data_point_score": float(last.get("Data Point Score", 0)),
        "direction": str(last.get("Divergence Direction", "-")),
    }


def render_alpha_delta_point_panel(blue_path: Any, red_path: Any, *, key: str, title: str = "Alpha / Delta Data Point", blue_label: str = "Blue Path", red_label: str = "Red Path") -> pd.DataFrame:
    df = build_alpha_delta_points(blue_path, red_path, blue_label=blue_label, red_label=red_label)
    summary = summarize_alpha_delta(df)
    st.session_state[f"{key}_alpha_delta_summary_20260615"] = summary
    st.session_state[f"{key}_alpha_delta_table_20260615"] = df
    with st.expander(f"📍 Open / Close — {title}", expanded=False):
        st.caption("Difference + ratio + divergence mean between alpha now and alpha previous. Display-only; original prediction logic is untouched.")
        if not summary.get("available"):
            st.info(summary.get("message", "Alpha/delta points are not ready yet."))
            return df
        c = st.columns(6)
        c[0].metric("Alpha Now", f"{summary['alpha_now_pips']:.3f} pips")
        c[1].metric("Alpha Prev", f"{summary['alpha_prev_pips']:.3f} pips")
        c[2].metric("Delta Point", f"{summary['delta_point']:.3f}")
        c[3].metric("Alpha Ratio", f"{summary.get('alpha_ratio_now_prev', 0):.3f}")
        c[4].metric("Alpha Div Mean", f"{summary.get('alpha_divergence_now_prev', 0):.3f}")
        c[5].metric("Data Point", f"{summary['data_point_score']:.3f}")
        try:
            from ui.stable_ui_libs_20260615 import modern_table
            modern_table(df.tail(80), f"{key}_alpha_delta_modern", height=320)
        except Exception:
            st.dataframe(df.tail(80), use_container_width=True, hide_index=True, height=320)
    return df


def add_alpha_delta_vertical_markers(
    fig: Any,
    blue_path: Any,
    red_path: Any,
    *,
    blue_label: str = "Blue Path",
    red_label: str = "Red Path",
    key: str = "alpha_delta_vertical",
) -> Any:
    """Add Alpha Point and Delta Point as vertical chart markers.

    This is display-only.  It intentionally uses vertical vlines/markers instead
    of horizontal hlines so alpha/delta read as candle/time points, not price
    levels.  It safely returns the original fig on any error.
    """
    try:
        df = build_alpha_delta_points(blue_path, red_path, blue_label=blue_label, red_label=red_label)
        if not isinstance(df, pd.DataFrame) or df.empty or "time" not in df.columns:
            return fig
        # Prefer real times. If time is empty, no vertical point can be drawn.
        df = df.copy()
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.dropna(subset=["time"])
        if df.empty:
            return fig
        alpha_idx = pd.to_numeric(df.get("Alpha Now", pd.Series(dtype=float)), errors="coerce").abs().idxmax()
        delta_idx = pd.to_numeric(df.get("Delta Point", pd.Series(dtype=float)), errors="coerce").abs().idxmax()
        points = [("Alpha Point", alpha_idx, "dot"), ("Delta Point", delta_idx, "dash")]
        for label, idx, dash in points:
            if idx not in df.index:
                continue
            row = df.loc[idx]
            x = row.get("time")
            y = row.get(red_label, row.get(blue_label))
            if pd.isna(x):
                continue
            try:
                fig.add_vline(x=x, line_dash=dash, line_width=2, opacity=.78, annotation_text=label, annotation_position="top")
            except Exception:
                pass
            try:
                if pd.notna(y):
                    fig.add_trace(__import__("plotly.graph_objects", fromlist=["Scatter"]).Scatter(
                        x=[x], y=[float(y)], mode="markers+text", text=[label], textposition="top center", name=label, showlegend=True,
                        marker={"size": 12, "symbol": "diamond" if "Delta" in label else "star"},
                    ))
            except Exception:
                pass
        st.session_state[f"{key}_vertical_points_20260615"] = df
        return fig
    except Exception:
        return fig
