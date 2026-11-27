"""Zero-touch startup auto-load for the slim Field 3 build (2026-10-19).

When the app opens and no completed Field 3 generation exists yet, this
module loads the canonical 28-symbol universe and runs the Super Quick
calculation — the same pipeline the Settings sidebar's "Super Quick Run"
button uses — so the Middle Standard Regime Ranking table appears after
a short wait with zero manual steps.

A Twelve Data key is used when one is configured (Streamlit Secrets
TWELVE_DATA_API_KEY -> credential vault -> session state), but it is NOT
required: the loader admits every symbol that already holds a valid
frame in the local candle store, which a cold boot restores from the
repo snapshot (fix 2026-11-25 — the old key gate meant a fresh redeploy,
whose in-app key vault is wiped, never auto-loaded at all and the app
sat at a partial 20/28). Runs at most once per browser session. Any
failure falls back silently to the manual Settings flow.
"""
from __future__ import annotations

import contextlib
import threading
from collections.abc import MutableMapping
from typing import Any

AUTO_LOAD_FLAG = "auto_load_attempted_20261019"
AUTO_LOAD_ERROR = "auto_load_error_20261019"


def _resolve_twelve_key(state: MutableMapping[str, Any]) -> tuple[str, str]:
    """Use the same aliases and temporary-key priority as every live fetch."""
    from core.twelve_data_key_pool import resolve_twelve_key
    key = resolve_twelve_key(state, "TWELVE_KEY_1")
    return key, "configured_provider" if key else ""


def _has_completed_generation(state: MutableMapping[str, Any]) -> bool:
    try:
        import pandas as pd

        ranking = state.get("field3_multisymbol_regime_20260708")
        return isinstance(ranking, pd.DataFrame) and not ranking.empty
    except Exception:
        return False


def maybe_auto_load_field3(state: MutableMapping[str, Any],
                           *, _headless: bool = False) -> dict[str, Any]:
    """Attempt the one-time startup auto-load. Never raises.

    _headless is for the background-thread wrapper below: streamlit
    spinners belong to a script run, so the thread runs without
    them. The load/calculation itself is identical."""
    outcome: dict[str, Any] = {"attempted": False, "ok": False, "reason": ""}
    try:
        if state.get(AUTO_LOAD_FLAG):
            outcome["reason"] = "already_attempted_this_session"
            return outcome
        if _has_completed_generation(state):
            outcome["reason"] = "generation_already_present"
            return outcome

        key, source = _resolve_twelve_key(state)
        # FIX 2026-11-25 (20-of-28 bug): a Twelve key is no longer a gate.
        # The load below admits every symbol with a valid frame in the
        # local candle store (restored from the repo snapshot on cold
        # boot) and only spends provider credits on symbols the store
        # cannot cover. The old gate returned here whenever the key was
        # missing or its pool momentarily empty -- exactly the state of
        # every fresh redeploy -- so auto-load never ran and the app
        # showed whatever partial load a manual Twelve run had managed.
        if key:
            # Make the key visible to the existing pool machinery exactly
            # like a Settings paste does.
            try:
                state["twelve_api_key"] = key
                state["twelve_api_key_source"] = f"auto_load_{source}"
            except Exception:
                pass
        else:
            source = "local_cache_no_key"

        outcome["attempted"] = True
        # Only now mark attempted: a real load is about to run.
        state[AUTO_LOAD_FLAG] = True

        import streamlit as st

        def _spin(msg):
            return (contextlib.nullcontext() if _headless
                    else st.spinner(msg))

        from core.fixed_fx_universe_20260918 import fixed_groups
        from core.multi_symbol_load_manager_20260707 import (
            activate_loaded_universe_for_run,
            load_all_selectors_safely,
        )
        from core.multi_symbol_run_groups_20260706 import mark_run_group
        from core.super_quick_field3_20260722 import run_super_quick_field3

        timeframe = str(
            state.get("timeframe") or state.get("selected_timeframe") or "H1"
        ).upper()
        groups = fixed_groups()
        scope = "LUNCH_CORE"  # Super Quick — the app's recommended default mode.

        # Parallel two-timeframe load (user order 2026-11-26): the
        # selector loader's records hold ONE timeframe at a time, so
        # the second timeframe the app actually consumes -- M15, used
        # by every check/precheck evaluation -- was never loaded at
        # startup and arrived as a second serial wait at check time.
        # Warm it CONCURRENTLY with the main load through the check
        # runtime's own route (repository-first, Dukascopy live fill;
        # spends no Twelve Data credits). The warm thread uses a
        # throwaway state dict (no session-state races); every bar it
        # fetches is persisted to the shared candle repository, so
        # the check runtime later reads them store-first.
        import threading

        def _warm_m15() -> None:
            try:
                from core.check_candle_runtime import fetch_m15_frames
                from core.fixed_fx_universe_20260918 import (
                    TARGET_FX_SYMBOLS,
                )

                fetch_m15_frames({}, list(TARGET_FX_SYMBOLS))
            except Exception:
                pass

        _m15_warm = threading.Thread(
            target=_warm_m15, daemon=True, name="auto_load_m15_warm"
        )
        _m15_warm.start()

        with _spin("Loading market data from Twelve Data…"):
            load_all_selectors_safely(state, groups, timeframe)

        _m15_warm.join(timeout=120)
        outcome["m15_warm_joined"] = not _m15_warm.is_alive()

        activation = activate_loaded_universe_for_run(state, scope, groups, timeframe)
        if not activation.get("ok"):
            outcome["reason"] = (
                "activation_failed: " + str(activation.get("message") or "not_ready")
            )
            return outcome
        run_symbols = list(activation.get("loaded_symbols") or [])
        if not run_symbols:
            outcome["reason"] = "no_loaded_symbols_after_activation"
            return outcome

        # Mirror the sidebar Super Quick bookkeeping exactly.
        state["settings_calculation_scope_20260625"] = scope
        state["field3_fast_two_table_mode_20260722"] = True
        state["field3_last_run_scope_20260722"] = scope
        try:
            from core.field10_fast_lane_20260709 import set_field10_fast_lane

            set_field10_fast_lane(state, enabled=True, scope=scope)
        except Exception:
            pass
        mark_run_group(state, scope, run_symbols)

        with _spin("Calculating regime ranking…"):
            fast_result = run_super_quick_field3(
                state, symbols=run_symbols, timeframe=timeframe
            )
        state["settings_run_status_20260617"] = fast_result

        outcome["ok"] = True
        outcome["reason"] = f"auto_load_complete_via_{source}"
        outcome["symbols"] = len(run_symbols)
        return outcome
    except Exception as exc:  # Silent fallback to the manual Settings flow.
        outcome["reason"] = f"{type(exc).__name__}: {exc}"
        try:
            state[AUTO_LOAD_ERROR] = outcome["reason"]
        except Exception:
            pass
        return outcome


# ---------------------------------------------------------------------
# Background wrapper (speed fix 2026-11-28, user order: the app must
# reach its dashboard in 1-5 s outside check windows). The synchronous
# auto-load above used to run BEFORE the first paint -- the user
# watched "Loading market data from Twelve Data..." for minutes.
# Now the runner calls maybe_auto_load_field3_async(): the load runs
# on a daemon thread against a detached copy of the session state
# (the load/calculation chain takes `state` as a parameter and never
# touches st.session_state directly), the dashboard paints at once
# from last-known state, and when the thread lands, the next rerun
# merges the produced keys into the real session state. A key the
# user changed in the meantime is never overwritten: only keys the
# thread created, or that still hold the exact snapshot object, are
# merged back.
# ---------------------------------------------------------------------
_BG_LOCK = threading.Lock()
_BG_RUNNING = False
_BG_PENDING: dict[str, Any] | None = None


def _snapshot_state(state: MutableMapping[str, Any]) -> dict[str, Any]:
    try:
        return {k: state[k] for k in list(state.keys())}
    except Exception:
        return dict(state)  # type: ignore[arg-type]


def _merge_detached(state: MutableMapping[str, Any],
                    snapshot: dict[str, Any],
                    detached: dict[str, Any]) -> None:
    for key, value in detached.items():
        if key not in state:
            state[key] = value
        elif key in snapshot and state.get(key) is snapshot[key] \
                and value is not snapshot[key]:
            state[key] = value


def maybe_auto_load_field3_async(
        state: MutableMapping[str, Any]) -> dict[str, Any]:
    """Non-blocking startup auto-load. Never raises.

    Returns immediately with one of: generation_already_present /
    auto_load_merged (a finished background load was merged into
    the session) / auto_load_running_in_background /
    auto_load_started_in_background / the synchronous outcome when
    there was nothing to load.
    """
    global _BG_RUNNING, _BG_PENDING
    outcome: dict[str, Any] = {"attempted": False, "ok": False,
                               "reason": ""}
    try:
        if _has_completed_generation(state):
            outcome["reason"] = "generation_already_present"
            return outcome
        with _BG_LOCK:
            pending = _BG_PENDING
            if pending is not None:
                _BG_PENDING = None
        if pending is not None:
            _merge_detached(state, pending["snapshot"],
                            pending["detached"])
            merged = dict(pending["outcome"])
            merged["merged_into_session"] = True
            if _has_completed_generation(state):
                merged["ok"] = True
            return merged
        with _BG_LOCK:
            if _BG_RUNNING:
                outcome["attempted"] = True
                outcome["reason"] = "auto_load_running_in_background"
                return outcome
            if state.get(AUTO_LOAD_FLAG):
                outcome["reason"] = "already_attempted_this_session"
                return outcome
            _BG_RUNNING = True
        snapshot = _snapshot_state(state)
        detached = dict(snapshot)

        def _work() -> None:
            global _BG_RUNNING, _BG_PENDING
            try:
                result = maybe_auto_load_field3(detached,
                                                _headless=True)
            except Exception as exc:  # the sync call never raises
                result = {"attempted": True, "ok": False,
                          "reason": f"{type(exc).__name__}: {exc}"}
            with _BG_LOCK:
                _BG_PENDING = {"snapshot": snapshot,
                               "detached": detached,
                               "outcome": result}
                _BG_RUNNING = False

        threading.Thread(target=_work, daemon=True,
                         name="auto_load_field3_bg").start()
        outcome["attempted"] = True
        outcome["reason"] = "auto_load_started_in_background"
        return outcome
    except Exception as exc:
        outcome["reason"] = f"{type(exc).__name__}: {exc}"
        return outcome


__all__ = ["maybe_auto_load_field3", "maybe_auto_load_field3_async",
           "AUTO_LOAD_FLAG", "AUTO_LOAD_ERROR"]
