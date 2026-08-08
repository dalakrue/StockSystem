"""Quota-aware scheduler for selected symbols.

Normal render-time reads remain cache-first and non-blocking. During an explicit
Settings-owned calculation transaction, optional quota-safe pacing can process
a bounded live-provider batch, wait for the next request window, and then
continue until every selected symbol has either a complete validated series or
an explicit unresolved status.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Sequence
import time

import pandas as pd

from core.data.candle_repository import CandleRepository
from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH
from core.data.market_data_orchestrator import MarketDataOrchestrator, MarketDataResult, provider_priority_for_state
from core.runtime_selection_20260705 import latest_completed_candle, normalize_symbols, normalize_symbol, normalize_timeframe


@dataclass(frozen=True)
class ScheduleItem:
    symbol: str
    timeframe: str
    needs_update: bool
    missing_data: bool
    latest_completed_candle: str | None
    expected_completed_candle: str
    active_session_relevance: int
    field10_priority: float
    active_symbol: bool
    reason: str


class MultiSymbolScheduler:
    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        orchestrator: MarketDataOrchestrator | None = None,
        max_live_requests_per_window: int = 6,
        max_m1_validation_symbols: int = 4,
        settlement_delay_minutes: int = 3,
        allow_emergency_reserve: bool = False,
        sleep_fn: Callable[[float], None] | None = None,
        clock_fn: Callable[[], float] | None = None,
    ) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.repository = CandleRepository(self.db_path)
        self.orchestrator = orchestrator or MarketDataOrchestrator(db_path=self.db_path)
        self.max_live_requests_per_window = max(1, int(max_live_requests_per_window))
        self.max_m1_validation_symbols = max(1, int(max_m1_validation_symbols))
        self.settlement_delay_minutes = max(0, int(settlement_delay_minutes))
        self.allow_emergency_reserve = bool(allow_emergency_reserve)
        self._sleep = sleep_fn or time.sleep
        self._clock = clock_fn or time.monotonic

    @staticmethod
    def _session_relevance(symbol: str, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        hour = now.hour
        currencies = {symbol[:3], symbol[3:6]} if len(symbol) == 6 else set()
        score = 0
        if 0 <= hour < 9 and currencies & {"JPY", "AUD", "NZD"}:
            score += 3
        if 7 <= hour < 16 and currencies & {"EUR", "GBP", "CHF"}:
            score += 3
        if 12 <= hour < 21 and currencies & {"USD", "CAD"}:
            score += 3
        return score

    def plan(
        self,
        symbols: Sequence[Any],
        timeframe: Any,
        *,
        active_symbol: Any | None = None,
        field10_priorities: Mapping[str, Any] | None = None,
    ) -> list[ScheduleItem]:
        selected = normalize_symbols(symbols)
        tf = normalize_timeframe(timeframe)
        expected = latest_completed_candle(
            timeframe=tf, settlement_delay_minutes=self.settlement_delay_minutes
        )
        active = normalize_symbol(active_symbol or (selected[0] if selected else "EURUSD"))
        priorities = field10_priorities if isinstance(field10_priorities, Mapping) else {}
        items: list[ScheduleItem] = []
        for symbol in selected:
            latest = self.repository.latest(symbol, tf)
            latest_text = str(latest.get("broker_open_time")) if latest else None
            missing = latest is None
            needs = self.repository.missing_from(symbol, tf, expected)
            reason = "MISSING_HISTORY" if missing else "LATEST_CANDLE_MISSING" if needs else "CURRENT_VALID_CACHE"
            items.append(ScheduleItem(
                symbol=symbol, timeframe=tf, needs_update=needs, missing_data=missing,
                latest_completed_candle=latest_text,
                expected_completed_candle=expected.isoformat(),
                active_session_relevance=self._session_relevance(symbol),
                field10_priority=float(priorities.get(symbol) or 0),
                active_symbol=symbol == active, reason=reason,
            ))
        # Missing first, then oldest, active session, current Field 10 priority,
        # and active symbol. Stable selected order is the final tie breaker.
        position = {symbol: idx for idx, symbol in enumerate(selected)}
        return sorted(
            items,
            key=lambda item: (
                not item.missing_data,
                not item.needs_update,
                item.latest_completed_candle or "",
                -item.active_session_relevance,
                -item.field10_priority,
                not item.active_symbol,
                position[item.symbol],
            ),
        )

    def run(
        self,
        *,
        symbols: Sequence[Any],
        timeframe: Any,
        state: MutableMapping[str, Any] | Mapping[str, Any] | None = None,
        active_symbol: Any | None = None,
        field10_priorities: Mapping[str, Any] | None = None,
        bars: int = 600,
        run_id: str = "",
        force_live: bool = False,
        progress_callback: Any = None,
    ) -> dict[str, Any]:
        plan = self.plan(symbols, timeframe, active_symbol=active_symbol, field10_priorities=field10_priorities)
        results: dict[str, dict[str, Any]] = {}
        live_started = 0
        deferred: list[str] = []
        total = max(1, len(plan))
        state_map = state if isinstance(state, Mapping) else {}
        explicit_stagger = bool(state_map.get("quota_safe_stagger_enabled_20260706", False))
        provider_plan = provider_priority_for_state(state_map)
        primary_provider = str(provider_plan[0] if provider_plan else "TWELVE_DATA_KEY_POOL").upper()
        # A one-click selected-universe run must not silently stop at the first
        # provider window merely because a transient UI flag was lost on a
        # Streamlit rerun.  Auto-enable compliant pacing only for explicit runs
        # that can exceed the configured rolling request budget.
        likely_live_count = sum(1 for item in plan if force_live or item.needs_update or item.missing_data)
        # Twelve Data pacing must never delay a Finnhub-primary load.  The old
        # auto-enable branch turned pacing back on for 8+ symbols even after the
        # selector explicitly disabled it, causing 60-second sleeps before
        # Finnhub was contacted. Twelve fallback requests remain protected by
        # the persistent quota reservation inside MarketDataOrchestrator.fetch.
        stagger_enabled = bool(
            explicit_stagger
            or (
                primary_provider in {"TWELVE_DATA", "TWELVE_DATA_FALLBACK", "TWELVE_DATA_KEY_POOL"}
                and len(plan) > self.max_live_requests_per_window
                and likely_live_count > self.max_live_requests_per_window
            )
        )
        batch_size = max(1, int(state_map.get("quota_safe_batch_size_20260706", self.max_live_requests_per_window) or self.max_live_requests_per_window))
        interval_seconds = max(1.0, float(state_map.get("quota_safe_batch_interval_seconds_20260706", 60.0) or 60.0))
        window_started = self._clock()
        live_attempts_in_window = 0
        pause_count = 0
        paced_wait_seconds = 0.0
        run_started = self._clock()
        full_range_progress = bool(state_map.get("market_data_progress_full_range_20260708", False))
        disabled_providers: set[str] = set()

        def publish(index: int, item: ScheduleItem, stage: str, result: MarketDataResult | None = None) -> None:
            if not callable(progress_callback):
                return
            if full_range_progress:
                percent = min(96.0, 4.0 + (92.0 * max(0, index) / total))
            else:
                percent = min(18.0, 2.0 + (16.0 * max(0, index) / total))
            payload: dict[str, Any] = {
                "overall_percent": round(percent, 1),
                "current_symbol": item.symbol,
                "current_stage": stage,
                "completed_symbols": max(0, min(index, total)),
                "total_symbols": total,
                "elapsed_seconds": round(max(0.0, self._clock() - run_started), 2),
            }
            if result is not None:
                payload["provider_status"] = result.status
                payload["provider"] = result.provider
            progress_callback(payload)

        def safe_fetch(item: ScheduleItem, *, requested_force_live: bool) -> MarketDataResult:
            fetch_kwargs = {
                "symbol": item.symbol,
                "timeframe": item.timeframe,
                "state": state,
                "bars": bars,
                "run_id": run_id,
                "force_live": requested_force_live,
                "essential": bool(self.allow_emergency_reserve and item.missing_data and item.active_symbol),
            }
            try:
                try:
                    result = self.orchestrator.fetch(
                        **fetch_kwargs, disabled_providers=disabled_providers,
                    )
                except TypeError as exc:
                    # Preserve compatibility with repository-local/custom test
                    # orchestrators that implement the older fetch signature.
                    # Only retry when the new optional keyword is the cause; all
                    # other TypeErrors remain isolated as real symbol failures.
                    if "disabled_providers" not in str(exc):
                        raise
                    result = self.orchestrator.fetch(**fetch_kwargs)
                # Run-scoped circuit breaker: after one authentication/config
                # failure or one transport timeout, do not repeat the same slow
                # failure for every remaining symbol. Symbol-specific invalid
                # data/422 responses do not open the circuit.
                for attempt in result.attempts:
                    provider = str(attempt.get("provider") or "").upper()
                    category = str(attempt.get("category") or "").upper()
                    message = str(attempt.get("message") or "").upper()
                    global_auth_failure = category == "PERMANENT_CLIENT_ERROR" and any(
                        token in message for token in ("NOT_CONFIGURED", "HTTP 401", "HTTP 403", "API KEY", "UNAUTHORIZED")
                    )
                    # Do not open a run-wide circuit for temporary/rate-limit
                    # market-data failures. With the Twelve Data key pool this
                    # was the visible 7/12 bug: after a bounded hard failure,
                    # remaining symbols were skipped as RUN_CIRCUIT_OPEN instead
                    # of being paced to another key/window or retried by the
                    # explicit reload button. Only true auth/config failures are
                    # run-wide, because retrying those for every symbol wastes
                    # credits and cannot succeed without changing credentials.
                    if provider and global_auth_failure:
                        disabled_providers.add(provider)
                return result
            except Exception as exc:
                # One unexpected provider/normalization failure must never abort
                # the other selected symbols. Reuse any validated cache first.
                cached = self.repository.load(item.symbol, item.timeframe, limit=bars, completed_only=True)
                if not cached.empty:
                    result = self.orchestrator._cached_result(
                        item.symbol, item.timeframe, cached, run_id=run_id, current=False,
                    )
                    result.message = (
                        f"Unexpected live-provider failure isolated for {item.symbol}; "
                        "validated local cache reused."
                    )
                    result.attempts = [{
                        "provider": "ORCHESTRATOR", "ok": False,
                        "category": "UNEXPECTED_SYMBOL_FAILURE",
                        "message": f"{type(exc).__name__}: {str(exc)[:180]}",
                    }]
                    result.fallback_provider = "LOCAL_VALID_CACHE"
                    return result
                return MarketDataResult(
                    ok=False, symbol=item.symbol, timeframe=item.timeframe,
                    frame=cached,
                    provider="NONE", provider_symbol=item.symbol, status="SYMBOL_FAILED",
                    message=f"Symbol failed safely: {type(exc).__name__}: {str(exc)[:180]}",
                    latest_completed_candle=None, fallback_provider=None,
                    attempts=[{
                        "provider": "ORCHESTRATOR", "ok": False,
                        "category": "UNEXPECTED_SYMBOL_FAILURE",
                        "message": f"{type(exc).__name__}: {str(exc)[:180]}",
                    }],
                    data_age_seconds=None, data_quality_score=0.0,
                    validation_status="INSUFFICIENT", run_id=run_id,
                )

        def wait_for_quota_capacity(index: int, item: ScheduleItem, *, reason: str) -> None:
            """Wait until one Twelve Data safety credit is actually available.

            Batch counters alone are insufficient when a connector validation or
            another session already used part of the rolling six-credit safety
            window.  Consulting the persistent quota ledger before each likely
            live request prevents the final selected symbols from being marked
            insufficient merely because they were processed later in the run.
            """
            nonlocal window_started, live_attempts_in_window, pause_count, paced_wait_seconds
            if not stagger_enabled:
                return
            for _ in range(4):
                try:
                    quota_state = self.orchestrator.quota.status().to_dict()
                    remaining_raw = quota_state.get("estimated_credits_remaining")
                    rate_limited = bool(quota_state.get("rate_limited"))
                    # Older/custom quota adapters may expose only the next-safe
                    # timestamp.  In that case retain deterministic batch pacing
                    # instead of treating missing telemetry as zero capacity.
                    if remaining_raw is None and not rate_limited:
                        return
                    remaining = float(remaining_raw or 0.0)
                    if remaining >= 1.0 and not rate_limited:
                        return
                    next_safe_raw = quota_state.get("next_safe_request_time")
                    wait_seconds = interval_seconds
                    if next_safe_raw:
                        next_safe = datetime.fromisoformat(str(next_safe_raw).replace("Z", "+00:00"))
                        if next_safe.tzinfo is None:
                            next_safe = next_safe.replace(tzinfo=timezone.utc)
                        wait_seconds = max(0.25, (next_safe - datetime.now(timezone.utc)).total_seconds() + 0.75)
                    publish(index - 1, item, f"Quota-safe wait: {reason}")
                    self._sleep(wait_seconds)
                    paced_wait_seconds += wait_seconds
                    pause_count += 1
                    window_started = self._clock()
                    live_attempts_in_window = 0
                except Exception:
                    # If quota telemetry itself is unavailable, retain the
                    # deterministic rolling-window pause rather than failing the
                    # complete selected-symbol transaction.
                    self._sleep(interval_seconds)
                    paced_wait_seconds += interval_seconds
                    pause_count += 1
                    window_started = self._clock()
                    live_attempts_in_window = 0
                    return

        def twelve_attempt_count(result: MarketDataResult) -> int:
            return sum(
                1 for attempt in result.attempts
                if str(attempt.get("provider") or "").upper() in {"TWELVE_DATA_KEY_POOL", "TWELVE_DATA_FALLBACK", "TWELVE_DATA", "TWELVE", "TWELVEDATA"}
                and bool(attempt.get("request_sent", attempt.get("ok", False)))
            )

        def handle_initial_result(index: int, item: ScheduleItem, result: MarketDataResult) -> None:
            nonlocal live_started, live_attempts_in_window
            results[item.symbol] = result.to_dict(include_frame=True)
            publish(index, item, f"Market data ready via {result.provider}", result)
            # Count only results that actually attempted a live provider. A cache
            # hit does not consume the scheduler's rolling live-request batch.
            twelve_attempts = twelve_attempt_count(result)
            if twelve_attempts:
                live_started += twelve_attempts
                live_attempts_in_window += twelve_attempts

        pool_workers = 1
        selector_assigned_alias = str(state_map.get("selector_owned_twelve_assigned_key_20260708") or "").strip().upper()
        if primary_provider == "TWELVE_DATA_KEY_POOL" and selector_assigned_alias not in {"TWELVE_KEY_1", "TWELVE_KEY_2"}:
            try:
                from core.twelve_data_key_pool import TwelveDataKeyPool
                pool_workers = max(1, TwelveDataKeyPool.from_state(state).active_key_count())
            except Exception:
                pool_workers = 1
        safe_parallel_workers = min(max(1, pool_workers), max(1, len(plan)))

        if primary_provider == "TWELVE_DATA_KEY_POOL" and safe_parallel_workers > 1:
            for index, item in enumerate(plan, start=1):
                publish(index - 1, item, "Queued for Twelve Data key-pool worker")
            with ThreadPoolExecutor(max_workers=safe_parallel_workers) as executor:
                future_map = {
                    executor.submit(safe_fetch, item, requested_force_live=bool(force_live)): (index, item)
                    for index, item in enumerate(plan, start=1)
                }
                for future in as_completed(future_map):
                    index, item = future_map[future]
                    result = future.result()
                    handle_initial_result(index, item, result)
        else:
            for index, item in enumerate(plan, start=1):
                publish(index - 1, item, "Checking validated candle cache")
                requested_force_live = bool(force_live)
                likely_live_request = bool(requested_force_live or item.needs_update or item.missing_data)
                if stagger_enabled and likely_live_request and live_attempts_in_window >= batch_size:
                    elapsed_window = max(0.0, self._clock() - window_started)
                    wait_seconds = max(0.0, interval_seconds - elapsed_window)
                    if wait_seconds > 0:
                        publish(index - 1, item, f"Quota-safe pause before next {batch_size}-symbol batch")
                        self._sleep(wait_seconds)
                        paced_wait_seconds += wait_seconds
                        pause_count += 1
                    window_started = self._clock()
                    live_attempts_in_window = 0
                if stagger_enabled and likely_live_request:
                    wait_for_quota_capacity(index, item, reason="rolling provider capacity")
                result = safe_fetch(item, requested_force_live=requested_force_live)
                handle_initial_result(index, item, result)

        # A successful provider response can still be too short for the selected
        # timeframe's 25-day higher-standard contract.  Retry only unresolved
        # symbols, after quota-safe pacing, so all ten selected children get a
        # fair chance to publish without rerunning already complete symbols.
        # Canonical ranking is allowed to use emergency exact-symbol history.
        # Retry only symbols below 25 candles; 25-49 rows are still rankable and
        # will be marked D_EMERGENCY_USABLE rather than failing as insufficient.
        minimum_rows = min(max(1, int(bars)), 25)
        default_rounds = 3 if (stagger_enabled and not explicit_stagger and len(plan) > self.max_live_requests_per_window) else 1
        configured_rounds = int(state_map.get("multi_symbol_fetch_rounds_20260706", default_rounds) or default_rounds)
        max_fetch_rounds = max(1, min(4, configured_rounds))
        retry_history: dict[str, list[dict[str, Any]]] = {}

        def unresolved_symbols() -> list[str]:
            unresolved: list[str] = []
            for item in plan:
                payload = results.get(item.symbol) or {}
                frame = payload.get("frame")
                rows = int(len(frame)) if isinstance(frame, pd.DataFrame) else 0
                if not bool(payload.get("ok")) or rows < minimum_rows:
                    unresolved.append(item.symbol)
            return unresolved

        plan_by_symbol = {item.symbol: item for item in plan}
        for fetch_round in range(2, max_fetch_rounds + 1):
            pending = unresolved_symbols()
            if not pending:
                break
            for retry_index, symbol in enumerate(pending, start=1):
                item = plan_by_symbol[symbol]
                if stagger_enabled and live_attempts_in_window >= batch_size:
                    elapsed_window = max(0.0, self._clock() - window_started)
                    wait_seconds = max(0.0, interval_seconds - elapsed_window)
                    if wait_seconds > 0:
                        publish(retry_index - 1, item, f"Quota-safe retry pause before next {batch_size}-symbol batch")
                        self._sleep(wait_seconds)
                        paced_wait_seconds += wait_seconds
                        pause_count += 1
                    window_started = self._clock()
                    live_attempts_in_window = 0
                wait_for_quota_capacity(retry_index, item, reason=f"retry round {fetch_round}")
                publish(retry_index - 1, item, f"Retrying incomplete market data ({fetch_round}/{max_fetch_rounds})")
                retried = safe_fetch(item, requested_force_live=True)
                twelve_attempts = twelve_attempt_count(retried)
                if twelve_attempts:
                    live_started += twelve_attempts
                    live_attempts_in_window += twelve_attempts
                previous = results.get(symbol) or {}
                previous_frame = previous.get("frame")
                previous_rows = int(len(previous_frame)) if isinstance(previous_frame, pd.DataFrame) else 0
                retry_rows = int(len(retried.frame)) if isinstance(retried.frame, pd.DataFrame) else 0
                retry_history.setdefault(symbol, []).append({
                    "round": fetch_round, "ok": bool(retried.ok),
                    "status": retried.status, "provider": retried.provider, "rows": retry_rows,
                })
                if (retried.ok and retry_rows >= previous_rows) or not bool(previous.get("ok")):
                    results[symbol] = retried.to_dict(include_frame=True)
                results[symbol]["fetch_retry_history_20260706"] = list(retry_history[symbol])
                publish(retry_index, item, f"Retry result via {retried.provider}", retried)

        unresolved = unresolved_symbols()
        quota = self.orchestrator.quota.status().to_dict()
        if deferred and not quota.get("next_safe_request_time"):
            quota["next_safe_request_time"] = datetime.now(timezone.utc).isoformat()
        return {
            "run_id": run_id,
            "timeframe": normalize_timeframe(timeframe),
            "plan": [asdict(item) for item in plan],
            "results": results,
            "deferred_symbols": deferred,
            "unresolved_symbols": unresolved,
            "required_candles_per_symbol": minimum_rows,
            "fetch_rounds": max_fetch_rounds,
            "fetch_retry_history_20260706": retry_history,
            "live_requests_started": live_started,
            "quota_safe_stagger": {
                "enabled": stagger_enabled,
                "pacing_provider": primary_provider if stagger_enabled else None,
                "batch_size": batch_size,
                "interval_seconds": interval_seconds,
                "pause_count": pause_count,
                "paced_wait_seconds": round(paced_wait_seconds, 3),
            },
            "run_disabled_providers": sorted(disabled_providers),
            "load_elapsed_seconds": round(max(0.0, self._clock() - run_started), 3),
            "quota": quota,
            "complete": not deferred and not unresolved and all(bool(value.get("ok")) for value in results.values()),
        }

    def m1_validation_scope(self, ranked_symbols: Sequence[Any], *, active_symbol: Any) -> list[str]:
        ordered = [normalize_symbol(active_symbol), *normalize_symbols(ranked_symbols)]
        deduped: list[str] = []
        for symbol in ordered:
            if symbol not in deduped:
                deduped.append(symbol)
            if len(deduped) >= self.max_m1_validation_symbols:
                break
        return deduped


__all__ = ["ScheduleItem", "MultiSymbolScheduler"]
