"""Lightweight causal Morning risk analytics for Quant Research V8.

All calculations are bounded, vectorized and advisory. Missing account/execution
inputs remain explicitly unavailable; no value is invented and no order sizing is
changed automatically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
import math
import numpy as np
import pandas as pd

VERSION = "morning-quant-metrics-v8-20260622"
MAX_HISTORY_ROWS = 5000


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _number(mapping: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in mapping:
            value = _finite(mapping.get(key))
            if value is not None:
                return value
    return None


def _series(values: Any, *, limit: int = MAX_HISTORY_ROWS) -> pd.Series:
    if isinstance(values, pd.Series):
        out = values
    elif isinstance(values, pd.DataFrame):
        candidate = next((c for c in ("return", "returns", "profit", "pnl", "equity", "close") if c in values.columns), None)
        out = values[candidate] if candidate else pd.Series(dtype=float)
    else:
        out = pd.Series(values if values is not None else [], dtype=float)
    return pd.to_numeric(out, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().tail(limit)


def historical_expected_shortfall(returns: Any, confidence: float, *, limit: int = MAX_HISTORY_ROWS) -> dict[str, Any]:
    r = _series(returns, limit=limit)
    if len(r) < 30:
        return {"status": "UNAVAILABLE", "value": None, "sample_count": int(len(r)), "reason": "minimum 30 settled returns required"}
    confidence = float(min(0.999, max(0.5, confidence)))
    threshold = float(r.quantile(1.0 - confidence, interpolation="higher"))
    tail = r[r <= threshold]
    value = float(-tail.mean()) if len(tail) else float(-threshold)
    return {"status": "AVAILABLE", "value": max(0.0, value), "sample_count": int(len(r)), "threshold": threshold}


def ewma_volatility(returns: Any, *, span: int) -> dict[str, Any]:
    r = _series(returns)
    if len(r) < max(8, span // 2):
        return {"status": "UNAVAILABLE", "value": None, "sample_count": int(len(r))}
    variance = r.pow(2).ewm(span=max(2, int(span)), adjust=False).mean().iloc[-1]
    return {"status": "AVAILABLE", "value": float(math.sqrt(max(0.0, variance))), "sample_count": int(len(r)), "span": int(span)}


def drawdown_statistics(equity_history: Any) -> dict[str, Any]:
    eq = _series(equity_history)
    if len(eq) < 2 or not (eq > 0).any():
        return {"status": "UNAVAILABLE", "current_drawdown_pct": None, "maximum_drawdown_pct": None, "drawdown_duration": None, "time_under_water_pct": None}
    peak = eq.cummax().replace(0, np.nan)
    dd = (eq / peak - 1.0).fillna(0.0)
    underwater = dd < -1e-12
    duration = 0
    max_duration = 0
    for flag in underwater.to_numpy(dtype=bool):
        duration = duration + 1 if flag else 0
        max_duration = max(max_duration, duration)
    return {
        "status": "AVAILABLE",
        "current_drawdown_pct": float(max(0.0, -dd.iloc[-1] * 100.0)),
        "maximum_drawdown_pct": float(max(0.0, -dd.min() * 100.0)),
        "drawdown_duration": int(duration),
        "maximum_drawdown_duration": int(max_duration),
        "time_under_water_pct": float(underwater.mean() * 100.0),
        "sample_count": int(len(eq)),
    }


def _normalized_positions(positions: Any) -> pd.DataFrame:
    if isinstance(positions, pd.DataFrame):
        out = positions.copy(deep=False)
    elif isinstance(positions, (list, tuple)):
        out = pd.DataFrame(list(positions))
    else:
        out = pd.DataFrame()
    if out.empty:
        return out
    aliases = {
        "side": ("side", "type", "direction"), "lots": ("lots", "volume", "lot"),
        "entry_price": ("entry_price", "price_open", "open_price"), "current_price": ("current_price", "price_current", "price"),
        "symbol": ("symbol",), "unrealized_profit": ("unrealized_profit", "profit", "pnl"),
        "stop_distance": ("stop_distance", "sl_distance", "stop_loss_distance"),
    }
    norm: dict[str, Any] = {}
    lower = {str(c).lower(): c for c in out.columns}
    for target, names in aliases.items():
        hit = next((lower[n] for n in names if n in lower), None)
        norm[target] = out[hit] if hit is not None else np.nan
    result = pd.DataFrame(norm)
    result["side"] = result["side"].astype(str).str.upper().replace({"0": "BUY", "1": "SELL", "POSITION_TYPE_BUY": "BUY", "POSITION_TYPE_SELL": "SELL"})
    for col in ("lots", "entry_price", "current_price", "unrealized_profit", "stop_distance"):
        result[col] = pd.to_numeric(result[col], errors="coerce")
    result["symbol"] = result["symbol"].astype(str)
    return result


def exposure_statistics(positions: Any, *, contract_size_default: float = 100000.0) -> dict[str, Any]:
    p = _normalized_positions(positions)
    if p.empty:
        return {"status": "AVAILABLE", "open_position_count": 0, "buy_exposure": 0.0, "sell_exposure": 0.0, "net_exposure": 0.0, "concentration": 0.0, "imbalance": 0.0, "by_symbol": {}}
    price = p["current_price"].fillna(p["entry_price"]).fillna(0.0).abs()
    p = p.assign(notional=p["lots"].fillna(0.0).abs() * price * float(contract_size_default))
    buy = float(p.loc[p.side.eq("BUY"), "notional"].sum())
    sell = float(p.loc[p.side.eq("SELL"), "notional"].sum())
    gross = buy + sell
    by_symbol = p.groupby("symbol", dropna=False)["notional"].sum().sort_values(ascending=False)
    concentration = float(by_symbol.iloc[0] / gross) if gross > 0 and len(by_symbol) else 0.0
    return {
        "status": "AVAILABLE", "open_position_count": int(len(p)), "buy_exposure": buy, "sell_exposure": sell,
        "net_exposure": buy - sell, "gross_exposure": gross, "concentration": concentration,
        "imbalance": float((buy - sell) / gross) if gross > 0 else 0.0,
        "by_symbol": {str(k): float(v) for k, v in by_symbol.items()},
    }


def risk_budget(account: Mapping[str, Any], *, risk_per_trade_pct: float | None = None, planned_trade_count: int | None = None, used_daily_risk: float | None = None) -> dict[str, Any]:
    balance = _number(account, "balance")
    if balance is None or balance <= 0 or risk_per_trade_pct is None or planned_trade_count is None:
        return {"status": "UNAVAILABLE", "planned_total_risk": None, "remaining_daily_risk": None, "utilization_pct": None, "reason": "balance, risk per trade and planned trade count are required"}
    planned = balance * max(0.0, float(risk_per_trade_pct)) / 100.0 * max(0, int(planned_trade_count))
    used = max(0.0, float(used_daily_risk or 0.0))
    return {"status": "AVAILABLE", "risk_per_trade": balance * float(risk_per_trade_pct) / 100.0, "planned_total_risk": planned, "used_daily_risk": used, "remaining_daily_risk": max(0.0, planned - used), "utilization_pct": min(999.0, used / planned * 100.0) if planned > 0 else 0.0}


def atr_stress(positions: Any, atr: float | None, *, point_value_per_lot: float | None = None) -> dict[str, Any]:
    p = _normalized_positions(positions)
    atr_value = _finite(atr)
    if p.empty:
        return {"status": "AVAILABLE", "stress_1atr": 0.0, "stress_2atr": 0.0, "stress_3atr": 0.0}
    if atr_value is None or atr_value <= 0:
        return {"status": "UNAVAILABLE", "stress_1atr": None, "stress_2atr": None, "stress_3atr": None, "reason": "positive ATR required"}
    multiplier = float(point_value_per_lot) if _finite(point_value_per_lot) is not None else 100000.0
    base = float((p["lots"].fillna(0).abs() * atr_value * multiplier).sum())
    return {"status": "AVAILABLE", "stress_1atr": base, "stress_2atr": 2.0 * base, "stress_3atr": 3.0 * base, "assumption": "adverse move applied to gross lots; advisory only"}


def execution_health(history: Any) -> dict[str, Any]:
    h = history.copy(deep=False).tail(MAX_HISTORY_ROWS) if isinstance(history, pd.DataFrame) else pd.DataFrame()
    if h.empty:
        return {"status": "UNAVAILABLE", "spread_percentile": None, "slippage_percentile": None, "latency_ms_p95": None, "failure_rate": None}
    def percentile(column: str, q: float = 0.95) -> float | None:
        if column not in h:
            return None
        s = pd.to_numeric(h[column], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        return float(s.quantile(q)) if len(s) else None
    failures = None
    if "connection_status" in h:
        failures = float(~h["connection_status"].astype(str).str.upper().isin({"OK", "CONNECTED", "SUCCESS", "READY"})).mean()
    elif "failure_type" in h:
        failures = float(h["failure_type"].notna().mean())
    return {"status": "AVAILABLE", "spread_percentile": percentile("spread"), "slippage_percentile": percentile("slippage"), "latency_ms_p95": percentile("fetch_duration_ms"), "failure_rate": failures, "sample_count": int(len(h))}


def capped_fractional_kelly(settled_trade_returns: Any, *, minimum_samples: int = 50, cap: float = 0.25) -> dict[str, Any]:
    r = _series(settled_trade_returns)
    if len(r) < int(minimum_samples):
        return {"status": "INSUFFICIENT_EVIDENCE", "fractional_kelly": None, "sample_count": int(len(r)), "shadow_only": True}
    wins = r[r > 0]; losses = -r[r < 0]
    if len(wins) == 0 or len(losses) == 0 or losses.mean() <= 0:
        raw = 0.0
    else:
        p = float((r > 0).mean()); b = float(wins.mean() / losses.mean())
        raw = max(0.0, p - (1.0 - p) / max(b, 1e-12))
    return {"status": "AVAILABLE", "raw_kelly": raw, "fractional_kelly": min(float(cap), 0.25 * raw), "maximum_allowed": min(float(cap), 0.25), "sample_count": int(len(r)), "shadow_only": True, "automatic_position_change": False}


def empirical_risk_of_ruin_proxy(drawdown: Mapping[str, Any], risk: Mapping[str, Any], es99: Mapping[str, Any]) -> dict[str, Any]:
    dd = _finite(drawdown.get("current_drawdown_pct")) or 0.0
    util = _finite(risk.get("utilization_pct")) or 0.0
    es = _finite(es99.get("value")) or 0.0
    score = min(100.0, 0.45 * dd + 0.35 * min(util, 100.0) + 20.0 * min(es, 1.0))
    return {"status": "AVAILABLE", "proxy_pct": score, "label": "EMPIRICAL PROXY — NOT A BANKRUPTCY PROBABILITY"}


def build_morning_metrics(
    *, account: Mapping[str, Any] | None, positions: Any = None, returns: Any = None,
    equity_history: Any = None, atr: float | None = None, execution_history: Any = None,
    risk_per_trade_pct: float | None = None, planned_trade_count: int | None = None,
    used_daily_risk: float | None = None,
) -> dict[str, Any]:
    account = dict(account or {})
    exposure = exposure_statistics(positions if positions is not None else account.get("positions"))
    drawdown = drawdown_statistics(equity_history if equity_history is not None else [account.get("balance"), account.get("equity")])
    es95 = historical_expected_shortfall(returns, .95)
    es99 = historical_expected_shortfall(returns, .99)
    risk = risk_budget(account, risk_per_trade_pct=risk_per_trade_pct, planned_trade_count=planned_trade_count, used_daily_risk=used_daily_risk)
    stress = atr_stress(positions if positions is not None else account.get("positions"), atr)
    output = {
        "version": VERSION,
        "account": {
            "balance": _number(account, "balance"), "equity": _number(account, "equity"),
            "floating_profit": _number(account, "profit", "floating_profit", "floating"),
            "used_margin": _number(account, "margin", "used_margin"),
            "free_margin": _number(account, "margin_free", "free_margin"),
            "margin_level": _number(account, "margin_level"),
        },
        "exposure": exposure, "drawdown": drawdown, "risk_budget": risk, "stress": stress,
        "expected_shortfall_95": es95, "expected_shortfall_99": es99,
        "ewma_volatility": {"1h": ewma_volatility(returns, span=24), "6h": ewma_volatility(returns, span=72), "24h": ewma_volatility(returns, span=168)},
        "execution_health": execution_health(execution_history),
        "kelly_shadow": capped_fractional_kelly(returns),
    }
    output["risk_of_ruin_proxy"] = empirical_risk_of_ruin_proxy(drawdown, risk, es99)
    return output


__all__ = ["VERSION", "historical_expected_shortfall", "ewma_volatility", "drawdown_statistics", "exposure_statistics", "risk_budget", "atr_stress", "execution_health", "capped_fractional_kelly", "empirical_risk_of_ruin_proxy", "build_morning_metrics"]
