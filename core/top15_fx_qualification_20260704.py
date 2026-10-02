"""Broker-observed Top-15 FX qualification.

No pair is assumed to have a low spread.  Selection is based on observations from
the connected broker account and excludes EURUSD, USDJPY and GBPUSD by contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import json
import math
import sqlite3
import time
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from core.multi_symbol_field10_20260701 import DB_PATH

VERSION = "top15-spread-qualification-20260704-v1"
EXCLUDED = frozenset({"EURUSD", "USDJPY", "GBPUSD"})
CANDIDATES = (
    "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURGBP", "EURCHF", "EURCAD",
    "EURAUD", "EURNZD", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD", "AUDCAD",
    "AUDNZD", "AUDCHF", "NZDCAD", "NZDCHF", "CADCHF", "EURSEK", "EURNOK",
    "GBPNOK", "GBPSEK", "CADJPY", "AUDJPY", "NZDJPY", "CHFJPY", "EURJPY",
    "GBPJPY",
)
LIQUIDITY_PRIOR = {symbol: max(0.25, 1.0 - i * 0.02) for i, symbol in enumerate(CANDIDATES)}


def normalize_broker_symbol(value: Any) -> str:
    clean = "".join(ch for ch in str(value or "").upper() if ch.isalpha())
    for symbol in sorted(set(CANDIDATES) | set(EXCLUDED), key=len, reverse=True):
        if symbol in clean:
            return symbol
    return clean[:6]


def _fingerprint(account: Mapping[str, Any] | None) -> str:
    account = account if isinstance(account, Mapping) else {}
    safe = {
        "server": str(account.get("server") or ""), "login_hash": sha256(str(account.get("login") or "").encode()).hexdigest()[:16],
        "currency": str(account.get("currency") or ""), "company": str(account.get("company") or ""),
    }
    return sha256(json.dumps(safe, sort_keys=True).encode()).hexdigest()


def migrate(path: Path | str = DB_PATH) -> None:
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS fx_spread_observation_20260704 (
            account_fingerprint TEXT NOT NULL,
            canonical_symbol TEXT NOT NULL,
            provider_symbol TEXT NOT NULL,
            spread_points REAL NOT NULL,
            observed_at TEXT NOT NULL,
            tradeable INTEGER NOT NULL,
            history_bars INTEGER NOT NULL DEFAULT 0,
            tick_volume_evidence INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(account_fingerprint,provider_symbol,observed_at)
        );
        CREATE INDEX IF NOT EXISTS idx_fx_spread_obs_symbol_time_20260704
            ON fx_spread_observation_20260704(account_fingerprint,canonical_symbol,observed_at DESC);
        CREATE TABLE IF NOT EXISTS fx_top15_qualification_20260704 (
            account_fingerprint TEXT NOT NULL,
            canonical_symbol TEXT NOT NULL,
            provider_symbol TEXT NOT NULL,
            rank INTEGER,
            qualified INTEGER NOT NULL,
            current_spread REAL,
            median_spread REAL,
            p95_spread REAL,
            observation_count INTEGER NOT NULL,
            spread_freshness_seconds REAL,
            history_bars INTEGER NOT NULL,
            tick_volume_evidence INTEGER NOT NULL,
            quality_score REAL NOT NULL,
            reason TEXT NOT NULL,
            evaluated_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            version TEXT NOT NULL,
            PRIMARY KEY(account_fingerprint,canonical_symbol)
        );
        """)
        conn.commit()


def qualify_from_observations(
    observations: pd.DataFrame, *, account: Mapping[str, Any] | None = None,
    maximum_median_spread: float = 20.0, minimum_observations: int = 1,
    now: pd.Timestamp | None = None, ttl_seconds: int = 3600,
) -> pd.DataFrame:
    now = pd.Timestamp.now(tz="UTC") if now is None else pd.Timestamp(now)
    if now.tzinfo is None: now = now.tz_localize("UTC")
    required = {"provider_symbol", "spread_points"}
    if not isinstance(observations, pd.DataFrame) or not required.issubset(observations.columns):
        return pd.DataFrame()
    work = observations.copy()
    work["canonical_symbol"] = work.get("canonical_symbol", work["provider_symbol"]).map(normalize_broker_symbol)
    work = work[~work["canonical_symbol"].isin(EXCLUDED) & work["canonical_symbol"].isin(CANDIDATES)]
    work["spread_points"] = pd.to_numeric(work["spread_points"], errors="coerce")
    work["observed_at"] = pd.to_datetime(work.get("observed_at", now), errors="coerce", utc=True)
    work["tradeable"] = work.get("tradeable", True).fillna(False).astype(bool)
    work["history_bars"] = pd.to_numeric(work.get("history_bars", 0), errors="coerce").fillna(0).astype(int)
    work["tick_volume_evidence"] = pd.to_numeric(work.get("tick_volume_evidence", 0), errors="coerce").fillna(0).astype(int)
    work = work.dropna(subset=["spread_points", "observed_at"])
    rows = []
    for symbol, group in work.groupby("canonical_symbol", sort=False):
        group = group.sort_values("observed_at").tail(200)
        spreads = group["spread_points"].astype(float)
        current = float(spreads.iloc[-1])
        median = float(spreads.median())
        p95 = float(spreads.quantile(0.95))
        count = int(len(spreads))
        latest = pd.Timestamp(group["observed_at"].iloc[-1])
        freshness = max(0.0, (now - latest).total_seconds())
        tradeable = bool(group["tradeable"].iloc[-1])
        bars = int(group["history_bars"].max())
        volume = int(group["tick_volume_evidence"].max())
        qualified = tradeable and count >= minimum_observations and median <= maximum_median_spread and freshness <= ttl_seconds
        spread_quality = float(np.clip(1.0 - median / max(maximum_median_spread * 1.5, 1), 0, 1))
        stability = float(np.clip(1.0 - max(0.0, p95 - median) / max(maximum_median_spread, 1), 0, 1))
        data_quality = min(1.0, bars / 600.0) * 0.7 + min(1.0, volume / 300.0) * 0.3
        score = 100 * (0.35 * LIQUIDITY_PRIOR.get(symbol, 0.3) + 0.30 * spread_quality + 0.20 * stability + 0.15 * data_quality)
        reasons = []
        if not tradeable: reasons.append("broker_symbol_not_tradeable")
        if count < minimum_observations: reasons.append("insufficient_spread_observations")
        if median > maximum_median_spread: reasons.append("rolling_median_spread_above_20_points")
        if freshness > ttl_seconds: reasons.append("spread_observation_stale")
        rows.append({
            "canonical_symbol": symbol, "provider_symbol": str(group["provider_symbol"].iloc[-1]),
            "qualified": qualified, "current_spread": current, "median_spread": median,
            "p95_spread": p95, "observation_count": count, "spread_freshness_seconds": freshness,
            "history_bars": bars, "tick_volume_evidence": volume, "quality_score": round(score, 6),
            "reason": ";".join(reasons) if reasons else "QUALIFIED_BY_BROKER_OBSERVATIONS",
            "evaluated_at": now.isoformat(), "expires_at": (now + pd.Timedelta(seconds=ttl_seconds)).isoformat(),
        })
    result = pd.DataFrame(rows)
    if result.empty: return result
    result = result.sort_values(["qualified", "quality_score", "median_spread"], ascending=[False, False, True], kind="mergesort")
    result["rank"] = np.where(result["qualified"], np.arange(1, len(result)+1), np.nan)
    qualified_index = result.index[result["qualified"]]
    result.loc[qualified_index, "rank"] = np.arange(1, len(qualified_index)+1)
    result.loc[~result["qualified"], "rank"] = np.nan
    return result.reset_index(drop=True)


def persist_qualification(result: pd.DataFrame, *, account: Mapping[str, Any] | None = None,
                          path: Path | str = DB_PATH) -> dict[str, Any]:
    migrate(path)
    fp = _fingerprint(account)
    if result.empty:
        return {"ok": False, "qualified_count": 0, "account_fingerprint": fp, "version": VERSION}
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=8000"); conn.execute("BEGIN IMMEDIATE")
        for row in result.to_dict("records"):
            conn.execute("""INSERT OR REPLACE INTO fx_top15_qualification_20260704(
                account_fingerprint,canonical_symbol,provider_symbol,rank,qualified,current_spread,
                median_spread,p95_spread,observation_count,spread_freshness_seconds,history_bars,
                tick_volume_evidence,quality_score,reason,evaluated_at,expires_at,version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                fp, row["canonical_symbol"], row["provider_symbol"], None if pd.isna(row["rank"]) else int(row["rank"]),
                int(bool(row["qualified"])), row["current_spread"], row["median_spread"], row["p95_spread"],
                int(row["observation_count"]), row["spread_freshness_seconds"], int(row["history_bars"]),
                int(row["tick_volume_evidence"]), row["quality_score"], row["reason"], row["evaluated_at"],
                row["expires_at"], VERSION,
            ))
        conn.commit()
    selected = result.loc[result["qualified"]].sort_values("rank").head(15)["canonical_symbol"].tolist()
    return {"ok": True, "qualified_count": len(selected), "selected": selected, "account_fingerprint": fp, "version": VERSION}


def qualify_mt5_top15(*, path: Path | str = DB_PATH, maximum_median_spread: float = 20.0) -> dict[str, Any]:
    """Observe current MT5 account symbols. Returns Plan-B evidence when MT5 is unavailable."""
    try:
        import MetaTrader5 as mt5  # type: ignore
    except Exception as exc:
        return {"ok": False, "status": "MT5_LIBRARY_UNAVAILABLE", "qualified_count": 0, "error": type(exc).__name__, "version": VERSION}
    if not mt5.initialize():
        return {"ok": False, "status": "MT5_NOT_CONNECTED", "qualified_count": 0, "version": VERSION}
    account_info = mt5.account_info()
    account = account_info._asdict() if account_info is not None and hasattr(account_info, "_asdict") else {}
    available = list(mt5.symbols_get() or [])
    rows = []
    now = pd.Timestamp.now(tz="UTC")
    for canonical in CANDIDATES:
        matches = [info for info in available if normalize_broker_symbol(getattr(info, "name", "")) == canonical]
        if not matches: continue
        info = sorted(matches, key=lambda x: (not bool(getattr(x, "visible", False)), len(str(getattr(x, "name", "")))))[0]
        name = str(getattr(info, "name", canonical))
        tick = mt5.symbol_info_tick(name)
        point = float(getattr(info, "point", 0.0) or 0.0)
        bid, ask = float(getattr(tick, "bid", 0.0) or 0.0), float(getattr(tick, "ask", 0.0) or 0.0)
        spread = (ask - bid) / point if point > 0 and ask > 0 and bid > 0 else float(getattr(info, "spread", np.nan))
        rates = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H1, 1, 600)
        history_bars = 0 if rates is None else len(rates)
        volume_count = 0 if rates is None or "tick_volume" not in rates.dtype.names else int(np.count_nonzero(rates["tick_volume"]))
        rows.append({"canonical_symbol": canonical, "provider_symbol": name, "spread_points": spread,
                     "observed_at": now, "tradeable": int(getattr(info, "trade_mode", 0)) != 0,
                     "history_bars": history_bars, "tick_volume_evidence": volume_count})
    observations = pd.DataFrame(rows)
    migrate(path)
    fp = _fingerprint(account)
    if not observations.empty:
        with sqlite3.connect(str(path), timeout=30) as conn:
            for row in observations.dropna(subset=["spread_points"]).to_dict("records"):
                conn.execute("INSERT OR REPLACE INTO fx_spread_observation_20260704 VALUES(?,?,?,?,?,?,?,?)", (
                    fp, row["canonical_symbol"], row["provider_symbol"], float(row["spread_points"]),
                    pd.Timestamp(row["observed_at"]).isoformat(), int(bool(row["tradeable"])),
                    int(row["history_bars"]), int(row["tick_volume_evidence"])))
            history = pd.read_sql_query("SELECT provider_symbol,canonical_symbol,spread_points,observed_at,tradeable,history_bars,tick_volume_evidence FROM fx_spread_observation_20260704 WHERE account_fingerprint=?", conn, params=(fp,))
            conn.commit()
    else:
        history = observations
    result = qualify_from_observations(history, account=account, maximum_median_spread=maximum_median_spread, now=now)
    report = persist_qualification(result, account=account, path=path)
    report["status"] = "QUALIFIED" if report["qualified_count"] >= 15 else "FEWER_THAN_15_QUALIFIED"
    report["table"] = result
    return report


__all__ = ["VERSION", "EXCLUDED", "CANDIDATES", "normalize_broker_symbol", "qualify_from_observations", "persist_qualification", "qualify_mt5_top15"]
