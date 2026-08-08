"""Quota-safe multi-provider market-data orchestrator.

Runtime candle route: validated local cache first, then FCS API as the main
live candle provider when configured, then the per-key Twelve Data provider
pool as fallback, then the last-known valid cache. Finnhub is kept out of the
main candle route and remains available elsewhere for news/sentiment. Every
caller receives a normalized frame plus explicit provenance/status and the safe
provider/key alias used for live requests.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection
import hashlib
import json
import logging
import os
import re
import sqlite3
import time

import pandas as pd
import requests

from core.data.candle_repository import CandleRepository, normalize_frame
from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
from core.data.twelve_data_quota_manager import TwelveDataQuotaManager
from core.data.symbol_level_provider_registry_20260708 import SymbolLevelProviderRegistry, normalize_provider_state
from core.runtime_selection_20260705 import latest_completed_candle, normalize_symbol, normalize_timeframe

LOGGER = logging.getLogger(__name__)
FCS_PROVIDER = "FCS_API_MAIN"
TWELVE_POOL_PROVIDER = "TWELVE_DATA_KEY_POOL"
TWELVE_FALLBACK_PROVIDER = TWELVE_POOL_PROVIDER
PROVIDER_PRIORITY: tuple[str, ...] = (
    FCS_PROVIDER, TWELVE_POOL_PROVIDER, "LOCAL_VALID_CACHE",
)
_FCS_PROVIDER_ALIASES = {"FCS", "FCS_API", "FCSAPI", "FCS_API_MAIN", "FCS_ACCESS_KEY", "FCS_MAIN"}
_TWELVE_PROVIDER_ALIASES = {
    "TWELVE_DATA_KEY_POOL", "TWELVE_KEY_POOL", "TWELVE_DATA_POOL",
    "TWELVE_DATA_FALLBACK", "TWELVE_DATA", "TWELVE", "TWELVEDATA",
}

def canonical_provider_name(provider: Any) -> str:
    value = str(provider or "").strip().upper()
    if value in _FCS_PROVIDER_ALIASES:
        return FCS_PROVIDER
    if value in _TWELVE_PROVIDER_ALIASES:
        return TWELVE_POOL_PROVIDER
    return value


def _secret_from_mapping(state: Mapping[str, Any] | None, provider: str) -> str:
    """Resolve only whether a provider credential exists without exposing it."""
    state_map = state if isinstance(state, Mapping) else {}
    provider_name = canonical_provider_name(provider)
    aliases = {
        FCS_PROVIDER: (
            "fcs_api_access_key", "fcs_access_key", "fcs_api_key", "fcsapi_key",
            "FCS_API_ACCESS_KEY", "FCS_ACCESS_KEY", "FCS_API_KEY",
        ),
        TWELVE_POOL_PROVIDER: (
            "twelve_api_key_1", "twelve_api_key_2", "twelve_api_key", "second_api_key",
            "TWELVE_DATA_API_KEY_1", "TWELVE_DATA_API_KEY_2", "TWELVE_DATA_API_KEY", "TWELVE_API_KEY",
        ),
        "FINNHUB": ("finnhub_api_key", "FINNHUB_API_KEY"),
        "ALPHA_VANTAGE": ("alpha_vantage_api_key", "ALPHA_VANTAGE_API_KEY"),
    }
    for key in aliases.get(provider_name, ()): 
        if str(state_map.get(key) or "").strip():
            return str(state_map.get(key) or "").strip()
    return ""

_FIAT_CODES = {
    "AED", "AUD", "CAD", "CHF", "CNH", "CNY", "CZK", "DKK", "EUR", "GBP",
    "HKD", "HUF", "IDR", "ILS", "INR", "JPY", "KRW", "MXN", "MYR", "NOK",
    "NZD", "PHP", "PLN", "RON", "RUB", "SAR", "SEK", "SGD", "THB", "TRY",
    "TWD", "USD", "ZAR",
}
_METAL_CODES = {"XAU", "XAG", "XPT", "XPD"}
_CRYPTO_BASES = {"BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "DOT", "LINK"}
_FINNHUB_SYMBOL_ALIASES = {
    "XAUUSD": "OANDA:XAU_USD",
    "XAGUSD": "OANDA:XAG_USD",
    "XPTUSD": "OANDA:XPT_USD",
    "XPDUSD": "OANDA:XPD_USD",
    "BTCUSD": "BINANCE:BTCUSDT",
    "ETHUSD": "BINANCE:ETHUSDT",
    "SOLUSD": "BINANCE:SOLUSDT",
    "XRPUSD": "BINANCE:XRPUSDT",
    "BNBUSD": "BINANCE:BNBUSDT",
    "ADAUSD": "BINANCE:ADAUSDT",
    "DOGEUSD": "BINANCE:DOGEUSDT",
    "AVAXUSD": "BINANCE:AVAXUSDT",
    "DOTUSD": "BINANCE:DOTUSDT",
    "LINKUSD": "BINANCE:LINKUSDT",
}
_YAHOO_SYMBOL_ALIASES = {
    # Spot FX is available through Yahoo's currency-pair chart symbols.
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "XPTUSD": "PL=F",
    "XPDUSD": "PA=F",
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "SOLUSD": "SOL-USD",
    "XRPUSD": "XRP-USD",
    "BNBUSD": "BNB-USD",
    "ADAUSD": "ADA-USD",
    "DOGEUSD": "DOGE-USD",
    "AVAXUSD": "AVAX-USD",
    "DOTUSD": "DOT-USD",
    "LINKUSD": "LINK-USD",
    "DXY": "DX-Y.NYB",
    # Common broker index aliases used by the three-selector UI.
    "NAS100": "^NDX",
    "US500": "^GSPC",
    "US30": "^DJI",
    "DAX40": "^GDAXI",
    "UK100": "^FTSE",
    "JPN225": "^N225",
    "HK50": "^HSI",
}
CONNECTOR_PROVIDER_PRIORITY: dict[str, tuple[str, ...]] = {
    # Local cache is checked before this tuple inside fetch(); the live route is
    # FCS API main, Twelve Data key pool fallback, then emergency cache.
    "fcs": PROVIDER_PRIORITY,
    "fcs_api": PROVIDER_PRIORITY,
    "fcs_api_main": PROVIDER_PRIORITY,
    "twelve_pool": PROVIDER_PRIORITY,
    "twelve_key_pool": PROVIDER_PRIORITY,
    "twelve": PROVIDER_PRIORITY,
    "twelve_data": PROVIDER_PRIORITY,
    "twelve_data_fallback": PROVIDER_PRIORITY,
    "fallback": PROVIDER_PRIORITY,
    "safe_demo": PROVIDER_PRIORITY,
}


PROVIDER_TIMEFRAME_MAP: dict[str, dict[str, str]] = {
    FCS_PROVIDER: {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"},
    TWELVE_POOL_PROVIDER: {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "1h", "D1": "1day"},
    # Legacy provider names are kept only so old cached rows/tests still normalize.
    "TWELVE_DATA": {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "1h", "H4": "1h", "D1": "1day"},
    "FINNHUB": {"M1": "1", "M5": "5", "M15": "15", "M30": "30", "H1": "60", "H4": "60", "D1": "D"},
    "MT5": {"M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30", "H1": "H1", "H4": "H4", "D1": "D1"},
    "ALPHA_VANTAGE": {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "60min", "H4": "60min"},
    "LOCAL_VALID_CACHE": {"M1": "M1", "M5": "M5", "M15": "M15", "M30": "M30", "H1": "H1", "H4": "H4", "D1": "D1"},
}

def provider_interval_for(timeframe: Any, provider: str) -> str:
    provider_name = canonical_provider_name(provider)
    tf = normalize_timeframe(timeframe)
    mapping = PROVIDER_TIMEFRAME_MAP.get(provider_name, {})
    if tf not in mapping:
        raise ProviderPermanentError(f"{provider_name} timeframe {tf} is unsupported")
    return mapping[tf]

def provider_priority_for_state(state: Mapping[str, Any] | None) -> tuple[str, ...]:
    """Return cache -> FCS main -> Twelve key-pool fallback -> emergency cache plan."""
    state_map = state if isinstance(state, Mapping) else {}
    # Selector-owned Twelve workers must not rotate/fall through to another live
    # candle provider.  Cache is still checked before this provider tuple inside
    # ``fetch``; after the assigned Twelve key fails, only last-known cache is
    # allowed.  This prevents Selector 1 from spending Key 2/Finnhub credits and
    # prevents Selector 2 from spending Key 1/Finnhub credits during normal loads.
    if bool(state_map.get("selector_owned_twelve_only_20260708")) and not _secret_from_mapping(state_map, FCS_PROVIDER):
        return (TWELVE_POOL_PROVIDER, "LOCAL_VALID_CACHE")
    source = str(state_map.get("connector_mode") or "twelve_pool").strip().lower()
    configured = tuple(canonical_provider_name(item) for item in CONNECTOR_PROVIDER_PRIORITY.get(source, PROVIDER_PRIORITY))
    sanitized: list[str] = []
    for provider in configured or PROVIDER_PRIORITY:
        provider = canonical_provider_name(provider)
        # FCS is a valid symbol-level main provider in the institutional route.
        if provider and provider not in sanitized:
            sanitized.append(provider)
    for provider in (FCS_PROVIDER, TWELVE_POOL_PROVIDER, "LOCAL_VALID_CACHE"):
        if provider not in sanitized:
            sanitized.append(provider)
    return tuple(sanitized)

def _provider_status(provider: str, primary_provider: str) -> str:
    provider = canonical_provider_name(provider)
    primary_provider = canonical_provider_name(primary_provider)
    if provider == primary_provider:
        return "LIVE_PRIMARY"
    if provider == TWELVE_FALLBACK_PROVIDER:
        return "LIVE_FALLBACK"
    if provider == "LOCAL_VALID_CACHE":
        return "CACHED_VALID"
    return "LIVE_FALLBACK"

STATUS_BY_PROVIDER = {
    FCS_PROVIDER: "LIVE_PRIMARY",
    TWELVE_POOL_PROVIDER: "LIVE_FALLBACK",
    "TWELVE_DATA": "LIVE_PRIMARY",
    "FINNHUB": "LIVE_FALLBACK",
    "MT5": "LEGACY_NOT_ACTIVE",
    "ALPHA_VANTAGE": "LEGACY_NOT_ACTIVE",
    "LOCAL_VALID_CACHE": "CACHED_VALID",
}


@dataclass
class MarketDataResult:
    ok: bool
    symbol: str
    timeframe: str
    frame: pd.DataFrame
    provider: str
    provider_symbol: str
    status: str
    message: str
    latest_completed_candle: str | None
    fallback_provider: str | None
    attempts: list[dict[str, Any]]
    data_age_seconds: float | None
    data_quality_score: float
    validation_status: str
    run_id: str = ""
    provider_key_alias: str | None = None

    def to_dict(self, *, include_frame: bool = True) -> dict[str, Any]:
        payload = {
            "ok": self.ok,
            "symbol": self.symbol,
            "canonical_symbol": self.symbol,
            "timeframe": self.timeframe,
            "requested_timeframe": self.timeframe,
            "provider": self.provider,
            "actual_provider": self.provider,
            "preferred_provider": FCS_PROVIDER,
            "provider_symbol": self.provider_symbol,
            "provider_key_alias": self.provider_key_alias,
            "actual_key_name": self.provider_key_alias,
            "status": self.status,
            "message": self.message,
            "latest_completed_candle": self.latest_completed_candle,
            "load_timestamp": datetime.now(timezone.utc).isoformat(),
            "fallback_provider": self.fallback_provider,
            "fallback_reason": (
                "LIVE_PROVIDER_FALLBACK_USED"
                if self.ok and canonical_provider_name(self.provider) not in {TWELVE_POOL_PROVIDER, "LOCAL_VALID_CACHE"}
                else "VALIDATED_LOCAL_CACHE_REUSED"
                if self.ok and self.status in {"CACHED_VALID", "STALE_VALID"}
                else None
            ),
            "attempts": self.attempts,
            "attempt_count": len(self.attempts),
            "data_age_seconds": self.data_age_seconds,
            "data_quality_score": self.data_quality_score,
            "validation_status": self.validation_status,
            "run_id": self.run_id,
        }
        if include_frame:
            payload["frame"] = self.frame
        return payload


class ProviderPermanentError(RuntimeError):
    pass


class ProviderRateLimited(RuntimeError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


def _explicit_success_flag(value: Any, frame: Any) -> bool:
    """Interpret adapter success metadata without Boolean-evaluating tabular objects."""
    if isinstance(value, pd.DataFrame):
        return not value.empty
    if isinstance(value, pd.Series):
        return not value.empty and bool(value.astype(bool).all())
    if hasattr(value, "size") and not isinstance(value, (str, bytes, bytearray)):
        try:
            return int(value.size) > 0 and bool(value.all())
        except Exception:
            return False
    if value is None:
        return isinstance(frame, pd.DataFrame) and not frame.empty
    return bool(value)


class MarketDataOrchestrator:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        adapters: Mapping[str, Callable[..., Any]] | None = None,
        quota_manager: TwelveDataQuotaManager | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)
        self.repository = CandleRepository(self.db_path)
        self.quota = quota_manager or TwelveDataQuotaManager(self.db_path)
        self.provider_registry = SymbolLevelProviderRegistry(self.db_path)
        self.session = session or requests.Session()
        provided = {str(k).upper(): v for k, v in (adapters or {}).items()}
        self.adapters: dict[str, Callable[..., Any]] = {
            FCS_PROVIDER: provided.get(FCS_PROVIDER, provided.get("FCS_API", self._fetch_fcs)),
            TWELVE_POOL_PROVIDER: provided.get(TWELVE_POOL_PROVIDER, provided.get("TWELVE_DATA", self._fetch_twelve)),
            # Legacy Twelve adapter labels are normalized to the key pool.
            "TWELVE_DATA": provided.get("TWELVE_DATA", self._fetch_twelve),
            "FINNHUB": provided.get("FINNHUB", self._fetch_finnhub),
            "MT5": provided.get("MT5", self._fetch_mt5),
            "ALPHA_VANTAGE": provided.get("ALPHA_VANTAGE", self._fetch_alpha_vantage),
        }

    @staticmethod
    def provider_symbol(symbol: Any, provider: str) -> str:
        canonical = normalize_symbol(symbol)
        provider_name = canonical_provider_name(provider)
        alias = _FINNHUB_SYMBOL_ALIASES.get(canonical) if provider_name == "FINNHUB" else None
        if alias:
            return alias
        if len(canonical) == 6 and canonical.isalpha():
            if provider_name in {FCS_PROVIDER, TWELVE_FALLBACK_PROVIDER}:
                return f"{canonical[:3]}/{canonical[3:]}"
            if provider_name == "FINNHUB" and canonical[:3] in (_FIAT_CODES | _METAL_CODES) and canonical[3:] in _FIAT_CODES:
                return f"OANDA:{canonical[:3]}_{canonical[3:]}"
        aliases = {
            ("XAUUSD", TWELVE_FALLBACK_PROVIDER): "XAU/USD",
            ("BTCUSD", TWELVE_FALLBACK_PROVIDER): "BTC/USD",
            ("DXY", TWELVE_FALLBACK_PROVIDER): "DXY",
            ("DXY", FCS_PROVIDER): "DXY",
        }
        return aliases.get((canonical, provider_name), canonical)

    @staticmethod
    def _finnhub_candle_endpoint(symbol: str) -> str:
        canonical = normalize_symbol(symbol)
        base, quote = canonical[:3], canonical[3:]
        if len(canonical) == 6 and base in _CRYPTO_BASES and quote in {"USD", "USDT"}:
            return "crypto/candle"
        if len(canonical) == 6 and base in (_FIAT_CODES | _METAL_CODES) and quote in _FIAT_CODES:
            return "forex/candle"
        return "stock/candle"

    @staticmethod
    def _secret(state: Mapping[str, Any], provider: str) -> str:
        provider_name = canonical_provider_name(provider)
        aliases = {
            FCS_PROVIDER: (
                "fcs_api_access_key", "fcs_access_key", "fcs_api_key", "fcsapi_key",
                "FCS_API_ACCESS_KEY", "FCS_ACCESS_KEY", "FCS_API_KEY",
            ),
            TWELVE_POOL_PROVIDER: (
                "twelve_api_key_1", "twelve_api_key", "second_api_key",
                "TWELVE_DATA_API_KEY_1", "TWELVE_DATA_API_KEY", "TWELVE_API_KEY",
            ),
            "FINNHUB": ("finnhub_api_key", "FINNHUB_API_KEY"),
            "ALPHA_VANTAGE": ("alpha_vantage_api_key", "ALPHA_VANTAGE_API_KEY"),
        }
        for key in aliases.get(provider_name, ()):
            value = str(state.get(key) or "").strip()
            if value:
                return value
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            logical = {
                FCS_PROVIDER: "fcs",
                TWELVE_POOL_PROVIDER: "second_api",
                "FINNHUB": "finnhub",
                "ALPHA_VANTAGE": "alpha_vantage",
            }.get(provider_name)
            if logical:
                return str(resolve_api_key(logical, state) or "").strip()
        except Exception:
            pass
        return ""

    def _health(self, provider: str, *, ok: bool, status: str, detail_code: str = "", rate_limited: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.execute(
                """INSERT INTO provider_health(provider,status,healthy,last_success_at,last_failure_at,last_429_at,
                   retry_after_seconds,fallback_count,detail_code,updated_at)
                   VALUES(?,?,?,?,?,?,NULL,0,?,?)
                   ON CONFLICT(provider) DO UPDATE SET status=excluded.status,healthy=excluded.healthy,
                   last_success_at=CASE WHEN excluded.healthy=1 THEN excluded.last_success_at ELSE provider_health.last_success_at END,
                   last_failure_at=CASE WHEN excluded.healthy=0 THEN excluded.last_failure_at ELSE provider_health.last_failure_at END,
                   last_429_at=CASE WHEN ?=1 THEN excluded.last_429_at ELSE provider_health.last_429_at END,
                   detail_code=excluded.detail_code,updated_at=excluded.updated_at""",
                (
                    provider, status, int(ok), now if ok else None, None if ok else now,
                    now if rate_limited else None, detail_code, now, int(rate_limited),
                ),
            )
            conn.commit()

    def _fallback_event(self, *, run_id: str, symbol: str, timeframe: str, from_provider: str, to_provider: str, reason: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        event_id = hashlib.sha256(f"{run_id}|{symbol}|{timeframe}|{from_provider}|{to_provider}|{now}".encode()).hexdigest()
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO fallback_events(event_id,run_id,symbol,timeframe,from_provider,to_provider,reason_code,occurred_at)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (event_id, run_id, symbol, timeframe, from_provider, to_provider, reason[:120], now),
            )
            conn.execute(
                "UPDATE provider_health SET fallback_count=fallback_count+1,updated_at=? WHERE provider=?",
                (now, to_provider),
            )
            conn.commit()

    def _ledger_attempt(
        self, *, run_id: str, symbol: str, timeframe: str, provider_attempted: str,
        provider_used: str = "", status: str = "FAILED", rows: int = 0,
        completed_candle_time: str | None = None, response_time_ms: float | None = None,
        error_code: str = "", error_message: str = "",
    ) -> None:
        try:
            with sqlite3.connect(str(self.db_path), timeout=10) as conn:
                conn.execute(
                    """INSERT INTO symbol_load_ledger_20260708(
                           run_id,symbol,timeframe,provider_attempted,provider_used,status,rows,
                           completed_candle_time,response_time_ms,error_code,error_message,created_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(run_id or ""), str(symbol or "").upper(), str(timeframe or "").upper(),
                        str(provider_attempted or "UNKNOWN").upper(), str(provider_used or "").upper(),
                        str(status or "FAILED").upper(), int(rows or 0), completed_candle_time,
                        None if response_time_ms is None else float(response_time_ms),
                        str(error_code or "")[:120], str(error_message or "")[:500], datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.commit()
        except Exception:
            LOGGER.debug("symbol_load_ledger write failed", exc_info=True)

    @staticmethod
    def _classify_failure(exc: Exception) -> tuple[str, bool]:
        text = str(exc).upper()
        if isinstance(exc, ProviderRateLimited) or "429" in text or "RATE LIMIT" in text or "QUOTA" in text:
            return "RATE_LIMITED", True
        if isinstance(exc, ProviderPermanentError) or any(token in text for token in ("INVALID SYMBOL", "401", "403", "API KEY", "UNAUTHORIZED", "AUTH")):
            return "AUTH_FAILED", False
        if any(token in text for token in ("TIMEOUT", "CONNECTION", "NETWORK", "500", "502", "503", "504")):
            return "TIMEOUT", True
        if any(token in text for token in ("EMPTY", "NO COMPLETE", "NO USABLE", "NO VALID", "NO CANDLE")):
            return "EMPTY_CANDLES", False
        return "VALIDATION_FAILED", False

    @staticmethod
    def _redact_failure_message(value: Any, state: Mapping[str, Any] | None = None) -> str:
        text = ("" if value is None else str(value)).replace("\n", " ")
        text = re.sub(
            r"(?i)(token|apikey|api_key|api-key)=([^&\s]+)",
            r"\1=[REDACTED]",
            text,
        )
        for key, secret in (state or {}).items():
            key_text = str(key).lower()
            secret_text = str(secret or "").strip()
            if secret_text and len(secret_text) >= 8 and any(marker in key_text for marker in ("api_key", "apikey", "token")):
                text = text.replace(secret_text, "[REDACTED]")
        return text[:180]

    @staticmethod
    def _final_failure_message(attempts: list[dict[str, Any]]) -> str:
        """Build a redacted, actionable summary of the provider route.

        The previous generic message hid the important distinction between a
        configured Finnhub key, candle-endpoint entitlement, an invalid Twelve
        Data credential, and a temporary network failure.  Only short provider
        categories/messages are included; request URLs and credentials never
        enter this text.
        """
        if not attempts:
            return "No live provider was attempted and no validated local candle cache is available."
        parts: list[str] = []
        seen: set[str] = set()
        for attempt in attempts:
            provider = str(attempt.get("provider") or "UNKNOWN").strip().upper()
            if provider in seen:
                continue
            seen.add(provider)
            category = str(attempt.get("category") or "FAILED").strip().upper()
            detail = str(attempt.get("message") or "").strip().replace("\n", " ")[:120]
            label = provider.replace("_", " ").title()
            parts.append(f"{label}: {detail or category}")
        route = "; ".join(parts[:5])
        return (
            "No trustworthy live or cached candle series is available. "
            f"Provider route: {route}."
        )

    def _normalize_adapter_result(
        self,
        raw: Any,
        *,
        symbol: str,
        timeframe: str,
        provider: str,
        provider_symbol: str,
        status: str,
    ) -> tuple[pd.DataFrame, str, dict[str, Any]]:
        message = ""
        frame = raw
        metadata: dict[str, Any] = {}
        if isinstance(raw, tuple):
            frame = raw[0] if len(raw) > 0 else None
            ok = _explicit_success_flag(raw[1], frame) if len(raw) > 1 else isinstance(frame, pd.DataFrame) and not frame.empty
            message = str(raw[2]) if len(raw) > 2 else ""
            if len(raw) > 3 and isinstance(raw[3], Mapping):
                metadata = dict(raw[3])
            if not ok:
                if "429" in message or "rate" in message.lower() or "quota" in message.lower() or "LIMIT" in message.upper():
                    raise ProviderRateLimited(message)
                raise RuntimeError(message or f"{provider} returned no valid data")
        if isinstance(frame, list):
            frame = pd.DataFrame(frame)
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            raise RuntimeError(f"{provider} returned empty data")
        normalized = normalize_frame(
            frame, symbol=symbol, timeframe=timeframe, provider=provider,
            provider_symbol=provider_symbol, source_status=status,
        )
        valid = normalized[(normalized["validation_status"] == "VALID") & normalized["is_complete"].astype(bool)]
        if valid.empty:
            raise RuntimeError(f"{provider} returned no complete valid candles")
        return valid, message, metadata

    def fetch(
        self,
        *,
        symbol: Any,
        timeframe: Any,
        state: MutableMapping[str, Any] | Mapping[str, Any] | None = None,
        bars: int = 600,
        run_id: str = "",
        force_live: bool = False,
        essential: bool = False,
        disabled_providers: Collection[str] | None = None,
    ) -> MarketDataResult:
        state = state if isinstance(state, Mapping) else {}
        canonical_symbol = normalize_symbol(symbol)
        tf = normalize_timeframe(timeframe)
        expected = latest_completed_candle(timeframe=tf)
        cached = self.repository.load(canonical_symbol, tf, limit=bars, completed_only=True)
        cache_current = False
        if not cached.empty:
            latest = pd.to_datetime(cached["open_time"], errors="coerce", utc=True).max()
            cache_current = pd.notna(latest) and pd.Timestamp(latest) >= pd.Timestamp(expected)
        from core.timeframe_window_contract_20260706 import minimum_calculation_candles
        minimum_history = min(max(1, int(bars)), int(minimum_calculation_candles(tf, "higher")))
        cache_sufficient = int(len(cached)) >= minimum_history
        # A current *and complete* validated local series is the same canonical
        # input all fields should reuse.  A one-candle/current cache must not
        # suppress the live history request and later appear as 100%-processed
        # but insufficient in Field 10.
        if cache_current and cache_sufficient and not force_live:
            return self._cached_result(canonical_symbol, tf, cached, run_id=run_id, current=True)

        attempts: list[dict[str, Any]] = []
        provider_order = tuple(canonical_provider_name(item) for item in provider_priority_for_state(state))
        primary_provider = provider_order[0]
        disabled = {str(value or "").strip().upper() for value in (disabled_providers or ()) if str(value or "").strip()}
        first_failure_provider = ""
        for provider in provider_order[:-1]:
            provider_symbol = self.provider_symbol(canonical_symbol, provider)
            # Force-live / explicit reload must bypass stale foreground
            # symbol-level circuit breakers. The key pool still enforces per-key
            # minute limits and cooldowns, so bypassing this local skip does not
            # bypass provider rules; it only guarantees the reload button makes a
            # real retry decision instead of returning the old RUN_CIRCUIT_OPEN
            # row forever.
            circuit_open = bool(provider in disabled or ((not force_live) and self.provider_registry.circuit_open(provider, canonical_symbol, tf)))
            if circuit_open:
                attempts.append({
                    "provider": provider,
                    "provider_symbol": provider_symbol,
                    "retry_count": 0,
                    "ok": False,
                    "request_sent": False,
                    "category": "RUN_CIRCUIT_OPEN",
                    "retryable": False,
                    "message": "Provider skipped by foreground symbol-level circuit breaker after recent hard failure.",
                })
                self._ledger_attempt(
                    run_id=run_id, symbol=canonical_symbol, timeframe=tf, provider_attempted=provider,
                    status="RUN_CIRCUIT_OPEN", error_code="RUN_CIRCUIT_OPEN",
                    error_message="Provider skipped by foreground symbol-level circuit breaker.",
                )
                continue
            # Twelve Data key pool may receive bounded retries for temporary
            # transport/server failures. Per-key credit/cooldown is enforced by
            # core.twelve_data_key_pool, not by a single global key counter.
            run_scope = str(state.get("settings_calculation_scope_20260625") or "QUICK").upper()
            assigned_twelve_alias = str(state.get("selector_owned_twelve_assigned_key_20260708") or state.get("twelve_assigned_key_alias_20260708") or "").strip().upper()
            if provider == primary_provider and provider == TWELVE_POOL_PROVIDER and assigned_twelve_alias:
                # Selector-owned button clicks get exactly one request decision per
                # symbol. Failed-symbol retry is controlled by the explicit UI buttons,
                # not by hidden in-click provider retry loops.
                max_attempts = 1
            elif provider == primary_provider and provider == TWELVE_POOL_PROVIDER:
                max_attempts = 2 if run_scope in {"LUNCH_CORE", "QUICK"} else 3
            else:
                max_attempts = 1
            for provider_attempt in range(max_attempts):
                attempt: dict[str, Any] = {
                    "provider": provider,
                    "provider_symbol": provider_symbol,
                    "provider_interval": provider_interval_for(tf, provider),
                    "requested_timeframe": tf,
                    "requested_rows": int(bars),
                    "retry_count": provider_attempt,
                }
                reservation: dict[str, Any] | None = None
                request_sent = False
                attempt_started = time.monotonic()
                try:
                    if provider == FCS_PROVIDER and not self._secret(state, provider):
                        raise ProviderPermanentError(f"{provider}_NOT_CONFIGURED")
                    if provider == TWELVE_POOL_PROVIDER:
                        try:
                            from core.twelve_data_key_pool import TwelveDataKeyPool
                            if not TwelveDataKeyPool.from_state(state).has_available_key():
                                raise ProviderPermanentError("TWELVE_DATA_KEY_POOL_NOT_CONFIGURED")
                        except ProviderPermanentError:
                            raise
                        except Exception:
                            pass
                    elif provider in {"FINNHUB", "ALPHA_VANTAGE"} and not self._secret(state, provider):
                        raise ProviderPermanentError(f"{provider}_NOT_CONFIGURED")

                    LOGGER.info(
                        "provider_request_start provider=%s symbol=%s timeframe=%s estimated_credit_cost=%s retry=%s",
                        provider, canonical_symbol, tf, 1 if provider == TWELVE_POOL_PROVIDER else 0, provider_attempt,
                    )
                    request_sent = True
                    raw = self.adapters[provider](
                        symbol=canonical_symbol, provider_symbol=provider_symbol,
                        timeframe=tf, bars=int(bars), state=state,
                    )
                    provider_status = _provider_status(provider, primary_provider)
                    frame, message, metadata = self._normalize_adapter_result(
                        raw, symbol=canonical_symbol, timeframe=tf, provider=provider,
                        provider_symbol=provider_symbol, status=provider_status,
                    )
                    provider_key_alias = str(metadata.get("provider_key_alias") or metadata.get("actual_key_name") or "").strip() or None
                    if provider_key_alias:
                        frame = frame.copy()
                        frame["provider_key_alias"] = provider_key_alias
                        attempt["provider_key_alias"] = provider_key_alias
                        attempt["actual_key_name"] = provider_key_alias
                    frame = frame.tail(max(2, int(bars))).reset_index(drop=True)
                    if reservation:
                        self.quota.complete(
                            str(reservation["request_id"]), response_status="SUCCESS",
                            http_status=200, retry_count=provider_attempt,
                        )
                    persisted = self.repository.upsert(frame, run_id=run_id, require_complete=True)
                    # A provider may return only the newest page even when the
                    # repository already contains older validated candles.  The
                    # child publication contract needs the complete causal
                    # history, not just the last response page.  Reloading after
                    # the atomic upsert combines both without synthesizing or
                    # borrowing any price from another symbol.
                    combined = self.repository.load(
                        canonical_symbol, tf, limit=int(bars), completed_only=True,
                    )
                    available = combined if not combined.empty and len(combined) >= len(frame) else frame
                    attempt.update({
                        "ok": True, "request_sent": True,
                        "load_duration_seconds": round(max(0.0, time.monotonic() - attempt_started), 3),
                        "response_rows": int(len(frame)),
                        "rows": int(len(available)),
                        "repository_rows_after_merge": int(len(combined)),
                        "persistence": persisted,
                    })
                    attempts.append(attempt)
                    self._health(provider, ok=True, status="CONNECTED")
                    try:
                        self.provider_registry.record_attempt(
                            provider=provider, symbol=canonical_symbol, timeframe=tf, ok=True,
                            rows=int(len(available)), response_time_ms=float(attempt.get("load_duration_seconds") or 0.0) * 1000.0,
                            coverage_ratio=min(1.0, float(len(available)) / max(1.0, float(bars))),
                        )
                        latest_loaded = pd.to_datetime(available["open_time"], errors="coerce", utc=True).max() if "open_time" in available.columns else pd.NaT
                        self._ledger_attempt(
                            run_id=run_id, symbol=canonical_symbol, timeframe=tf, provider_attempted=provider,
                            provider_used=provider, status="VALIDATED", rows=int(len(available)),
                            completed_candle_time=None if pd.isna(latest_loaded) else pd.Timestamp(latest_loaded).isoformat(),
                            response_time_ms=float(attempt.get("load_duration_seconds") or 0.0) * 1000.0,
                        )
                    except Exception:
                        LOGGER.debug("provider registry success update failed", exc_info=True)
                    LOGGER.info(
                        "provider_request_result provider=%s symbol=%s timeframe=%s status=SUCCESS response_rows=%s available_rows=%s retry=%s",
                        provider, canonical_symbol, tf, len(frame), len(available), provider_attempt,
                    )
                    if provider != primary_provider:
                        self._fallback_event(
                            run_id=run_id, symbol=canonical_symbol, timeframe=tf,
                            from_provider=first_failure_provider or primary_provider,
                            to_provider=provider, reason="UPSTREAM_PROVIDER_UNAVAILABLE",
                        )
                    return self._live_result(
                        canonical_symbol, tf, available, provider, provider_symbol,
                        message or f"Validated {provider} candles", attempts, run_id,
                        status=provider_status, primary_provider=primary_provider, provider_key_alias=provider_key_alias,
                    )
                except Exception as exc:
                    category, retryable = self._classify_failure(exc)
                    if not first_failure_provider:
                        first_failure_provider = provider
                    redacted_message = self._redact_failure_message(exc, state)
                    quota_blocked = bool(
                        provider == TWELVE_POOL_PROVIDER
                        and category == "RATE_LIMITED"
                        and any(token in str(redacted_message).upper() for token in ("ALL_TWELVE_KEYS_LIMITED", "RATE_LIMIT", "QUOTA", "COOLDOWN", "LIMITED"))
                    )
                    attempt.update({
                        "ok": False, "request_sent": False if quota_blocked else bool(request_sent),
                        "quota_blocked": quota_blocked,
                        "load_duration_seconds": round(max(0.0, time.monotonic() - attempt_started), 3),
                        "category": category, "retryable": retryable,
                        "message": redacted_message,
                    })
                    attempts.append(attempt)
                    if reservation and reservation.get("request_id"):
                        if request_sent:
                            self.quota.complete(
                                str(reservation["request_id"]), response_status=category,
                                retry_count=provider_attempt,
                            )
                        else:
                            self.quota.release(str(reservation["request_id"]))
                    if provider == TWELVE_POOL_PROVIDER and category == "RATE_LIMITED":
                        retry_after = exc.retry_after if isinstance(exc, ProviderRateLimited) else None
                        self._health(provider, ok=False, status="RATE_LIMITED", detail_code=category, rate_limited=True)
                    else:
                        self._health(provider, ok=False, status="UNAVAILABLE", detail_code=category)
                    try:
                        self.provider_registry.record_attempt(
                            provider=provider, symbol=canonical_symbol, timeframe=tf, ok=False, rows=0,
                            response_time_ms=float(attempt.get("load_duration_seconds") or 0.0) * 1000.0,
                            error_code=category, error_message=str(attempt.get("message") or category),
                        )
                        self._ledger_attempt(
                            run_id=run_id, symbol=canonical_symbol, timeframe=tf, provider_attempted=provider,
                            status=category, response_time_ms=float(attempt.get("load_duration_seconds") or 0.0) * 1000.0,
                            error_code=category, error_message=str(attempt.get("message") or category),
                        )
                    except Exception:
                        LOGGER.debug("provider registry failure update failed", exc_info=True)
                    LOGGER.info(
                        "provider_request_result provider=%s symbol=%s timeframe=%s status=%s retry=%s",
                        provider, canonical_symbol, tf, category, provider_attempt,
                    )
                    should_retry = (
                        provider == primary_provider
                        and provider == TWELVE_POOL_PROVIDER
                        and retryable
                        and category in {"TEMPORARY_PROVIDER_ERROR", "RATE_LIMITED"}
                        and provider_attempt < max_attempts - 1
                    )
                    if should_retry:
                        # Short bounded backoff only. Long Retry-After windows are
                        # never slept through; they activate Plan B immediately.
                        delay = min(2.0, self.quota.backoff_seconds(provider_attempt))
                        LOGGER.info(
                            "provider_retry provider=%s symbol=%s timeframe=%s delay_seconds=%.3f retry=%s",
                            provider, canonical_symbol, tf, delay, provider_attempt + 1,
                        )
                        time.sleep(delay)
                        continue
                    break

        cached = self.repository.load(canonical_symbol, tf, limit=bars, completed_only=True)
        if not cached.empty:
            result = self._cached_result(canonical_symbol, tf, cached, run_id=run_id, current=False)
            result.attempts = attempts
            result.fallback_provider = "LOCAL_VALID_CACHE"
            latest_cached = pd.to_datetime(cached["open_time"], errors="coerce", utc=True).max() if "open_time" in cached.columns else pd.NaT
            self._ledger_attempt(
                run_id=run_id, symbol=canonical_symbol, timeframe=tf, provider_attempted="LAST_KNOWN_VALID_CACHE",
                provider_used="LOCAL_VALID_CACHE", status="DEGRADED_VALID_CACHE", rows=int(len(cached)),
                completed_candle_time=None if pd.isna(latest_cached) else pd.Timestamp(latest_cached).isoformat(),
            )
            return result
        self._ledger_attempt(
            run_id=run_id, symbol=canonical_symbol, timeframe=tf, provider_attempted="ALL_PROVIDERS",
            provider_used="NONE", status="FAILED_EXPLICIT", rows=0, error_code="CACHE_MISSING",
            error_message=self._final_failure_message(attempts),
        )
        return MarketDataResult(
            ok=False, symbol=canonical_symbol, timeframe=tf,
            frame=pd.DataFrame(), provider="NONE", provider_symbol=canonical_symbol,
            status="INSUFFICIENT", message=self._final_failure_message(attempts),
            latest_completed_candle=None, fallback_provider=None, attempts=attempts,
            data_age_seconds=None, data_quality_score=0.0,
            validation_status="INSUFFICIENT", run_id=run_id,
        )

    def _live_result(self, symbol: str, timeframe: str, frame: pd.DataFrame, provider: str, provider_symbol: str,
                     message: str, attempts: list[dict[str, Any]], run_id: str, *,
                     status: str | None = None, primary_provider: str = TWELVE_POOL_PROVIDER,
                     provider_key_alias: str | None = None) -> MarketDataResult:
        latest = pd.to_datetime(frame["open_time"], errors="coerce", utc=True).max()
        age = max(0.0, (pd.Timestamp.now(tz="UTC") - pd.Timestamp(latest)).total_seconds()) if pd.notna(latest) else None
        return MarketDataResult(
            ok=True, symbol=symbol, timeframe=timeframe, frame=frame,
            provider=provider, provider_symbol=provider_symbol,
            status=status or _provider_status(provider, primary_provider), message=message,
            latest_completed_candle=pd.Timestamp(latest).isoformat() if pd.notna(latest) else None,
            fallback_provider=None if provider == primary_provider else provider,
            attempts=attempts, data_age_seconds=age,
            data_quality_score=float(frame["data_quality_score"].mean()),
            validation_status="VALID", run_id=run_id, provider_key_alias=provider_key_alias,
        )

    def _cached_result(self, symbol: str, timeframe: str, frame: pd.DataFrame, *, run_id: str, current: bool) -> MarketDataResult:
        latest = pd.to_datetime(frame["open_time"], errors="coerce", utc=True).max()
        age = max(0.0, (pd.Timestamp.now(tz="UTC") - pd.Timestamp(latest)).total_seconds()) if pd.notna(latest) else None
        provider = str(frame.iloc[-1].get("provider") or "LOCAL_VALID_CACHE")
        provider_key_alias = str(frame.iloc[-1].get("provider_key_alias") or "") if "provider_key_alias" in frame.columns else ""
        expected = pd.Timestamp(latest_completed_candle(timeframe=timeframe))
        status = "CACHED_VALID" if current or (pd.notna(latest) and pd.Timestamp(latest) >= expected) else "STALE_VALID"
        quality_raw = pd.to_numeric(frame.get("data_quality_score"), errors="coerce").mean()
        quality = float(quality_raw) if pd.notna(quality_raw) else 0.0
        if status == "STALE_VALID":
            quality = max(0.0, quality - 15.0)
        return MarketDataResult(
            ok=True, symbol=symbol, timeframe=timeframe, frame=frame,
            provider=provider, provider_symbol=str(frame.iloc[-1].get("provider_symbol") or symbol),
            status=status, message="Validated local candle cache reused; no API request was made.",
            latest_completed_candle=pd.Timestamp(latest).isoformat() if pd.notna(latest) else None,
            fallback_provider="LOCAL_VALID_CACHE", attempts=[], data_age_seconds=age,
            data_quality_score=quality, validation_status="VALID", run_id=run_id,
            provider_key_alias=provider_key_alias or None,
        )


    def _fetch_fcs(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        """Fetch candles from FCS API using the user's access key.

        The response parser accepts the common FCS history shapes without
        leaking credentials into errors.  Candle-data success is validated by
        the shared normalizer after this function returns.
        """
        access_key = self._secret(state, FCS_PROVIDER)
        if not access_key:
            raise ProviderPermanentError("FCS_API_MAIN_NOT_CONFIGURED")
        period = provider_interval_for(timeframe, FCS_PROVIDER)
        params = {
            "symbol": provider_symbol,
            "period": period,
            "access_key": access_key,
        }
        # Some FCS plans accept a limit parameter; unsupported parameters are
        # ignored by the API, while the downstream repository still enforces the
        # real number of returned complete candles.
        params["limit"] = int(max(2, min(int(bars), 1000)))
        url = "https://fcsapi.com/api-v3/forex/history"
        response = self.session.get(url, params=params, timeout=15)
        if response.status_code == 429:
            raise ProviderRateLimited("FCS_API_MAIN_RATE_LIMITED", retry_after=None)
        if response.status_code in {401, 403}:
            raise ProviderPermanentError("FCS_API_MAIN_AUTH_FAILED")
        if response.status_code >= 400:
            raise RuntimeError(f"FCS_API_MAIN_HTTP_{response.status_code}")
        try:
            data = response.json()
        except Exception as exc:
            raise RuntimeError("FCS_API_MAIN_INVALID_JSON") from exc
        status_value = data.get("status") if isinstance(data, Mapping) else None
        if isinstance(status_value, str) and status_value.lower() in {"false", "error", "failed"}:
            msg = str(data.get("msg") or data.get("message") or "FCS_API_MAIN_STATUS_FAILED")
            upper = msg.upper()
            if "LIMIT" in upper or "RATE" in upper or "QUOTA" in upper:
                raise ProviderRateLimited("FCS_API_MAIN_RATE_LIMITED")
            if "KEY" in upper or "AUTH" in upper or "ACCESS" in upper:
                raise ProviderPermanentError("FCS_API_MAIN_AUTH_FAILED")
            raise RuntimeError("FCS_API_MAIN_RETURNED_FAILED_STATUS")
        raw_rows = []
        if isinstance(data, Mapping):
            for key in ("response", "data", "candles", "history"):
                value = data.get(key)
                if isinstance(value, list):
                    raw_rows = value
                    break
                if isinstance(value, Mapping):
                    raw_rows = list(value.values())
                    break
        if not raw_rows:
            raise RuntimeError("FCS_API_MAIN_RETURNED_EMPTY_CANDLES")
        rows = []
        for item in raw_rows:
            if not isinstance(item, Mapping):
                continue
            rows.append({
                "time": item.get("tm") or item.get("time") or item.get("date") or item.get("timestamp"),
                "open": item.get("o") or item.get("open"),
                "high": item.get("h") or item.get("high"),
                "low": item.get("l") or item.get("low"),
                "close": item.get("c") or item.get("close"),
                "volume": item.get("v") or item.get("volume") or 0,
            })
        frame = pd.DataFrame(rows)
        if "time" in frame.columns:
            numeric_time = pd.to_numeric(frame["time"], errors="coerce")
            if numeric_time.notna().mean() > 0.8:
                unit = "ms" if float(numeric_time.dropna().median()) > 10_000_000_000 else "s"
                frame["time"] = pd.to_datetime(numeric_time, errors="coerce", unit=unit, utc=True)
        metadata = {"provider_key_alias": "FCS_API_MAIN", "actual_key_name": "FCS_API_MAIN"}
        return frame, True, "FCS API main returned candle rows", metadata

    def _fetch_twelve(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        from core.connectors.data_parts.fetchers import fetch_twelve
        from core.twelve_data_key_pool import TwelveDataKeyPool

        # Pass the real runtime state object through. Converting Streamlit
        # SessionStateProxy to a dict here creates a per-thread copy, so every
        # parallel request starts with an empty key ledger and Key 1 is reused
        # until it rate-limits. The key pool itself handles read-only fallbacks.
        pool = TwelveDataKeyPool.from_state(state)
        assigned_alias = str(state.get("selector_owned_twelve_assigned_key_20260708") or state.get("twelve_assigned_key_alias_20260708") or "").strip().upper()
        if assigned_alias in {"KEY_1", "TWELVE_DATA_KEY_1", "TWELVE_API_KEY_1"}:
            assigned_alias = "TWELVE_KEY_1"
        if assigned_alias in {"KEY_2", "TWELVE_DATA_KEY_2", "TWELVE_API_KEY_2"}:
            assigned_alias = "TWELVE_KEY_2"
        lease = pool.reserve_alias(assigned_alias, symbol=symbol, timeframe=timeframe) if assigned_alias in {"TWELVE_KEY_1", "TWELVE_KEY_2"} else pool.reserve_key(symbol=symbol, timeframe=timeframe)
        if lease is None:
            snapshot = pool.status_snapshot()
            if assigned_alias in {"TWELVE_KEY_1", "TWELVE_KEY_2"}:
                info = snapshot.get(assigned_alias, {})
                if info.get("configured"):
                    raise ProviderRateLimited(f"{assigned_alias}_QUOTA_COOLDOWN")
                raise ProviderPermanentError(f"{assigned_alias}_NOT_CONFIGURED")
            configured = [alias for alias, info in snapshot.items() if info.get("configured")]
            if configured:
                raise ProviderRateLimited("ALL_TWELVE_KEYS_LIMITED")
            raise ProviderPermanentError("TWELVE_DATA_KEY_POOL_NOT_CONFIGURED")

        # Build H4 from genuine H1 rows. This avoids plan-specific 4h endpoint
        # restrictions while keeping one Twelve Data request and exact prices.
        interval = provider_interval_for(timeframe, TWELVE_POOL_PROVIDER)
        source_rows = (max(2, int(bars)) + 24) * (4 if timeframe == "H4" else 1)
        metadata = {
            "provider_key_alias": lease.alias,
            "actual_key_name": lease.alias,
            "masked_key": lease.masked_key,
            "remaining_before": lease.remaining_before,
            "remaining_after": lease.remaining_after,
            "selector_owned": bool(assigned_alias),
        }
        raw = fetch_twelve(provider_symbol, lease.api_key, interval=interval, bars=min(source_rows, 5000))
        ok = bool(isinstance(raw, tuple) and len(raw) >= 2 and raw[1])
        message = str(raw[2] if isinstance(raw, tuple) and len(raw) >= 3 else "")
        upper = message.upper()
        if not ok:
            if "429" in upper or "RATE" in upper or "QUOTA" in upper or "LIMIT" in upper:
                pool.mark_429(lease.alias, reason=message or f"{lease.alias}_RATE_LIMIT")
                raise ProviderRateLimited(f"{lease.alias.replace('TWELVE_', '')}_RATE_LIMIT: {message or 'HTTP 429'}")
            pool.mark_failure(lease.alias, message or "EMPTY_CANDLES")
            return raw[0] if isinstance(raw, tuple) and raw else None, False, message, metadata
        pool.mark_success(lease.alias)

        if timeframe != "H4":
            frame = raw[0]
            if isinstance(frame, pd.DataFrame):
                frame = frame.copy()
                frame["provider_key_alias"] = lease.alias
                return frame, True, f"{message} via {lease.alias}", metadata
            return raw[0], True, f"{message} via {lease.alias}", metadata
        frame = raw[0]
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            return raw[0], False, f"Twelve Data {lease.alias} returned empty H1 rows for H4 aggregation", metadata
        time_col = next((column for column in ("time", "datetime", "open_time") if column in frame.columns), None)
        if time_col is None:
            return frame, False, f"Twelve Data {lease.alias} H1 rows have no usable timestamp for H4 aggregation", metadata
        h4 = frame.copy()
        h4[time_col] = pd.to_datetime(h4[time_col], errors="coerce", utc=True)
        h4 = (
            h4.dropna(subset=[time_col, "open", "high", "low", "close"])
            .sort_values(time_col)
            .set_index(time_col)
            .resample("4h", origin="epoch", label="left", closed="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
            .rename(columns={time_col: "time"})
            .tail(max(2, int(bars)))
            .reset_index(drop=True)
        )
        h4["provider_key_alias"] = lease.alias
        return h4, True, f"Twelve Data key pool {lease.alias} connected 1h and aggregated to H4", metadata

    def _fetch_mt5(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        from core.connectors.data_parts.fetchers import fetch_mt5
        return fetch_mt5(provider_symbol, timeframe=timeframe, bars=bars)

    def _fetch_yahoo_finance(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        """Fetch a real keyless chart series as a cloud-safe live fallback.

        This route is intentionally below Finnhub and Twelve Data. It exists so
        a valid Finnhub news credential that lacks candle entitlement, or a
        temporarily rejected Twelve key, does not leave Settings at zero rows.
        No synthetic candles are created.
        """
        interval = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "1h", "D1": "1d",
        }[timeframe]
        seconds = {
            "M1": 60, "M5": 300, "M15": 900, "M30": 1800,
            "H1": 3600, "H4": 3600, "D1": 86400,
        }[timeframe]
        multiplier = 4 if timeframe == "H4" else 1
        requested_rows = max(2, int(bars))
        source_rows = (requested_rows + 32) * multiplier
        # Headroom covers weekends/closures. The minimum windows also respect
        # Yahoo's short intraday retention limits without asking for years of M1.
        minimum_window = {
            "M1": 7 * 86400,
            "M5": 30 * 86400,
            "M15": 60 * 86400,
            "M30": 60 * 86400,
            "H1": 120 * 86400,
            "H4": 220 * 86400,
            "D1": 4 * 365 * 86400,
        }[timeframe]
        end = int(time.time())
        start = end - max(minimum_window, int(source_rows * seconds * 1.8))
        params = {
            "interval": interval,
            "period1": start,
            "period2": end,
            "events": "history",
            "includeAdjustedClose": "true",
        }
        timeout = max(3.0, min(float(os.environ.get("YAHOO_FINANCE_TIMEOUT_SECONDS", "8")), 20.0))
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; ADX-Quant-Pro/2026.07)",
        }
        last_error = ""
        payload: dict[str, Any] | None = None
        for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
            try:
                response = self.session.get(
                    f"https://{host}/v8/finance/chart/{provider_symbol}",
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                if response.status_code == 429:
                    raise ProviderRateLimited("Yahoo Finance HTTP 429", float(response.headers.get("Retry-After") or 60))
                if response.status_code in (401, 403):
                    last_error = f"Yahoo Finance HTTP {response.status_code}"
                    continue
                response.raise_for_status()
                candidate = response.json()
                chart = candidate.get("chart") if isinstance(candidate, dict) else None
                error = chart.get("error") if isinstance(chart, dict) else None
                if error:
                    description = str(error.get("description") or error.get("code") or "chart error")
                    last_error = f"Yahoo Finance: {description[:140]}"
                    continue
                payload = candidate
                break
            except ProviderRateLimited:
                raise
            except requests.Timeout:
                last_error = "Yahoo Finance request timed out"
            except requests.RequestException as exc:
                last_error = f"Yahoo Finance network error: {type(exc).__name__}"
            except Exception as exc:
                last_error = f"Yahoo Finance response error: {type(exc).__name__}"
        if payload is None:
            raise RuntimeError(last_error or "Yahoo Finance returned no response")

        chart = payload.get("chart") or {}
        results = chart.get("result") or []
        if not results:
            raise RuntimeError("Yahoo Finance returned no chart result")
        result = results[0] if isinstance(results[0], dict) else {}
        timestamps = result.get("timestamp") or []
        indicators = result.get("indicators") or {}
        quotes = indicators.get("quote") or []
        quote = quotes[0] if quotes and isinstance(quotes[0], dict) else {}
        if not timestamps or not quote:
            raise RuntimeError("Yahoo Finance returned no candle rows")
        size = len(timestamps)
        def values(name: str) -> list[Any]:
            raw_values = quote.get(name)
            if not isinstance(raw_values, list):
                return [None] * size
            return (raw_values + [None] * size)[:size]
        frame = pd.DataFrame({
            "time": pd.to_datetime(timestamps, unit="s", errors="coerce", utc=True),
            "open": values("open"),
            "high": values("high"),
            "low": values("low"),
            "close": values("close"),
            "volume": values("volume"),
        }).dropna(subset=["time", "open", "high", "low", "close"])
        if frame.empty:
            raise RuntimeError("Yahoo Finance candle rows could not be normalized")
        if timeframe == "H4":
            frame = (
                frame.sort_values("time")
                .set_index("time")
                .resample("4h", origin="epoch", label="left", closed="left")
                .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                .dropna(subset=["open", "high", "low", "close"])
                .reset_index()
            )
        frame = frame.sort_values("time").tail(requested_rows).reset_index(drop=True)
        if len(frame) < 2:
            raise RuntimeError(f"Yahoo Finance returned only {len(frame)} usable candle row(s)")
        return frame

    def _fetch_finnhub(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        key = self._secret(state, "FINNHUB")
        if not key:
            raise ProviderPermanentError("FINNHUB_NOT_CONFIGURED")
        # Finnhub candle resolutions are 1/5/15/30/60/D/W/M.  H4 therefore
        # must be built from genuine H1 candles; requesting resolution=240
        # returns no data for the forex endpoint and caused every H4 selector
        # load to fall through all providers before failing.
        resolution = provider_interval_for(timeframe, "FINNHUB")
        source_seconds = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 3600, "D1": 86400}[timeframe]
        source_multiplier = 4 if timeframe == "H4" else 1
        endpoint = self._finnhub_candle_endpoint(symbol)
        # Calendar windows need headroom for weekends and exchange closures.
        # This requests genuine history only; no candle is generated or padded.
        calendar_multiplier = 1.15 if endpoint == "crypto/candle" else 1.65 if endpoint == "forex/candle" else 5.0
        source_rows = max(120, (max(2, int(bars)) + 24) * source_multiplier)
        end = int(time.time())
        start = end - int(source_rows * source_seconds * calendar_multiplier)
        response = self.session.get(
            f"https://finnhub.io/api/v1/{endpoint}",
            params={"symbol": provider_symbol, "resolution": resolution, "from": start, "to": end, "token": key},
            timeout=max(3.0, min(float(os.environ.get("FINNHUB_TIMEOUT_SECONDS", "8")), 20.0)),
        )
        if response.status_code == 429:
            raise ProviderRateLimited("Finnhub HTTP 429", float(response.headers.get("Retry-After") or 60))
        if response.status_code in (401, 403, 422):
            detail = ""
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    detail = str(payload.get("error") or payload.get("message") or "").strip()
            except Exception:
                detail = ""
            lower = detail.lower()
            if response.status_code == 401 or "invalid api key" in lower or "invalid token" in lower:
                raise ProviderPermanentError("Finnhub rejected the saved API key (HTTP 401)")
            if response.status_code == 403:
                raise ProviderPermanentError(
                    "Finnhub candle endpoint is unavailable for this account plan (HTTP 403)"
                    + (f": {detail[:100]}" if detail else "")
                )
            raise ProviderPermanentError(
                f"Finnhub rejected symbol/timeframe request (HTTP {response.status_code})"
                + (f": {detail[:100]}" if detail else "")
            )
        response.raise_for_status()
        data = response.json()
        if data.get("s") != "ok" or not data.get("t"):
            raise RuntimeError(f"Finnhub response status {data.get('s')}")
        frame = pd.DataFrame({
            "time": pd.to_datetime(data["t"], unit="s", utc=True),
            "open": data["o"], "high": data["h"], "low": data["l"],
            "close": data["c"], "volume": data.get("v", [None] * len(data["t"])),
        })
        if timeframe == "H4":
            frame = (
                frame.dropna(subset=["time", "open", "high", "low", "close"])
                .sort_values("time")
                .set_index("time")
                .resample("4h", origin="epoch", label="left", closed="left")
                .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
                .dropna(subset=["open", "high", "low", "close"])
                .reset_index()
            )
        return frame.tail(max(2, int(bars))).reset_index(drop=True)

    def _fetch_alpha_vantage(self, *, symbol: str, provider_symbol: str, timeframe: str, bars: int, state: Mapping[str, Any]) -> Any:
        key = self._secret(state, "ALPHA_VANTAGE")
        if not key:
            raise ProviderPermanentError("ALPHA_VANTAGE_NOT_CONFIGURED")
        if len(symbol) != 6 or not symbol.isalpha():
            raise ProviderPermanentError("Alpha Vantage fallback supports FX pairs only")
        interval = provider_interval_for(timeframe, "ALPHA_VANTAGE")
        response = self.session.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "FX_INTRADAY", "from_symbol": symbol[:3], "to_symbol": symbol[3:],
                "interval": interval, "outputsize": "full" if bars > 100 else "compact", "apikey": key,
            }, timeout=max(3.0, min(float(os.environ.get("ALPHA_VANTAGE_TIMEOUT_SECONDS", "10")), 25.0)),
        )
        if response.status_code == 429:
            raise ProviderRateLimited("Alpha Vantage HTTP 429", float(response.headers.get("Retry-After") or 60))
        response.raise_for_status()
        data = response.json()
        if "Note" in data or "Information" in data:
            raise ProviderRateLimited(str(data.get("Note") or data.get("Information")))
        key_name = next((name for name in data if "Time Series FX" in name), None)
        if not key_name:
            raise ProviderPermanentError(str(data.get("Error Message") or "Alpha Vantage missing FX time series"))
        rows = []
        for stamp, values in data[key_name].items():
            rows.append({
                "time": stamp, "open": values.get("1. open"), "high": values.get("2. high"),
                "low": values.get("3. low"), "close": values.get("4. close"), "volume": None,
            })
        frame = pd.DataFrame(rows).sort_values("time")
        if timeframe == "H4" and not frame.empty:
            frame["time"] = pd.to_datetime(frame["time"], errors="coerce", utc=True)
            frame = frame.set_index("time").resample("4h", label="left", closed="left").agg(
                {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
            ).dropna(subset=["open", "high", "low", "close"]).reset_index()
        return frame.tail(int(bars))



def is_valid_candle_df(df: Any, min_rows: int = 50, allow_stale: bool = False) -> bool:
    """Shared candle validation used by the canonical 12-symbol provider route."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    required_cols = ["open", "high", "low", "close"]
    for col in required_cols:
        if col not in df.columns:
            return False
    if len(df) < int(min_rows) and not allow_stale:
        return False
    if df[required_cols].isna().all().any():
        return False
    return True


def first_valid_df(*dfs: Any) -> pd.DataFrame:
    """Return the first non-empty DataFrame without Boolean-evaluating pandas objects."""
    for df in dfs:
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            return df
    return pd.DataFrame()


def fetch_forex_candles_provider_chain(
    symbol: Any,
    timeframe: Any,
    outputsize: int = 600,
    state: Mapping[str, Any] | None = None,
    *,
    force_live: bool = False,
    db_path: str | Path | None = None,
) -> tuple[pd.DataFrame, str, dict[str, Any]]:
    """Cache → Twelve Data key pool → Finnhub candles → last-known valid cache."""
    state_map = state if isinstance(state, Mapping) else {}
    canonical_symbol = normalize_symbol(symbol)
    tf = normalize_timeframe(timeframe)
    trace: dict[str, Any] = {
        "symbol": canonical_symbol,
        "timeframe": tf,
        "twelve_attempted": False,
        "twelve_error": None,
        "actual_key_name": None,
        "provider_key_alias": None,
        "finnhub_attempted": False,
        "finnhub_error": None,
        "cache_used": False,
        "provider_used": None,
    }
    orchestrator = MarketDataOrchestrator(db_path=db_path)
    result = orchestrator.fetch(
        symbol=canonical_symbol,
        timeframe=tf,
        state=state_map,
        bars=int(outputsize),
        run_id=str(state_map.get("canonical_last_load_run_id") or ""),
        force_live=bool(force_live),
    )
    for attempt in result.attempts:
        provider = canonical_provider_name(attempt.get("provider"))
        ok = bool(attempt.get("ok"))
        message = str(attempt.get("message") or attempt.get("category") or "").strip()
        if provider == TWELVE_POOL_PROVIDER:
            trace["twelve_attempted"] = True
            trace["actual_key_name"] = attempt.get("actual_key_name") or attempt.get("provider_key_alias") or trace.get("actual_key_name")
            trace["provider_key_alias"] = trace["actual_key_name"]
            if not ok:
                trace["twelve_error"] = message or trace["twelve_error"]
        elif provider == "FINNHUB":
            trace["finnhub_attempted"] = True
            if not ok:
                trace["finnhub_error"] = message or trace["finnhub_error"]
    provider_used = canonical_provider_name(result.provider)
    if provider_used in {"LOCAL_VALID_CACHE", "CACHE", "SQLITE"}:
        trace["cache_used"] = True
        trace["provider_used"] = "LOCAL_CACHE"
        return result.frame, "CACHE_SUCCESS" if result.status == "CACHED_VALID" else "EMERGENCY_CACHE_SUCCESS", trace
    if provider_used == TWELVE_POOL_PROVIDER and is_valid_candle_df(result.frame, min_rows=25, allow_stale=True):
        trace["provider_used"] = TWELVE_POOL_PROVIDER
        trace["actual_key_name"] = result.provider_key_alias or trace.get("actual_key_name")
        trace["provider_key_alias"] = trace["actual_key_name"]
        return result.frame, "TWELVE_SUCCESS", trace
    if provider_used == "FINNHUB" and is_valid_candle_df(result.frame, min_rows=25, allow_stale=True):
        trace["provider_used"] = "FINNHUB"
        return result.frame, "FINNHUB_SUCCESS", trace
    if is_valid_candle_df(result.frame, min_rows=25, allow_stale=True):
        trace["provider_used"] = "LAST_KNOWN_VALID_CACHE"
        return result.frame, "EMERGENCY_CACHE_SUCCESS", trace
    trace["provider_used"] = "NONE"
    return pd.DataFrame(), "FAILED_NO_DATA", trace


def test_twelve_key_pool_connection(state: Mapping[str, Any] | None = None, *, session: requests.Session | None = None, db_path: str | Path | None = None) -> dict[str, Any]:
    """Settings-tab two-key Twelve Data authentication/status test."""
    from core.twelve_data_key_pool import TwelveDataKeyPool, test_twelve_data_key
    state_map = state if isinstance(state, Mapping) else {}
    # Keep the original state object for the key pool. Some Streamlit runtimes
    # expose SessionStateProxy as get/__setitem__ without MutableMapping, and a
    # throw-away dict here hides both saved keys and per-key counters.
    pool_state = state
    results = {
        "connected": False,
        "status": "FAILED",
        "keys": {},
        "available_symbols_status": "NOT_CHECKED",
        "api_response_time_ms": None,
        "error_message": "",
    }
    total_ms = 0
    for alias in ("TWELVE_KEY_1", "TWELVE_KEY_2"):
        key_result = test_twelve_data_key(pool_state, alias=alias)
        results["keys"][alias] = key_result
        if key_result.get("api_response_time_ms") is not None:
            total_ms += int(key_result.get("api_response_time_ms") or 0)
    snapshot = TwelveDataKeyPool.from_state(pool_state).status_snapshot()
    connected = any(bool(item.get("connected")) for item in results["keys"].values())
    results.update({
        "connected": connected,
        "status": "CONNECTED" if connected else "FAILED",
        "available_symbols_status": "CHECKED_BY_EURUSD_1MIN_SAMPLE" if connected else "NO_KEY_CONNECTED",
        "api_response_time_ms": total_ms or None,
        "key_pool_status": snapshot,
    })
    if not connected:
        results["error_message"] = "; ".join(
            f"{alias}: {item.get('error_message') or item.get('status')}" for alias, item in results["keys"].items()
        )[:240]
    try:
        from core.connectors.credential_vault import mark_connection
        for alias, item in results["keys"].items():
            mark_connection(alias, connected=bool(item.get("connected")), configured=item.get("masked_key") != "NOT_CONFIGURED", status=str(item.get("status") or "FAILED"), error_code=str(item.get("error_message") or ""))
    except Exception:
        pass
    return results

__all__ = [
    "PROVIDER_PRIORITY", "CONNECTOR_PROVIDER_PRIORITY", "PROVIDER_TIMEFRAME_MAP",
    "provider_priority_for_state", "provider_interval_for", "STATUS_BY_PROVIDER", "MarketDataResult",
    "ProviderPermanentError", "ProviderRateLimited", "MarketDataOrchestrator",
    "is_valid_candle_df", "first_valid_df", "fetch_forex_candles_provider_chain",
    "test_twelve_key_pool_connection", "SymbolLevelProviderRegistry", "normalize_provider_state",
]
