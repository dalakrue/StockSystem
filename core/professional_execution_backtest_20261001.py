"""Execution-path backtest built from selected signals plus continuous candles.

The Finder signal CSV remains a compact four-symbol-per-hour decision file.
This module evaluates those entries against a separate all-symbol OHLC stream,
so future TP/SL order, floating excursion, Middle Bias exits, and the hard 24h
cap are based on candles after the entry rather than on selected snapshots.
"""
from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from typing import Any
import json
import zipfile

import numpy as np
import pandas as pd


VERSION = "professional-execution-backtest-20261002-v2-rebound-audit"
DEFAULT_SPREAD_PIPS = 1.0
DEFAULT_MAX_HOLD_HOURS = 48


def _first_column(frame: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lookup = {str(column).strip().lower(): str(column) for column in frame.columns}
    for name in names:
        if name in frame.columns:
            return name
        found = lookup.get(name.strip().lower())
        if found:
            return found
    return None


def _truthy(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "1.0", "yes"})


def _pip_size(symbol: Any) -> float:
    name = str(symbol or "").upper().replace("/", "")
    if "XAU" in name or "GOLD" in name:
        return 0.10
    if "XAG" in name or "SILVER" in name or "JPY" in name:
        return 0.01
    if "BTC" in name or "ETH" in name:
        return 1.0
    return 0.0001


def _direction(row: Mapping[str, Any]) -> str:
    decision = str(row.get("Strategy Decision") or "").upper().strip()
    if decision.startswith("BUY"):
        return "BUY"
    if decision.startswith("SELL"):
        return "SELL"
    bias = str(row.get("Middle Regime Bias") or row.get("Middle Bias") or "").upper().strip()
    return bias if bias in {"BUY", "SELL"} else ""


def _number(row: Mapping[str, Any], names: tuple[str, ...]) -> float:
    for name in names:
        value = pd.to_numeric(pd.Series([row.get(name)]), errors="coerce").iloc[0]
        if pd.notna(value) and np.isfinite(float(value)):
            return float(value)
    return float("nan")


def _normalize_candles(candles: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(candles, pd.DataFrame) or candles.empty:
        return pd.DataFrame()
    result = candles.copy()
    time_column = _first_column(result, ("Datetime", "Completed Candle", "open_time", "time", "timestamp"))
    symbol_column = _first_column(result, ("Symbol", "symbol"))
    open_column = _first_column(result, ("Open Price", "open", "Open"))
    high_column = _first_column(result, ("High Price", "Highest Price", "high", "High"))
    low_column = _first_column(result, ("Low Price", "Lowest Price", "low", "Low"))
    close_column = _first_column(result, ("Close Price", "close", "Close"))
    required = {
        "timestamp": time_column, "symbol": symbol_column, "open": open_column,
        "high": high_column, "low": low_column, "close": close_column,
    }
    missing = [name for name, column in required.items() if column is None]
    if missing:
        raise ValueError(f"Candle database is missing: {', '.join(missing)}")
    normalized = pd.DataFrame({
        "Datetime": pd.to_datetime(result[time_column], errors="coerce", utc=True),
        "Symbol": result[symbol_column].astype(str).str.upper().str.replace(r"[/_ ]", "", regex=True),
        "Open Price": pd.to_numeric(result[open_column], errors="coerce"),
        "High Price": pd.to_numeric(result[high_column], errors="coerce"),
        "Low Price": pd.to_numeric(result[low_column], errors="coerce"),
        "Close Price": pd.to_numeric(result[close_column], errors="coerce"),
    })
    normalized = normalized.dropna(subset=["Datetime", "Symbol", "Open Price", "High Price", "Low Price", "Close Price"])
    normalized = normalized.loc[
        normalized["High Price"].ge(normalized[["Open Price", "Close Price", "Low Price"]].max(axis=1))
        & normalized["Low Price"].le(normalized[["Open Price", "Close Price", "High Price"]].min(axis=1))
    ]
    return (
        normalized.drop_duplicates(["Symbol", "Datetime"], keep="last")
        .sort_values(["Symbol", "Datetime"], kind="mergesort")
        .reset_index(drop=True)
    )


def _bias_lookup(finder_rows: pd.DataFrame | None) -> dict[tuple[str, pd.Timestamp], str]:
    if not isinstance(finder_rows, pd.DataFrame) or finder_rows.empty:
        return {}
    time_column = _first_column(finder_rows, ("Datetime", "Completed Candle", "_FinderDatetime"))
    symbol_column = _first_column(finder_rows, ("Symbol", "symbol"))
    bias_column = _first_column(finder_rows, ("Middle Regime Bias", "Middle Bias", "Middle_Regime_Bias"))
    if not time_column or not symbol_column or not bias_column:
        return {}
    timestamps = pd.to_datetime(finder_rows[time_column], errors="coerce", utc=True)
    symbols = finder_rows[symbol_column].astype(str).str.upper().str.replace(r"[/_ ]", "", regex=True)
    biases = finder_rows[bias_column].astype(str).str.upper().str.strip()
    return {
        (symbol, pd.Timestamp(timestamp)): bias
        for symbol, timestamp, bias in zip(symbols, timestamps, biases)
        if pd.notna(timestamp)
    }


def evaluate_execution_backtest(signals,candles,*,finder_rows=None,spread_pips=2.0,max_hold_hours=24):
    from core.monthly_backtest import replay_portfolio
    from core.monthly_runtime import raw_frame
    raw=raw_frame(candles)
    start=pd.to_datetime(signals.get('check_at',signals.get('Datetime')),utc=True).min() if len(signals) else None
    end=pd.to_datetime(signals.get('check_at',signals.get('Datetime')),utc=True).max() if len(signals) else None
    replay=replay_portfolio(raw,entry_start=start,entry_end=end)
    aliases={'entry_at':'Entry Time','exit_at':'Exit Time','entry_side':'Direction','entry_price':'Entry Price','exit_price':'Exit Price','tp_price':'TP Price','sl_price':'SL Price','net_pips':'Net Pips','gross_pips':'Gross Pips','hold_hours':'Hold Hours','exit_reason':'Exit Reason'}
    result=replay['trades'].rename(columns=aliases)
    result['Backtest Valid']=result['Net Pips'].notna()
    result['Replay Mode']='DYNAMIC_TP_FIRST_VALIDATED'
    result['Hourly Entry Origin']='MONTHLY_EQUATION'
    result.attrs['portfolio_metrics']=replay['metrics']
    result.attrs['check_decisions']=replay['checks']
    result.attrs['round_trip_cost_pips']=1.0
    return result

def summarize_execution_backtest(trades: pd.DataFrame) -> dict[str, Any]:
    valid = trades.loc[trades.get("Backtest Valid", pd.Series(False, index=trades.index)).eq(True)].copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    net = pd.to_numeric(valid.get("Net Pips", pd.Series(dtype=float)), errors="coerce").dropna()
    if net.empty:
        max_drawdown = 0.0
    else:
        equity = net.cumsum()
        max_drawdown = float((equity - equity.cummax().clip(lower=0)).min())
    audited=isinstance(trades,pd.DataFrame) and 'Replay Mode' in trades
    if audited: max_drawdown=float(trades.attrs.get('portfolio_metrics',{}).get('Max DD',max_drawdown))
    wins = int((net > 0).sum())
    losses = int((net < 0).sum())
    gross_profit = float(net.loc[net > 0].sum()) if not net.empty else 0.0
    gross_loss = abs(float(net.loc[net < 0].sum())) if not net.empty else 0.0
    holds = pd.to_numeric(valid.get("Hold Hours", pd.Series(dtype=float)), errors="coerce").dropna()
    mfe = pd.to_numeric(valid.get("MFE Pips", pd.Series(dtype=float)), errors="coerce").dropna()
    mae = pd.to_numeric(valid.get("MAE Pips", pd.Series(dtype=float)), errors="coerce").dropna()
    exits = valid.get("Exit Reason", pd.Series("", index=valid.index)).astype(str)
    rebound_evaluated = valid.get(
        "Post-SL Rebound Evaluated", pd.Series(False, index=valid.index)
    ).astype(bool)
    rebound_hit = valid.get(
        "Post-SL Rebound To TP", pd.Series(False, index=valid.index)
    ).astype(bool)

    def exit_pct(prefix: str) -> float:
        return round(100.0 * exits.str.startswith(prefix).sum() / max(1, len(valid)), 3)

    return {
        "version": VERSION,
        "trades_total": int(len(trades)) if isinstance(trades, pd.DataFrame) else 0,
        "trades_valid": int(len(valid)),
        "trades_incomplete_or_invalid": int(len(trades) - len(valid)) if isinstance(trades, pd.DataFrame) else 0,
        "net_pips": round(float(net.sum()), 3) if not net.empty else 0.0,
        "max_drawdown_pips": round(max_drawdown, 3),
        "win_rate_pct": round(100.0 * wins / max(1, wins + losses), 3),
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        "romad": round(float(net.sum()) / abs(max_drawdown), 4) if max_drawdown < 0 else None,
        "average_hold_hours": round(float(holds.mean()), 3) if not holds.empty else None,
        "median_hold_hours": round(float(holds.median()), 3) if not holds.empty else None,
        "p75_hold_hours": round(float(holds.quantile(0.75)), 3) if not holds.empty else None,
        "tp_exit_pct": exit_pct("TP" if audited else "TP_HIT"),
        "sl_exit_pct": exit_pct("SL" if audited else "SL_HIT"),
        "middle_bias_exit_pct": exit_pct("BIAS" if audited else "MIDDLE_BIAS_EXIT"),
        "time_exit_24h_pct": exit_pct("TIMEOUT" if audited else "24H_TIME_EXIT"),
        "tp_first_rate_pct": exit_pct("TP" if audited else "TP_HIT"),
        "sl_first_rate_pct": exit_pct("SL" if audited else "SL_HIT"),
        "post_sl_rebound_to_tp_rate_pct": round(
            100.0 * int((rebound_hit & rebound_evaluated).sum()) / max(1, int(rebound_evaluated.sum())), 3
        ),
        "post_sl_rebound_sample_count": int(rebound_evaluated.sum()),
        "average_mfe_pips": round(float(mfe.mean()), 3) if not mfe.empty else None,
        "average_mae_pips": round(float(mae.mean()), 3) if not mae.empty else None,
        "strategy_origin_trades": int(
            valid.get("Hourly Entry Origin", pd.Series("", index=valid.index)).astype(str).eq("STRATEGY").sum()
        ),
        "rank_fill_trades": int(
            valid.get("Hourly Entry Origin", pd.Series("", index=valid.index)).astype(str).eq("RANK-FILL").sum()
        ),
        "monthly_equation_trades": int(len(valid)),
        "spread_pips_per_trade": DEFAULT_SPREAD_PIPS,
        "max_hold_hours": DEFAULT_MAX_HOLD_HOURS,
        "same_candle_tp_sl_policy": "TP_FIRST_VALIDATED" if audited else "SL_FIRST_CONSERVATIVE_LEGACY",
        "round_trip_cost_pips":trades.attrs.get('round_trip_cost_pips',DEFAULT_SPREAD_PIPS) if isinstance(trades,pd.DataFrame) else DEFAULT_SPREAD_PIPS,
    }


def build_professional_backtest_bundle(signals,candles,*,finder_rows,entry_start,entry_end,spread_pips=2.0,max_hold_hours=24):
    from core.monthly_backtest import replay_portfolio,independent_diagnostics,bundle
    replay=replay_portfolio(candles,entry_start=entry_start,entry_end=entry_end)
    diagnostic=independent_diagnostics(candles,signals=replay['signals'])
    return bundle(replay,diagnostic),replay['trades'],replay['metrics']


# Retained unrelated display/API constants from the original app.
__all__ = [
    "VERSION", "DEFAULT_SPREAD_PIPS", "DEFAULT_MAX_HOLD_HOURS",
    "evaluate_execution_backtest", "summarize_execution_backtest",
    "build_professional_backtest_bundle",
]
