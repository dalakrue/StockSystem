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
DEFAULT_SPREAD_PIPS = 2.0
DEFAULT_MAX_HOLD_HOURS = 24


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


def evaluate_execution_backtest(
    signals: pd.DataFrame,
    candles: pd.DataFrame,
    *,
    finder_rows: pd.DataFrame | None = None,
    spread_pips: float = DEFAULT_SPREAD_PIPS,
    max_hold_hours: int = DEFAULT_MAX_HOLD_HOURS,
) -> pd.DataFrame:
    """Evaluate selected entries against every future candle of their symbol.

    Intrabar ordering cannot be known from OHLC alone.  If a candle touches TP
    and SL, the deterministic conservative policy records SL first.  TP/SL are
    evaluated before a Middle Bias flip because barriers are intrabar while the
    completed-candle bias is known at the candle close.
    """
    if not isinstance(signals, pd.DataFrame) or signals.empty:
        return pd.DataFrame()
    selected = signals.copy()
    if "Hourly 4 Entry" in selected.columns:
        selected = selected.loc[_truthy(selected["Hourly 4 Entry"])].copy()
    if selected.empty:
        return pd.DataFrame()
    signal_time_column = _first_column(selected, ("Datetime", "Completed Candle", "_FinderDatetime"))
    signal_symbol_column = _first_column(selected, ("Symbol", "symbol"))
    if not signal_time_column or not signal_symbol_column:
        raise ValueError("Signals require Datetime and Symbol columns")
    selected["_entry_time"] = pd.to_datetime(selected[signal_time_column], errors="coerce", utc=True)
    selected["_symbol"] = selected[signal_symbol_column].astype(str).str.upper().str.replace(r"[/_ ]", "", regex=True)
    selected = selected.dropna(subset=["_entry_time", "_symbol"])

    movie = _normalize_candles(candles)
    if movie.empty:
        raise ValueError("The continuous candle database is empty")
    grouped = {}
    for symbol, group in movie.groupby("Symbol", sort=False):
        ordered = group.sort_values("Datetime", kind="mergesort").reset_index(drop=True)
        grouped[symbol] = (ordered, pd.DatetimeIndex(ordered["Datetime"]))
    biases = _bias_lookup(finder_rows)
    spread = max(0.0, float(spread_pips))
    hold_cap = max(1, int(max_hold_hours))
    rows: list[dict[str, Any]] = []

    for _, signal in selected.sort_values(["_entry_time", "_symbol"], kind="mergesort").iterrows():
        symbol = str(signal["_symbol"])
        entry_time = pd.Timestamp(signal["_entry_time"])
        side = _direction(signal)
        entry_price = _number(signal, ("Close Price", "Entry Price", "close", "Close"))
        tp_price = _number(signal, ("Suggested TP Price", "Suggested TP", "TP Price"))
        sl_price = _number(signal, ("Suggested SL Price", "Suggested SL", "SL Price"))
        pip = _pip_size(symbol)
        horizon_end = entry_time + pd.Timedelta(hours=hold_cap)
        strategy_ids = [
            str(column).split()[0]
            for column in signal.index
            if str(column).startswith("S")
            and str(column).endswith(" Entry Condition")
            and str(signal.get(column, "False")).strip().lower() in {"true", "1", "1.0"}
        ]
        symbol_bundle = grouped.get(symbol)
        symbol_candles = symbol_bundle[0] if symbol_bundle is not None else pd.DataFrame()
        signal_valid = (
            side in {"BUY", "SELL"}
            and np.isfinite(entry_price)
            and np.isfinite(tp_price)
            and np.isfinite(sl_price)
            and not symbol_candles.empty
        )
        base = {
            "Entry Time": entry_time,
            "Scheduled 24H Cap": horizon_end,
            "Symbol": symbol,
            "Side": side or "INVALID",
            "Entry Price": entry_price,
            "TP Price": tp_price,
            "SL Price": sl_price,
            "Spread Pips": spread,
            "Max Hold Hours": hold_cap,
            "Evaluation Version": VERSION,
            "Intrabar Ambiguity Policy": "SL_FIRST_CONSERVATIVE",
            "Hourly Entry Origin": str(signal.get("Hourly Entry Origin") or ""),
            "Strategy IDs": ",".join(strategy_ids),
            "S111-S120 Entry": any(111 <= int(value[1:]) <= 120 for value in strategy_ids),
            "Entry Middle Regime Bias": str(signal.get("Middle Regime Bias") or ""),
            "Preferred TP Horizon": str(signal.get("Preferred TP Horizon") or ""),
            "TP Target Horizon Hours": _number(signal, ("TP Target Horizon Hours", "Expected TP Hours")),
            "TP/SL Pair Quality Score": _number(signal, ("TP/SL Pair Quality Score",)),
            "Modeled SL Rebound To TP Rate": _number(signal, ("SL Rebound To TP Rate",)),
        }
        if not signal_valid:
            rows.append({
                **base, "Exit Time": pd.NaT, "Exit Price": np.nan,
                "Exit Reason": "INVALID_SIGNAL_OR_MISSING_CANDLE_STREAM", "Outcome": "INVALID",
                "Backtest Valid": False, "Full 24H Coverage": False,
                "Future Candles Used": 0, "Candle Gap Count": 0,
                "TP And SL Same Candle": False, "Middle Bias At Exit": "",
                "Post-SL Rebound To TP": False, "Post-SL Rebound Evaluated": False,
                "Gross Pips": np.nan, "Net Pips": np.nan,
                "Observed Mark-to-Market Pips": np.nan,
                "MFE Pips": np.nan, "MAE Pips": np.nan,
                "Max Floating Loss Pips": np.nan, "Hold Hours": np.nan,
            })
            continue

        symbol_times = symbol_bundle[1]
        start_position = int(symbol_times.searchsorted(entry_time, side="right"))
        end_position = int(symbol_times.searchsorted(horizon_end, side="right"))
        future = symbol_candles.iloc[start_position:end_position]
        data_complete_through = pd.Timestamp(symbol_times[-1])
        full_horizon = bool(data_complete_through >= horizon_end)
        timeline = pd.concat(
            [pd.Series([entry_time]), future["Datetime"]], ignore_index=True
        ).sort_values()
        gaps = int((timeline.diff().dt.total_seconds().div(3600).fillna(0) > 1.5).sum())
        favourable: list[float] = []
        adverse: list[float] = []
        exit_time: pd.Timestamp | Any = pd.NaT
        exit_price = float("nan")
        exit_reason = ""
        exit_bias = ""
        both_same_candle = False
        used_count = int(len(future))

        for candle_number, candle in enumerate(future.itertuples(index=False), start=1):
            timestamp = pd.Timestamp(candle[0])
            high = float(candle[3])
            low = float(candle[4])
            close = float(candle[5])
            if side == "BUY":
                favourable.append(max(0.0, (high - entry_price) / pip))
                adverse.append(max(0.0, (entry_price - low) / pip))
                tp_hit = high >= tp_price
                sl_hit = low <= sl_price
            else:
                favourable.append(max(0.0, (entry_price - low) / pip))
                adverse.append(max(0.0, (high - entry_price) / pip))
                tp_hit = low <= tp_price
                sl_hit = high >= sl_price
            current_bias = biases.get((symbol, timestamp), "")
            if tp_hit and sl_hit:
                both_same_candle = True
                exit_time, exit_price, exit_reason = timestamp, sl_price, "SL_HIT_AMBIGUOUS_CANDLE"
            elif sl_hit:
                exit_time, exit_price, exit_reason = timestamp, sl_price, "SL_HIT"
            elif tp_hit:
                exit_time, exit_price, exit_reason = timestamp, tp_price, "TP_HIT"
            elif current_bias and current_bias != side:
                exit_time, exit_price, exit_reason = timestamp, close, "MIDDLE_BIAS_EXIT"
                exit_bias = current_bias
            if exit_reason:
                used_count = candle_number
                break

        observed_price = float(future.iloc[-1]["Close Price"]) if not future.empty else entry_price
        observed_gross = ((observed_price - entry_price) / pip) * (1.0 if side == "BUY" else -1.0)
        post_sl_rebound = False
        post_sl_evaluated = bool(exit_reason.startswith("SL_"))
        if post_sl_evaluated and used_count < len(future):
            after_stop = future.iloc[used_count:]
            if side == "BUY":
                post_sl_rebound = bool(after_stop["High Price"].ge(tp_price).any())
            else:
                post_sl_rebound = bool(after_stop["Low Price"].le(tp_price).any())
        backtest_valid = bool(exit_reason)
        if not exit_reason and full_horizon and not future.empty:
            final = future.iloc[-1]
            exit_time = pd.Timestamp(final["Datetime"])
            exit_price = float(final["Close Price"])
            exit_reason = "24H_TIME_EXIT"
            backtest_valid = True
        elif not exit_reason:
            exit_reason = "INSUFFICIENT_FUTURE_DATA"

        if backtest_valid:
            gross_pips = ((exit_price - entry_price) / pip) * (1.0 if side == "BUY" else -1.0)
            net_pips = gross_pips - spread
            outcome = "WIN" if net_pips > 0 else "LOSS" if net_pips < 0 else "FLAT"
            hold_hours = (pd.Timestamp(exit_time) - entry_time).total_seconds() / 3600.0
        else:
            gross_pips = net_pips = hold_hours = float("nan")
            outcome = "INCOMPLETE"
        rows.append({
            **base,
            "Exit Time": exit_time,
            "Exit Price": exit_price,
            "Exit Reason": exit_reason,
            "Outcome": outcome,
            "Backtest Valid": backtest_valid,
            "Full 24H Coverage": full_horizon,
            "Data Complete Through": data_complete_through,
            "Future Candles Used": used_count,
            "Candle Gap Count": gaps,
            "TP And SL Same Candle": both_same_candle,
            "Post-SL Rebound To TP": post_sl_rebound,
            "Post-SL Rebound Evaluated": post_sl_evaluated,
            "Middle Bias At Exit": exit_bias,
            "Gross Pips": round(float(gross_pips), 3) if np.isfinite(gross_pips) else np.nan,
            "Net Pips": round(float(net_pips), 3) if np.isfinite(net_pips) else np.nan,
            "Observed Mark-to-Market Pips": round(float(observed_gross - spread), 3),
            "MFE Pips": round(max(favourable, default=0.0), 3),
            "MAE Pips": round(max(adverse, default=0.0), 3),
            "Max Floating Loss Pips": round(-max(adverse, default=0.0), 3),
            "Hold Hours": round(float(hold_hours), 3) if np.isfinite(hold_hours) else np.nan,
        })

    return pd.DataFrame(rows).sort_values(["Entry Time", "Symbol"], kind="mergesort").reset_index(drop=True)


def summarize_execution_backtest(trades: pd.DataFrame) -> dict[str, Any]:
    valid = trades.loc[trades.get("Backtest Valid", pd.Series(False, index=trades.index)).eq(True)].copy() if isinstance(trades, pd.DataFrame) else pd.DataFrame()
    net = pd.to_numeric(valid.get("Net Pips", pd.Series(dtype=float)), errors="coerce").dropna()
    if net.empty:
        max_drawdown = 0.0
    else:
        equity = net.cumsum()
        max_drawdown = float((equity - equity.cummax()).min())
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
        "tp_exit_pct": exit_pct("TP_HIT"),
        "sl_exit_pct": exit_pct("SL_HIT"),
        "middle_bias_exit_pct": exit_pct("MIDDLE_BIAS_EXIT"),
        "time_exit_24h_pct": exit_pct("24H_TIME_EXIT"),
        "tp_first_rate_pct": exit_pct("TP_HIT"),
        "sl_first_rate_pct": exit_pct("SL_HIT"),
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
        "s111_s120_additional_trades": int(
            valid.get("S111-S120 Entry", pd.Series(False, index=valid.index)).astype(bool).sum()
        ),
        "spread_pips_per_trade": DEFAULT_SPREAD_PIPS,
        "max_hold_hours": DEFAULT_MAX_HOLD_HOURS,
        "same_candle_tp_sl_policy": "SL_FIRST_CONSERVATIVE",
    }


def build_professional_backtest_bundle(
    signals: pd.DataFrame,
    candles: pd.DataFrame,
    *,
    finder_rows: pd.DataFrame,
    entry_start: Any,
    entry_end: Any,
    spread_pips: float = DEFAULT_SPREAD_PIPS,
    max_hold_hours: int = DEFAULT_MAX_HOLD_HOURS,
) -> tuple[bytes, pd.DataFrame, dict[str, Any]]:
    """Create one auditable ZIP containing signals, evidence, and outcomes."""
    start = pd.to_datetime(entry_start, errors="coerce", utc=True)
    end = pd.to_datetime(entry_end, errors="coerce", utc=True)
    selected = signals.copy()
    if "Hourly 4 Entry" in selected.columns:
        selected = selected.loc[_truthy(selected["Hourly 4 Entry"])].copy()
    signal_time_column = _first_column(selected, ("Datetime", "Completed Candle", "_FinderDatetime"))
    if signal_time_column:
        signal_times = pd.to_datetime(selected[signal_time_column], errors="coerce", utc=True)
        selected = selected.loc[signal_times.between(start, end, inclusive="both")].copy()
    trades = evaluate_execution_backtest(
        selected, candles, finder_rows=finder_rows,
        spread_pips=spread_pips, max_hold_hours=max_hold_hours,
    )
    summary = summarize_execution_backtest(trades)
    summary.update({
        "entry_start_utc": str(start),
        "entry_end_utc": str(end),
        "signal_rows": int(len(selected)),
        "candle_rows": int(len(candles)),
        "candle_symbols": int(candles["Symbol"].nunique()) if "Symbol" in candles else 0,
        "spread_pips_per_trade": float(spread_pips),
        "max_hold_hours": int(max_hold_hours),
    })

    candle_export = candles.copy()
    candle_time_column = _first_column(candle_export, ("Datetime", "Completed Candle", "open_time", "time"))
    if candle_time_column:
        candle_times = pd.to_datetime(candle_export[candle_time_column], errors="coerce", utc=True)
        candle_export["Backtest Candle Role"] = np.where(candle_times.le(end), "ENTRY_WINDOW", "FUTURE_24H_PADDING")
    bias_columns = [column for column in ("Datetime", "Completed Candle", "Symbol", "Timeframe", "Middle Regime Bias") if column in finder_rows.columns]
    bias_timeline = finder_rows.loc[:, bias_columns].copy() if bias_columns else pd.DataFrame()
    if not bias_timeline.empty:
        time_column = _first_column(bias_timeline, ("Datetime", "Completed Candle"))
        bias_timeline["Datetime"] = pd.to_datetime(bias_timeline[time_column], errors="coerce", utc=True)
        bias_timeline = bias_timeline.drop_duplicates(["Symbol", "Datetime"], keep="last").sort_values(["Datetime", "Symbol"])

    readme = f"""PROFESSIONAL EXECUTION BACKTEST BUNDLE

This bundle separates decisions from market evidence.

01_hourly_signals.csv
  Only the Finder-selected hourly entries (up to four symbols per hour).

02_all_symbol_candles.csv
  Every stored OHLC candle for every built symbol in the entry range, plus up
  to {max_hold_hours} future hours. Unselected symbols are intentionally kept.

03_middle_bias_timeline.csv
  The all-symbol Middle Bias timeline used to detect post-entry bias exits.

04_execution_backtest.csv
  TP, SL, Middle Bias, time-cap, MFE, MAE, floating-loss and net-pip results.

05_summary.json
  Aggregate results and the evaluation policy.

Rules
  - Entry uses the signal candle Close Price.
  - Only candles strictly after the entry can close the trade.
  - TP/SL use future High/Low. If both occur in one OHLC candle, SL wins
    conservatively because the true tick order is unknown.
  - A completed-candle Middle Bias loss exits at that candle's Close Price.
  - Remaining positions exit at the last available candle at/before {max_hold_hours}h.
  - {spread_pips:g} pips are deducted from each valid trade.
  - A tail without enough future data is INSUFFICIENT_FUTURE_DATA and has no
    realized Net Pips. No future candles or prices are fabricated.

Engine: {VERSION}
"""
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("01_hourly_signals.csv", selected.to_csv(index=False, encoding="utf-8"))
        archive.writestr("02_all_symbol_candles.csv", candle_export.to_csv(index=False, encoding="utf-8"))
        archive.writestr("03_middle_bias_timeline.csv", bias_timeline.to_csv(index=False, encoding="utf-8"))
        archive.writestr("04_execution_backtest.csv", trades.to_csv(index=False, encoding="utf-8"))
        archive.writestr("05_summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        archive.writestr("README.txt", readme)
    return output.getvalue(), trades, summary


__all__ = [
    "VERSION", "DEFAULT_SPREAD_PIPS", "DEFAULT_MAX_HOLD_HOURS",
    "evaluate_execution_backtest", "summarize_execution_backtest",
    "build_professional_backtest_bundle",
]
