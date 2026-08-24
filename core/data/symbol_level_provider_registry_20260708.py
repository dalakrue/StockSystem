"""Symbol-level provider health registry for the foreground 12-symbol loader.

The registry is intentionally lightweight and SQLite-backed so Streamlit reruns,
failed requests, and reload-only actions retain symbol/timeframe/provider health.
It implements the requested research-inspired control logic without replacing
trading calculations: provider state, adaptive score, and a temporary circuit
breaker are updated after every symbol request.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import sqlite3

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema

TERMINAL_BAD_STATES = {"AUTH_FAILED"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_provider_state(value: Any) -> str:
    text = str(value or "").upper().strip()
    if any(token in text for token in ("AUTH", "401", "403", "KEY", "UNAUTHORIZED")):
        return "AUTH_FAILED"
    if any(token in text for token in ("RATE", "429", "QUOTA", "LIMIT")):
        return "RATE_LIMITED"
    if any(token in text for token in ("TIMEOUT", "CONNECTION", "NETWORK", "503", "504")):
        return "TIMEOUT"
    if any(token in text for token in ("EMPTY", "NO COMPLETE", "NO USABLE", "NO VALID")):
        return "EMPTY_DATA"
    if any(token in text for token in ("STALE", "CACHE")):
        return "STALE_CACHE_ONLY"
    if text in {"DISABLED", "RUN_CIRCUIT_OPEN", "CIRCUIT_OPEN"}:
        return "DISABLED"
    if text in {"SUCCESS", "CONNECTED", "VALID", "HEALTHY", "COMPLETED"}:
        return "HEALTHY"
    return text or "EMPTY_DATA"


@dataclass(frozen=True)
class ProviderScore:
    provider: str
    symbol: str
    timeframe: str
    live_state: str
    score: float
    circuit_open: bool
    attempts: int
    successes: int
    failures: int
    last_error: str = ""


class SymbolLevelProviderRegistry:
    """Persist provider health per provider + symbol + timeframe."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.execute("PRAGMA busy_timeout=15000")
        return conn

    def get_score(self, provider: str, symbol: str, timeframe: str) -> ProviderScore:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """SELECT provider,symbol,timeframe,live_state,score,circuit_open,
                          attempts,successes,failures,last_error
                   FROM symbol_provider_health_20260708
                   WHERE provider=? AND symbol=? AND timeframe=?""",
                (str(provider).upper(), str(symbol).upper(), str(timeframe).upper()),
            ).fetchone()
        if row:
            return ProviderScore(
                provider=str(row["provider"]), symbol=str(row["symbol"]), timeframe=str(row["timeframe"]),
                live_state=str(row["live_state"]), score=float(row["score"] or 0.5),
                circuit_open=bool(row["circuit_open"]), attempts=int(row["attempts"] or 0),
                successes=int(row["successes"] or 0), failures=int(row["failures"] or 0),
                last_error=str(row["last_error"] or ""),
            )
        return ProviderScore(str(provider).upper(), str(symbol).upper(), str(timeframe).upper(), "HEALTHY", 0.50, False, 0, 0, 0, "")

    def circuit_open(self, provider: str, symbol: str, timeframe: str) -> bool:
        score = self.get_score(provider, symbol, timeframe)
        if score.circuit_open:
            return True
        # Provider-wide circuit is only for real authentication/configuration
        # failures. Rate-limit and timeout states are per-key/per-request
        # transient conditions handled by quota pacing and reload; making them
        # provider-wide caused later symbols to be skipped as RUN_CIRCUIT_OPEN.
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) FROM symbol_provider_health_20260708
                   WHERE provider=? AND live_state='AUTH_FAILED'
                     AND circuit_open=1""",
                (str(provider).upper(),),
            ).fetchone()
        return bool(row and int(row[0] or 0) > 0)

    def record_attempt(
        self,
        *,
        provider: str,
        symbol: str,
        timeframe: str,
        ok: bool,
        rows: int = 0,
        response_time_ms: float | None = None,
        error_code: str = "",
        error_message: str = "",
        coverage_ratio: float | None = None,
    ) -> ProviderScore:
        provider = str(provider or "UNKNOWN").upper()
        symbol = str(symbol or "").upper()
        timeframe = str(timeframe or "H4").upper()
        previous = self.get_score(provider, symbol, timeframe)
        attempts = previous.attempts + 1
        successes = previous.successes + (1 if ok else 0)
        failures = previous.failures + (0 if ok else 1)
        state = "HEALTHY" if ok else normalize_provider_state(error_code or error_message)
        response_penalty = min(0.35, max(0.0, float(response_time_ms or 0.0) / 30000.0))
        row_bonus = min(0.25, max(0.0, int(rows or 0) / 600.0) * 0.25)
        coverage_bonus = min(0.25, max(0.0, float(coverage_ratio if coverage_ratio is not None else 0.0)) * 0.25)
        success_rate = successes / max(1, attempts)
        score = max(0.0, min(1.0, 0.15 + 0.55 * success_rate + row_bonus + coverage_bonus - response_penalty))
        # Do not circuit-break rate-limit/timeout/temporary data failures.
        # Those must remain retryable by the foreground reload controls. Keep a
        # circuit only for authentication/config errors and repeated exact-symbol
        # empty data, both bypassable by orchestrator force_live.
        repeated_hard_failure = (not ok) and state in TERMINAL_BAD_STATES and failures >= 1
        repeated_empty = (not ok) and state in {"EMPTY_DATA", "EMPTY_CANDLES"} and failures >= 2
        circuit = bool(repeated_hard_failure or repeated_empty)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO symbol_provider_health_20260708(
                       provider,symbol,timeframe,live_state,score,circuit_open,attempts,successes,failures,
                       last_success_at,last_failure_at,last_error,median_response_ms,last_rows,last_coverage_ratio,updated_at
                   ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider,symbol,timeframe) DO UPDATE SET
                       live_state=excluded.live_state,score=excluded.score,circuit_open=excluded.circuit_open,
                       attempts=excluded.attempts,successes=excluded.successes,failures=excluded.failures,
                       last_success_at=CASE WHEN excluded.successes>symbol_provider_health_20260708.successes THEN excluded.last_success_at ELSE symbol_provider_health_20260708.last_success_at END,
                       last_failure_at=CASE WHEN excluded.failures>symbol_provider_health_20260708.failures THEN excluded.last_failure_at ELSE symbol_provider_health_20260708.last_failure_at END,
                       last_error=excluded.last_error,median_response_ms=excluded.median_response_ms,
                       last_rows=excluded.last_rows,last_coverage_ratio=excluded.last_coverage_ratio,updated_at=excluded.updated_at""",
                (
                    provider, symbol, timeframe, state, score, int(circuit), attempts, successes, failures,
                    now if ok else previous.__dict__.get('last_success_at'), now if not ok else None,
                    str(error_message or error_code or "")[:300], float(response_time_ms or 0.0), int(rows or 0),
                    float(coverage_ratio or 0.0), now,
                ),
            )
            conn.commit()
        return self.get_score(provider, symbol, timeframe)

    def reset_circuit(self, *, provider: str | None = None, symbol: str | None = None, timeframe: str | None = None) -> int:
        """Clear local circuit flags without deleting audit history.

        Used by explicit reload/force-refresh actions so the user button makes
        a fresh provider decision. This does not reset Twelve Data key-pool
        counters or cooldowns.
        """
        clauses: list[str] = ["circuit_open=1"]
        params: list[Any] = []
        if provider:
            clauses.append("provider=?")
            params.append(str(provider).upper())
        if symbol:
            clauses.append("symbol=?")
            params.append(str(symbol).upper())
        if timeframe:
            clauses.append("timeframe=?")
            params.append(str(timeframe).upper())
        now = _now()
        with self._connect() as conn:
            cur = conn.execute(
                f"""UPDATE symbol_provider_health_20260708
                    SET circuit_open=0, live_state=CASE WHEN live_state='AUTH_FAILED' THEN live_state ELSE 'HEALTHY' END,
                        updated_at=?
                    WHERE {' AND '.join(clauses)}""",
                (now, *params),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def provider_board(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT provider,symbol,timeframe,live_state,score,circuit_open,attempts,successes,failures,
                          last_success_at,last_failure_at,last_error,median_response_ms,last_rows,last_coverage_ratio,updated_at
                   FROM symbol_provider_health_20260708
                   ORDER BY updated_at DESC LIMIT 200"""
            ).fetchall()
        return [dict(row) for row in rows]


__all__ = ["ProviderScore", "SymbolLevelProviderRegistry", "normalize_provider_state"]
