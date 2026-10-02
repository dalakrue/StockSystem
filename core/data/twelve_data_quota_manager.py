"""Persistent Twelve Data quota guard.

The guard reserves capacity before a request. It does not attempt to evade
provider limits and never stores credentials.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import hashlib
import random
import sqlite3
import time

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema


@dataclass(frozen=True)
class QuotaStatus:
    minute_limit: float
    safe_minute_limit: float
    credits_used_last_60_seconds: float
    estimated_credits_remaining: float
    daily_limit: float
    daily_safe_limit: float
    estimated_daily_used: float
    daily_remaining: float
    emergency_reserve: float
    next_safe_request_time: str | None
    rate_limited: bool
    last_429_time: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TwelveDataQuotaManager:
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        minute_limit: float = 8,
        safe_minute_limit: float = 6,
        daily_limit: float = 800,
        daily_safe_limit: float = 700,
        emergency_reserve: float = 2,
        clock: Any = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.minute_limit = float(minute_limit)
        self.safe_minute_limit = min(float(safe_minute_limit), self.minute_limit)
        self.daily_limit = float(daily_limit)
        self.daily_safe_limit = min(float(daily_safe_limit), self.daily_limit)
        self.emergency_reserve = max(0.0, float(emergency_reserve))
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        migrate_deployment_schema(self.db_path)

    def _now(self) -> datetime:
        value = self._clock()
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15)
        conn.execute("PRAGMA busy_timeout=10000")
        return conn

    def _recent_rows(self, now: datetime) -> list[tuple[float, str]]:
        cutoff = (now - timedelta(seconds=60)).isoformat()
        with self._connection() as conn:
            rows = conn.execute(
                """SELECT request_cost,requested_at FROM api_request_ledger
                   WHERE provider='TWELVE_DATA' AND requested_at>? AND response_status NOT IN ('RELEASED','REJECTED')
                   ORDER BY requested_at""",
                (cutoff,),
            ).fetchall()
        return [(float(row[0] or 0), str(row[1])) for row in rows]

    def _daily_used(self, now: datetime) -> float:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT estimated_used FROM daily_quota_usage WHERE provider='TWELVE_DATA' AND usage_day=?",
                (now.date().isoformat(),),
            ).fetchone()
        return float(row[0] or 0) if row else 0.0

    def status(self) -> QuotaStatus:
        now = self._now()
        recent = self._recent_rows(now)
        used = sum(cost for cost, _ in recent)
        daily_used = self._daily_used(now)
        with self._connection() as conn:
            row = conn.execute(
                "SELECT last_429_at,retry_after_seconds FROM provider_health WHERE provider='TWELVE_DATA'"
            ).fetchone()
        last_429 = str(row[0]) if row and row[0] else None
        retry_after = float(row[1] or 0) if row else 0.0
        rate_limited = False
        if last_429:
            try:
                rate_limited = self._now() < datetime.fromisoformat(last_429) + timedelta(seconds=retry_after)
            except Exception:
                rate_limited = False
        next_safe = None
        if used >= self.safe_minute_limit and recent:
            try:
                oldest = datetime.fromisoformat(recent[0][1])
                next_safe = (oldest + timedelta(seconds=60)).isoformat()
            except Exception:
                pass
        if rate_limited and last_429:
            next_safe = (datetime.fromisoformat(last_429) + timedelta(seconds=retry_after)).isoformat()
        return QuotaStatus(
            minute_limit=self.minute_limit,
            safe_minute_limit=self.safe_minute_limit,
            credits_used_last_60_seconds=round(used, 4),
            estimated_credits_remaining=round(max(0.0, self.safe_minute_limit - used), 4),
            daily_limit=self.daily_limit,
            daily_safe_limit=self.daily_safe_limit,
            estimated_daily_used=round(daily_used, 4),
            daily_remaining=round(max(0.0, self.daily_safe_limit - daily_used), 4),
            emergency_reserve=self.emergency_reserve,
            next_safe_request_time=next_safe,
            rate_limited=rate_limited,
            last_429_time=last_429,
        )

    def can_request(self, cost: float = 1, *, essential: bool = False) -> tuple[bool, str, QuotaStatus]:
        cost = max(0.0, float(cost))
        status = self.status()
        if status.rate_limited:
            return False, "RATE_LIMIT_COOLDOWN", status
        minute_ceiling = self.minute_limit if essential else self.safe_minute_limit
        daily_ceiling = self.daily_limit if essential else self.daily_safe_limit
        if status.credits_used_last_60_seconds + cost > minute_ceiling:
            return False, "ROLLING_MINUTE_SAFETY_LIMIT", status
        if status.estimated_daily_used + cost > daily_ceiling:
            return False, "DAILY_SAFETY_LIMIT", status
        return True, "ALLOWED", status

    def reserve(
        self,
        *,
        cost: float = 1,
        endpoint_category: str = "TIME_SERIES",
        run_id: str = "",
        symbol: str = "",
        timeframe: str = "H1",
        essential: bool = False,
    ) -> dict[str, Any]:
        allowed, reason, before = self.can_request(cost, essential=essential)
        if not allowed:
            return {"allowed": False, "reason": reason, "quota": before.to_dict()}
        now = self._now()
        request_id = hashlib.sha256(
            f"TWELVE_DATA|{now.isoformat()}|{run_id}|{symbol}|{timeframe}|{random.random()}".encode()
        ).hexdigest()
        symbol_hash = hashlib.sha256(str(symbol).upper().encode()).hexdigest() if symbol else None
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            # Recheck under the write lock so concurrent sessions cannot overbook.
            cutoff = (now - timedelta(seconds=60)).isoformat()
            used = float(conn.execute(
                """SELECT COALESCE(SUM(request_cost),0) FROM api_request_ledger
                   WHERE provider='TWELVE_DATA' AND requested_at>? AND response_status NOT IN ('RELEASED','REJECTED')""",
                (cutoff,),
            ).fetchone()[0] or 0)
            day = now.date().isoformat()
            daily = float(conn.execute(
                "SELECT COALESCE(estimated_used,0) FROM daily_quota_usage WHERE provider='TWELVE_DATA' AND usage_day=?",
                (day,),
            ).fetchone()[0] or 0) if conn.execute(
                "SELECT 1 FROM daily_quota_usage WHERE provider='TWELVE_DATA' AND usage_day=?", (day,)
            ).fetchone() else 0.0
            minute_ceiling = self.minute_limit if essential else self.safe_minute_limit
            daily_ceiling = self.daily_limit if essential else self.daily_safe_limit
            if used + cost > minute_ceiling or daily + cost > daily_ceiling:
                conn.rollback()
                return {"allowed": False, "reason": "CONCURRENT_QUOTA_RECHECK_FAILED", "quota": self.status().to_dict()}
            conn.execute(
                """INSERT INTO api_request_ledger(
                    request_id,provider,endpoint_category,request_cost,requested_at,response_status,
                    retry_count,run_id,symbol_hash,timeframe) VALUES(?,?,?,?,?,'RESERVED',0,?,?,?)""",
                (request_id, "TWELVE_DATA", endpoint_category, float(cost), now.isoformat(), run_id, symbol_hash, str(timeframe).upper()),
            )
            conn.execute(
                """INSERT INTO daily_quota_usage(provider,usage_day,estimated_used,emergency_used,updated_at)
                   VALUES('TWELVE_DATA',?,?,?,?)
                   ON CONFLICT(provider,usage_day) DO UPDATE SET
                   estimated_used=daily_quota_usage.estimated_used+excluded.estimated_used,
                   emergency_used=daily_quota_usage.emergency_used+excluded.emergency_used,
                   updated_at=excluded.updated_at""",
                (day, float(cost), float(cost) if essential and daily >= self.daily_safe_limit else 0.0, now.isoformat()),
            )
            conn.commit()
        return {"allowed": True, "request_id": request_id, "reason": reason, "quota": self.status().to_dict()}

    def complete(self, request_id: str, *, response_status: str, http_status: int | None = None, retry_count: int = 0) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE api_request_ledger SET response_status=?,http_status=?,retry_count=? WHERE request_id=?",
                (str(response_status), http_status, int(retry_count), str(request_id)),
            )
            conn.commit()

    def release(self, request_id: str) -> None:
        """Release a reservation only when no provider request was sent."""
        now = self._now()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT request_cost,requested_at FROM api_request_ledger WHERE request_id=? AND response_status='RESERVED'",
                (str(request_id),),
            ).fetchone()
            if not row:
                return
            cost = float(row[0] or 0)
            usage_day = datetime.fromisoformat(str(row[1])).date().isoformat()
            conn.execute("UPDATE api_request_ledger SET response_status='RELEASED' WHERE request_id=?", (str(request_id),))
            conn.execute(
                """UPDATE daily_quota_usage SET estimated_used=MAX(0,estimated_used-?),updated_at=?
                   WHERE provider='TWELVE_DATA' AND usage_day=?""",
                (cost, now.isoformat(), usage_day),
            )
            conn.commit()

    def record_429(self, *, retry_after: float | None = None) -> None:
        now = self._now()
        wait = max(1.0, float(retry_after or 60.0))
        with self._connection() as conn:
            conn.execute(
                """INSERT INTO provider_health(provider,status,healthy,last_failure_at,last_429_at,retry_after_seconds,updated_at)
                   VALUES('TWELVE_DATA','RATE_LIMITED',0,?,?,?,?)
                   ON CONFLICT(provider) DO UPDATE SET status='RATE_LIMITED',healthy=0,
                   last_failure_at=excluded.last_failure_at,last_429_at=excluded.last_429_at,
                   retry_after_seconds=excluded.retry_after_seconds,updated_at=excluded.updated_at""",
                (now.isoformat(), now.isoformat(), wait, now.isoformat()),
            )
            conn.commit()

    @staticmethod
    def backoff_seconds(attempt: int, retry_after: float | None = None) -> float:
        if retry_after is not None:
            return max(0.0, min(float(retry_after), 120.0))
        attempt = max(0, int(attempt))
        return min(30.0, (2 ** attempt) + random.uniform(0.1, 0.8))

    def bounded_retry(self, operation: Any, *, max_retries: int = 2, retry_after: float | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(max(0, int(max_retries)) + 1):
            try:
                return operation(attempt)
            except Exception as exc:  # caller must raise only retryable failures
                last_error = exc
                if attempt >= max_retries:
                    break
                time.sleep(self.backoff_seconds(attempt, retry_after))
        if last_error:
            raise last_error
        raise RuntimeError("Quota retry operation did not execute")


__all__ = ["QuotaStatus", "TwelveDataQuotaManager"]
