"""Bounded, secret-free multi-symbol market-data request router.

The router wraps the existing ``manual_connect`` provider session.  It never
stores credentials, bridge tokens or raw endpoints in its cache/report.  The
cache identity is provider + canonical/provider symbol + timeframe + candle
count + completed H1 candle + the project's existing composite profile
fingerprint.
"""
from __future__ import annotations
from core.global_symbol_compat import set_legacy_calculation_symbol

from collections.abc import Mapping, MutableMapping
from hashlib import sha256
from typing import Any
import io
import json
import sqlite3
import time
from pathlib import Path

import pandas as pd

from core.sqlite_readonly_20260704 import connect_readonly

VERSION = "multi-symbol-api-runtime-20260704-v2"
CACHE_KEY = "multi_symbol_api_frame_cache_20260702"
AUDIT_KEY = "multi_symbol_api_dedup_audit_20260702"


def _clean(value: Any) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum() or ch in {"_", "-", "."})


def _profile(state: Mapping[str, Any]) -> Mapping[str, Any]:
    value = state.get("market_connector_saved_profile_20260702")
    return value if isinstance(value, Mapping) else {}


def _frame_time(frame: pd.DataFrame, timeframe: str = "H4") -> pd.Timestamp:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.NaT
    for column in ("time", "datetime", "timestamp", "Broker Candle Time"):
        if column in frame.columns:
            parsed = pd.to_datetime(frame[column], errors="coerce", utc=True).dropna()
            if not parsed.empty:
                return _floor_to_timeframe(pd.Timestamp(parsed.max()), timeframe)
    if isinstance(frame.index, pd.DatetimeIndex):
        parsed = pd.to_datetime(frame.index, errors="coerce", utc=True)
        if len(parsed):
            return _floor_to_timeframe(pd.Timestamp(parsed.max()), timeframe)
    return pd.NaT



def _floor_to_timeframe(value: pd.Timestamp, timeframe: str) -> pd.Timestamp:
    tf = str(timeframe or "H4").upper()
    rule = {"M1":"min", "M5":"5min", "M15":"15min", "M30":"30min", "H1":"h", "H4":"4h", "D1":"D"}.get(tf, "h")
    return pd.Timestamp(value).floor(rule)

def completed_h1_identity(state: Mapping[str, Any]) -> str:
    timeframe = str(state.get("timeframe") or state.get("selected_timeframe") or "H4").upper()
    for key in (
        "canonical_decision_result_20260617", "canonical_result_20260617",
        "last_valid_canonical_decision_result_20260617",
    ):
        canonical = state.get(key)
        if isinstance(canonical, Mapping):
            value = (
                canonical.get("completed_broker_candle") or canonical.get("broker_candle_time")
                or canonical.get("latest_completed_candle_time")
            )
            parsed = pd.to_datetime(value, errors="coerce", utc=True)
            if pd.notna(parsed):
                return _floor_to_timeframe(pd.Timestamp(parsed), timeframe).isoformat()
    parsed = _frame_time(state.get("last_df"), timeframe)
    return parsed.isoformat() if pd.notna(parsed) else f"UNRESOLVED_COMPLETED_{timeframe}"


def build_request_key(
    *, provider: str, canonical_symbol: str, provider_alias: str, timeframe: str,
    candle_count: int, completed_h1_candle: str, profile_fingerprint: str,
) -> str:
    material = "|".join((
        _clean(provider), _clean(canonical_symbol), _clean(provider_alias),
        _clean(timeframe), str(int(candle_count)), str(completed_h1_candle),
        str(profile_fingerprint or "NO_PROFILE_FINGERPRINT"),
    ))
    return sha256(material.encode("utf-8")).hexdigest()


def classify_provider_failure(message: Any, source: Any = "") -> dict[str, Any]:
    text = f"{source} {message}".upper()
    if any(token in text for token in ("401", "403", "AUTH", "API KEY", "UNAUTHORIZED", "FORBIDDEN")):
        return {"category": "AUTHENTICATION", "retryable": False}
    if any(token in text for token in ("INVALID SYMBOL", "SYMBOL NOT FOUND", "UNKNOWN SYMBOL", "BAD SYMBOL")):
        return {"category": "INVALID_SYMBOL", "retryable": False}
    if any(token in text for token in ("QUOTA", "RATE LIMIT EXCEEDED", "429", "CREDITS EXCEEDED")):
        return {"category": "QUOTA_EXHAUSTED", "retryable": False}
    if any(token in text for token in ("408", "425", "500", "502", "503", "504", "TIMEOUT", "TEMPORARY", "CONNECTION RESET")):
        return {"category": "TEMPORARY_PROVIDER_FAILURE", "retryable": True}
    return {"category": "PROVIDER_FAILURE", "retryable": False}


def connection_profile_reusable(previous: Mapping[str, Any] | None, current: Mapping[str, Any] | None) -> bool:
    """Reuse is allowed only for the unchanged existing composite fingerprint."""
    previous = previous if isinstance(previous, Mapping) else {}
    current = current if isinstance(current, Mapping) else {}
    old = str(previous.get("signature") or "")
    new = str(current.get("signature") or "")
    return bool(old and new and old == new)


def _runtime_db_path() -> Path:
    try:
        from core.multi_symbol_field10_20260701 import DB_PATH
        return Path(DB_PATH)
    except Exception:
        return Path(__file__).resolve().parents[1] / "data" / "multi_symbol_field10_20260701.sqlite3"


def migrate_api_runtime(path: Path | str | None = None) -> None:
    path = Path(path or _runtime_db_path()); path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=8000")
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS market_data_candle_cache_20260704 (
            request_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            canonical_symbol TEXT NOT NULL,
            provider_symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            completed_broker_candle TEXT NOT NULL,
            requested_bar_count INTEGER NOT NULL,
            adjusted_status TEXT NOT NULL,
            provider_profile_fingerprint TEXT NOT NULL,
            source TEXT NOT NULL,
            frame_json TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            stored_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_market_cache_identity_20260704
          ON market_data_candle_cache_20260704(provider,canonical_symbol,timeframe,completed_broker_candle);
        CREATE TABLE IF NOT EXISTS api_request_audit_20260704 (
            request_id TEXT PRIMARY KEY,
            parent_run_id TEXT,
            provider TEXT NOT NULL,
            endpoint_category TEXT NOT NULL,
            symbol_count INTEGER NOT NULL,
            requested_symbols_hash TEXT NOT NULL,
            credits_used REAL,
            credits_left REAL,
            cache_hit INTEGER NOT NULL,
            deduplicated INTEGER NOT NULL,
            response_status TEXT NOT NULL,
            completed_h1_identity TEXT NOT NULL,
            requested_at TEXT NOT NULL,
            duration_ms REAL NOT NULL,
            retry_count INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_api_audit_parent_provider_20260704
          ON api_request_audit_20260704(parent_run_id,provider,requested_at);
        CREATE TABLE IF NOT EXISTS shared_news_cache_20260704 (
            cache_key TEXT PRIMARY KEY,
            provider TEXT NOT NULL,
            normalized_url TEXT,
            headline_hash TEXT NOT NULL,
            headline TEXT NOT NULL,
            published_at TEXT,
            source TEXT,
            payload_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            stored_at TEXT NOT NULL
        );
        """)
        conn.commit()


def _persistent_get(request_key: str, path: Path | str | None = None) -> tuple[pd.DataFrame | None, str]:
    try:
        migrate_api_runtime(path)
        with sqlite3.connect(str(path or _runtime_db_path()), timeout=30) as conn:
            row = conn.execute("SELECT frame_json,source FROM market_data_candle_cache_20260704 WHERE request_key=?", (request_key,)).fetchone()
        if not row:
            return None, ""
        frame = pd.read_json(io.StringIO(str(row[0])), orient="split")
        for column in ("time", "datetime", "timestamp", "Broker Candle Time"):
            if column in frame.columns:
                frame[column] = pd.to_datetime(frame[column], errors="coerce", utc=True)
        return (frame if not frame.empty else None), str(row[1] or "PERSISTENT_EXACT_CANDLE_CACHE")
    except Exception:
        return None, ""


def _persistent_put(request_key: str, frame: pd.DataFrame, *, provider: str, canonical_symbol: str,
                    provider_alias: str, timeframe: str, completed: str, candle_count: int,
                    profile_fingerprint: str, source: str, path: Path | str | None = None) -> None:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return
    migrate_api_runtime(path)
    payload = frame.to_json(orient="split", date_format="iso")
    with sqlite3.connect(str(path or _runtime_db_path()), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=8000")
        conn.execute("""INSERT OR REPLACE INTO market_data_candle_cache_20260704(
            request_key,provider,canonical_symbol,provider_symbol,timeframe,completed_broker_candle,
            requested_bar_count,adjusted_status,provider_profile_fingerprint,source,frame_json,row_count,stored_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            request_key, _clean(provider), _clean(canonical_symbol), _clean(provider_alias), _clean(timeframe),
            completed, int(candle_count), "RAW_OR_PROVIDER_DEFINED", sha256(str(profile_fingerprint).encode()).hexdigest(),
            str(source or "UNKNOWN"), payload, int(len(frame)), pd.Timestamp.now(tz="UTC").isoformat(),
        ))
        conn.commit()


def twelve_token_bucket_acquire(state: MutableMapping[str, Any], *, credits: float = 1.0,
                                capacity: float = 3.0, usable_capacity: float = 2.0,
                                refill_per_minute: float = 2.0) -> dict[str, Any]:
    """Reserve one credit and target at most two Twelve Data credits per minute."""
    key = "twelve_token_bucket_20260704"
    now = time.monotonic()
    bucket = state.get(key) if isinstance(state.get(key), Mapping) else {}
    tokens = float(bucket.get("tokens", usable_capacity))
    last = float(bucket.get("last", now))
    tokens = min(usable_capacity, tokens + max(0.0, now-last) * refill_per_minute / 60.0)
    allowed = tokens >= credits
    if allowed: tokens -= credits
    state[key] = {"tokens": tokens, "last": now, "capacity": capacity,
                  "usable_capacity": usable_capacity, "safety_reserve": max(0.0, capacity-usable_capacity)}
    return {"allowed": allowed, "tokens_left": round(tokens, 6), "cooldown_seconds": 0.0 if allowed else round((credits-tokens)*60/refill_per_minute, 3)}


def _audit_request(*, request_key: str, state: Mapping[str, Any], provider: str, symbol: str,
                   cache_hit: bool, deduplicated: bool, response_status: str, completed: str,
                   duration_ms: float, retry_count: int, credits_used: float | None = None,
                   credits_left: float | None = None, path: Path | str | None = None) -> None:
    try:
        migrate_api_runtime(path)
        requested_at = pd.Timestamp.now(tz="UTC").isoformat()
        request_id = sha256(f"{request_key}|{requested_at}|{response_status}".encode()).hexdigest()
        parent = str(state.get("multi_symbol_parent_run_id_20260701") or state.get("parent_run_id") or "")
        with sqlite3.connect(str(path or _runtime_db_path()), timeout=30) as conn:
            conn.execute("""INSERT OR REPLACE INTO api_request_audit_20260704(
                request_id,parent_run_id,provider,endpoint_category,symbol_count,requested_symbols_hash,
                credits_used,credits_left,cache_hit,deduplicated,response_status,completed_h1_identity,
                requested_at,duration_ms,retry_count) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                request_id, parent, _clean(provider), "H1_OHLC", 1, sha256(_clean(symbol).encode()).hexdigest(),
                credits_used, credits_left, int(cache_hit), int(deduplicated), str(response_status), str(completed),
                requested_at, float(duration_ms), int(retry_count),
            ))
            conn.commit()
    except Exception:
        pass


def cache_shared_news_items(items: list[Mapping[str, Any]], *, ttl_seconds: int = 1800,
                            provider: str = "FINNHUB", path: Path | str | None = None) -> dict[str, Any]:
    """Persist one shared macro/news pool and deduplicate it locally.

    The function performs no network request. Callers fetch once per TTL, then map
    the returned shared records to any number of symbols.
    """
    import re
    migrate_api_runtime(path)
    now = pd.Timestamp.now(tz="UTC")
    kept: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_headlines: set[str] = set()
    for item in items or []:
        headline = " ".join(str(item.get("headline") or item.get("title") or "").split())
        if not headline:
            continue
        url = str(item.get("url") or item.get("link") or "").strip().lower().split("?")[0]
        normalized_headline = re.sub(r"[^a-z0-9 ]+", "", headline.lower())
        hhash = sha256(normalized_headline.encode()).hexdigest()
        if (url and url in seen_urls) or hhash in seen_headlines:
            continue
        seen_urls.add(url); seen_headlines.add(hhash)
        payload = dict(item)
        kept.append({"url": url, "headline": headline, "headline_hash": hhash, "payload": payload})
    with sqlite3.connect(str(path or _runtime_db_path()), timeout=30) as conn:
        conn.execute("PRAGMA journal_mode=WAL"); conn.execute("PRAGMA busy_timeout=8000")
        for row in kept:
            cache_key = sha256(f"{provider}|{row['url']}|{row['headline_hash']}".encode()).hexdigest()
            published = row["payload"].get("datetime") or row["payload"].get("published_at") or row["payload"].get("time")
            conn.execute("""INSERT OR REPLACE INTO shared_news_cache_20260704(
                cache_key,provider,normalized_url,headline_hash,headline,published_at,source,
                payload_json,expires_at,stored_at) VALUES(?,?,?,?,?,?,?,?,?,?)""", (
                cache_key, _clean(provider), row["url"], row["headline_hash"], row["headline"],
                str(published or ""), str(row["payload"].get("source") or ""),
                json.dumps(row["payload"], sort_keys=True, default=str),
                (now + pd.Timedelta(seconds=ttl_seconds)).isoformat(), now.isoformat(),
            ))
        conn.commit()
    return {"ok": True, "input_count": len(items or []), "stored_count": len(kept),
            "deduplicated_count": max(0, len(items or [])-len(kept)), "expires_at": (now + pd.Timedelta(seconds=ttl_seconds)).isoformat()}


def load_shared_news(*, provider: str = "FINNHUB", path: Path | str | None = None) -> list[dict[str, Any]]:
    now = pd.Timestamp.now(tz="UTC").isoformat()
    with connect_readonly(path or _runtime_db_path(), timeout=30) as conn:
        rows = conn.execute("SELECT payload_json FROM shared_news_cache_20260704 WHERE provider=? AND expires_at>=? ORDER BY published_at DESC", (_clean(provider), now)).fetchall()
    output: list[dict[str, Any]] = []
    for row in rows:
        try: output.append(json.loads(str(row[0])))
        except Exception: continue
    return output


def api_budget_summary(state: Mapping[str, Any], path: Path | str | None = None) -> dict[str, Any]:
    try:
        parent = str(state.get("multi_symbol_parent_run_id_20260701") or state.get("parent_run_id") or "")
        with connect_readonly(path or _runtime_db_path(), timeout=30) as conn:
            query = "SELECT provider,COALESCE(SUM(credits_used),0),SUM(cache_hit),SUM(deduplicated),COUNT(*) FROM api_request_audit_20260704"
            params: tuple[Any, ...] = ()
            if parent:
                query += " WHERE parent_run_id=?"; params = (parent,)
            query += " GROUP BY provider"
            rows = conn.execute(query, params).fetchall()
        providers = {str(r[0]): {"credits_used": float(r[1]), "cache_hits": int(r[2]), "deduplicated": int(r[3]), "requests": int(r[4])} for r in rows}
        twelve = providers.get("TWELVE", providers.get("TWELVEDATA", {}))
        mt5 = providers.get("MT5", {})
        return {"twelve_credits_used": twelve.get("credits_used", 0.0), "twelve_cache_hits": twelve.get("cache_hits", 0),
                "mt5_symbols_loaded": mt5.get("requests", 0), "api_requests_avoided": sum(v.get("cache_hits",0)+v.get("deduplicated",0) for v in providers.values()),
                "provider_cooldown_status": state.get("twelve_token_bucket_20260704", {}), "providers": providers}
    except Exception as exc:
        return {"error": type(exc).__name__}


def prepare_symbol_market_data(
    state: MutableMapping[str, Any], symbol: str, *, force: bool = False,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Prepare one symbol feed with exact-candle deduplication and bounded retry.

    It is intentionally sequential; this is the provider-safe bounded
    concurrency policy (one in-flight request per shared profile).
    """
    profile = _profile(state)
    if not profile:
        report = {"ok": True, "status": "DELEGATED_TO_EXISTING_RUNNER", "requests": 0, "cache_hits": 0, "version": VERSION}
        state["multi_symbol_api_requests_current_symbol_20260702"] = 0
        state["multi_symbol_api_cache_hits_current_symbol_20260702"] = 0
        return report

    from core.multi_symbol_field10_20260701 import normalize_symbol, resolve_provider_symbol
    canonical_symbol = normalize_symbol(symbol)
    provider = str(profile.get("mode") or state.get("connector_mode") or "fallback").lower()
    timeframe = str(state.get("timeframe") or state.get("selected_timeframe") or profile.get("timeframe") or "H4").upper()
    if timeframe == "CUSTOM":
        timeframe = "H1"
    candle_count = int(profile.get("bars") or state.get("connector_bars") or 600)
    provider_alias = resolve_provider_symbol(canonical_symbol, provider)
    completed = completed_h1_identity(state)
    request_key = build_request_key(
        provider=provider, canonical_symbol=canonical_symbol, provider_alias=provider_alias,
        timeframe=timeframe, candle_count=candle_count, completed_h1_candle=completed,
        profile_fingerprint=str(profile.get("signature") or ""),
    )
    cache = state.get(CACHE_KEY)
    if not isinstance(cache, dict):
        cache = {}
        state[CACHE_KEY] = cache
    cached = cache.get(request_key)
    if not force and isinstance(cached, Mapping) and isinstance(cached.get("frame"), pd.DataFrame) and not cached["frame"].empty:
        state["last_df"] = cached["frame"].copy(deep=False)
        state["source"] = cached.get("source") or "MULTI_SYMBOL_EXACT_CANDLE_CACHE"
        # Child calculation identity is transient. Never mutate Settings main,
        # Lunch display, connector, or widget-owned selection keys here.
        set_legacy_calculation_symbol(state, canonical_symbol, connector=False)  # approved calculation boundary
        report = {
            "ok": True, "status": "EXACT_CANDLE_CACHE_HIT", "requests": 0, "cache_hits": 1,
            "request_key": request_key, "symbol": canonical_symbol, "provider_alias": provider_alias,
            "timeframe": timeframe, "candle_count": candle_count, "completed_h1_candle": completed,
            "profile_signature": str(profile.get("signature") or ""), "version": VERSION,
        }
        state["multi_symbol_api_requests_current_symbol_20260702"] = 0
        state["multi_symbol_api_cache_hits_current_symbol_20260702"] = 1
        state[AUDIT_KEY] = report
        return report

    # Persistent reuse is enabled inside a traceable parent run (the normal
    # production path) or by an explicit caller opt-in.  Standalone callers
    # retain the legacy first-fetch/session-dedup contract and cannot inherit
    # unrelated process history from the project database.
    persistent_allowed = bool(
        state.get("multi_symbol_parent_run_id_20260701")
        or state.get("parent_run_id")
        or state.get("enable_persistent_candle_cache_20260704", False)
    )
    if not force and persistent_allowed:
        persistent_frame, persistent_source = _persistent_get(request_key)
        if isinstance(persistent_frame, pd.DataFrame) and not persistent_frame.empty:
            cache[request_key] = {"frame": persistent_frame.copy(deep=False), "source": persistent_source}
            state["last_df"] = persistent_frame
            state["source"] = persistent_source or "PERSISTENT_EXACT_CANDLE_CACHE"
            set_legacy_calculation_symbol(state, canonical_symbol, connector=False)
            report = {"ok": True, "status": "PERSISTENT_EXACT_CANDLE_CACHE_HIT", "requests": 0, "cache_hits": 1,
                      "request_key": request_key, "symbol": canonical_symbol, "provider_alias": provider_alias,
                      "timeframe": timeframe, "candle_count": candle_count, "completed_h1_candle": completed,
                      "profile_signature": str(profile.get("signature") or ""), "version": VERSION}
            state["multi_symbol_api_requests_current_symbol_20260702"] = 0
            state["multi_symbol_api_cache_hits_current_symbol_20260702"] = 1
            state[AUDIT_KEY] = report
            _audit_request(request_key=request_key, state=state, provider=provider, symbol=canonical_symbol,
                           cache_hit=True, deduplicated=True, response_status=report["status"], completed=completed, duration_ms=0, retry_count=0, credits_used=0)
            return report

    if provider in {"twelve", "twelvedata", "twelve_data"}:
        bucket = twelve_token_bucket_acquire(state)
        if not bucket["allowed"]:
            report = {"ok": False, "status": "PROVIDER_COOLDOWN", "requests": 0, "cache_hits": 0,
                      "cooldown_seconds": bucket["cooldown_seconds"], "symbol": canonical_symbol, "version": VERSION}
            state[AUDIT_KEY] = report
            _audit_request(request_key=request_key, state=state, provider=provider, symbol=canonical_symbol,
                           cache_hit=False, deduplicated=False, response_status=report["status"], completed=completed,
                           duration_ms=0, retry_count=0, credits_used=0, credits_left=bucket["tokens_left"])
            return report

    from core.data_connectors import manual_connect
    request_started = time.perf_counter()
    requests = 0
    last_failure: dict[str, Any] = {}
    for attempt in range(1, max(1, min(int(max_attempts), 3)) + 1):
        requests += 1
        frame, ok, source, message = manual_connect(
            mode=provider, symbol=provider_alias,
            api_key=state.get("twelve_api_key", ""), bars=candle_count,
            timeframe=timeframe, bridge_url=state.get("doo_bridge_url", ""),
            bridge_token=state.get("doo_bridge_token", ""),
            allow_demo=bool(state.get("allow_safe_demo", False)),
        )
        if ok and isinstance(frame, pd.DataFrame) and not frame.empty:
            cache[request_key] = {
                "frame": frame.copy(deep=False), "source": str(source or "UNKNOWN"),
                "symbol": canonical_symbol, "provider_alias": provider_alias,
                "timeframe": timeframe, "candle_count": candle_count,
                "completed_h1_candle": completed,
            }
            state["last_df"] = frame
            state["source"] = source
            set_legacy_calculation_symbol(state, canonical_symbol, connector=False)  # approved calculation boundary
            report = {
                "ok": True, "status": "FETCHED", "requests": requests, "cache_hits": 0,
                "retry_count": max(0, requests - 1), "request_key": request_key,
                "symbol": canonical_symbol, "provider_alias": provider_alias,
                "timeframe": timeframe, "candle_count": candle_count,
                "completed_h1_candle": completed, "source": str(source or "UNKNOWN"),
                "rows": int(len(frame)), "profile_signature": str(profile.get("signature") or ""),
                "version": VERSION,
            }
            state["multi_symbol_api_requests_current_symbol_20260702"] = requests
            state["multi_symbol_api_cache_hits_current_symbol_20260702"] = 0
            state[AUDIT_KEY] = report
            if persistent_allowed:
                _persistent_put(request_key, frame, provider=provider, canonical_symbol=canonical_symbol,
                                provider_alias=provider_alias, timeframe=timeframe, completed=completed,
                                candle_count=candle_count, profile_fingerprint=str(profile.get("signature") or ""),
                                source=str(source or "UNKNOWN"))
            credit = 1.0 if provider in {"twelve", "twelvedata", "twelve_data"} else 0.0
            _audit_request(request_key=request_key, state=state, provider=provider, symbol=canonical_symbol,
                           cache_hit=False, deduplicated=False, response_status="FETCHED", completed=completed,
                           duration_ms=(time.perf_counter()-request_started)*1000, retry_count=max(0, requests-1),
                           credits_used=credit)
            return report
        category = classify_provider_failure(message, source)
        last_failure = {
            "category": category["category"], "provider_status": str(source or "UNKNOWN"),
            "message": str(message or "Provider returned no completed frame"), "attempt": attempt,
        }
        if not category["retryable"] or attempt >= max_attempts:
            break
        time.sleep(min(0.25 * (2 ** (attempt - 1)), 1.0))

    report = {
        "ok": False, "status": "FAILED", "requests": requests, "cache_hits": 0,
        "retry_count": max(0, requests - 1), "request_key": request_key,
        "symbol": canonical_symbol, "provider_alias": provider_alias,
        "timeframe": timeframe, "candle_count": candle_count,
        "completed_h1_candle": completed, "failure": last_failure,
        "profile_signature": str(profile.get("signature") or ""), "version": VERSION,
    }
    state["multi_symbol_api_requests_current_symbol_20260702"] = requests
    state["multi_symbol_api_cache_hits_current_symbol_20260702"] = 0
    state[AUDIT_KEY] = report
    _audit_request(request_key=request_key, state=state, provider=provider, symbol=canonical_symbol,
                   cache_hit=False, deduplicated=False, response_status=str(last_failure.get("category") or "FAILED"),
                   completed=completed, duration_ms=(time.perf_counter()-request_started)*1000,
                   retry_count=max(0, requests-1), credits_used=0)
    return report


__all__ = [
    "VERSION", "CACHE_KEY", "AUDIT_KEY", "completed_h1_identity", "build_request_key",
    "classify_provider_failure", "connection_profile_reusable", "prepare_symbol_market_data",
    "migrate_api_runtime", "twelve_token_bucket_acquire", "api_budget_summary",
    "cache_shared_news_items", "load_shared_news",
]
