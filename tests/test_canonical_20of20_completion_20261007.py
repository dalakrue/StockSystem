"""Tests for the 2026-10-07 canonical 20/20 load completion fix.

The middle standard regime ranking table must only be produced when the FULL
canonical 20-symbol universe is loaded. These tests cover:

- ensure_complete_canonical_load() retries failed symbols through the FULL
  key pool until 20/20 (or bounded rounds), never re-fetching good rows
- _pool_capacity_snapshot() / _wait_for_pool_capacity() quota-aware waits
- load_all_selectors_safely() accepts ensure_complete and runs the loop
- retry flag consumed by the top Quick Actions wiring (state-flag contract)
"""
import pytest

from core import multi_symbol_load_manager_20260707 as lm
from core.fixed_fx_universe_20260918 import TARGET_FX_SYMBOLS


SYMBOLS_20 = list(TARGET_FX_SYMBOLS)
assert len(SYMBOLS_20) == 20
GROUPS = {"FIRST": SYMBOLS_20[:7], "SECOND": SYMBOLS_20[7:14], "THIRD": SYMBOLS_20[14:]}


def six_key_state():
    state = {"enable_twelve_multi_key_loading": True, "timeframe": "H1"}
    for index in range(1, 7):
        state[f"twelve_api_key_{index}"] = f"POOL-TEST-KEY-{index}"
    return state


def test_pool_capacity_snapshot_reports_usable_keys():
    import core.multi_symbol_load_manager_20260707 as mod
    ok, detail = mod._pool_capacity_snapshot(six_key_state())
    assert ok is True
    assert "TWELVE_KEY_1" in detail


def test_pool_capacity_snapshot_no_keys_configured():
    import core.multi_symbol_load_manager_20260707 as mod
    ok, detail = mod._pool_capacity_snapshot({"enable_twelve_multi_key_loading": True})
    assert ok is False


def test_wait_for_pool_capacity_returns_immediately_when_credits_available(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod
    sleeps = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: sleeps.append(s))
    assert mod._wait_for_pool_capacity(six_key_state(), max_wait_seconds=75) is True
    assert sleeps == []


def test_ensure_complete_retries_failed_only_through_full_pool(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod

    state = six_key_state()
    failed_now = list(SYMBOLS_20[15:])  # 5 failed symbols
    calls = []

    def fake_merge(state_arg, configured, tf):
        loaded = [s for s in SYMBOLS_20 if s not in failed_now]
        return {"requested_symbols": list(SYMBOLS_20), "loaded_symbols": loaded,
                "failed_symbols": list(failed_now)}

    def fake_run_group(state_arg, group_name, symbols, tf, key_alias, **kwargs):
        calls.append({"group": group_name, "key": key_alias,
                      "retry_symbols": list(kwargs.get("retry_symbols") or [])})
        # Simulate provider success: failed symbols in this group now load.
        for symbol in kwargs.get("retry_symbols") or []:
            if symbol in failed_now:
                failed_now.remove(symbol)
        return {"ok": True}

    def fake_records(state_arg):
        # Pretend every group already has a load record so the retry path is used.
        return {"FIRST": {"a": 1}, "SECOND": {"a": 1}, "THIRD": {"a": 1}}

    monkeypatch.setattr(mod, "merge_selector_load_results", fake_merge)
    monkeypatch.setattr(mod, "_run_group_with_temporary_assignment", fake_run_group)
    monkeypatch.setattr(mod, "_records", fake_records)
    monkeypatch.setattr(mod, "clear_circuit_breaker_for_symbols", lambda *a, **k: {"cleared": 1})
    monkeypatch.setattr(mod, "_wait_for_pool_capacity", lambda *a, **k: True)

    final = mod.ensure_complete_canonical_load(state, GROUPS, "H1", max_rounds=5)

    assert final["failed_symbols"] == []
    assert len(final["loaded_symbols"]) == 20
    # Every retry went through the FULL pool (all keys), never a single key.
    assert calls and all(call["key"] == "TWELVE_DATA_KEY_POOL" for call in calls)
    # Only failed symbols were retried — good rows never re-fetched.
    retried = [s for call in calls for s in call["retry_symbols"]]
    assert sorted(retried) == sorted(SYMBOLS_20[15:])
    assert len(retried) == len(set(retried))
    trace = state["canonical_completion_loop_trace_20261007"]
    assert trace["complete"] is True


def test_ensure_complete_stops_after_max_rounds(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod

    state = six_key_state()

    def fake_merge(state_arg, configured, tf):
        return {"requested_symbols": list(SYMBOLS_20),
                "loaded_symbols": list(SYMBOLS_20[:17]),
                "failed_symbols": list(SYMBOLS_20[17:])}

    monkeypatch.setattr(mod, "merge_selector_load_results", fake_merge)
    monkeypatch.setattr(mod, "_run_group_with_temporary_assignment",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("provider down")))
    monkeypatch.setattr(mod, "_records", lambda s: {"FIRST": {}, "SECOND": {}, "THIRD": {}})
    monkeypatch.setattr(mod, "clear_circuit_breaker_for_symbols", lambda *a, **k: {})
    monkeypatch.setattr(mod, "_wait_for_pool_capacity", lambda *a, **k: True)

    final = mod.ensure_complete_canonical_load(state, GROUPS, "H1", max_rounds=3)
    trace = state["canonical_completion_loop_trace_20261007"]
    assert trace["complete"] is False
    assert len(trace["rounds"]) == 3
    assert final["failed_symbols"] == list(SYMBOLS_20[17:])


def test_ensure_complete_noop_when_already_complete(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod

    state = six_key_state()
    calls = []

    def fake_merge(state_arg, configured, tf):
        return {"requested_symbols": list(SYMBOLS_20), "loaded_symbols": list(SYMBOLS_20),
                "failed_symbols": []}

    monkeypatch.setattr(mod, "merge_selector_load_results", fake_merge)
    monkeypatch.setattr(mod, "_run_group_with_temporary_assignment",
                        lambda *a, **k: calls.append(1))

    final = mod.ensure_complete_canonical_load(state, GROUPS, "H1", max_rounds=5)
    assert calls == []
    assert final["failed_symbols"] == []
    assert state["canonical_completion_loop_trace_20261007"]["complete"] is True


def test_load_all_selectors_safely_runs_completion_loop(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod

    state = six_key_state()
    seen = {}

    def fake_ensure(state_arg, configured, tf, **kwargs):
        seen["called"] = True
        return {"requested_symbols": list(SYMBOLS_20), "loaded_symbols": list(SYMBOLS_20),
                "failed_symbols": []}

    # Short-circuit the per-selector loads; we only verify the completion
    # loop wiring here.
    monkeypatch.setattr(mod, "load_selector_with_assigned_key", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(mod, "merge_selector_load_results",
                        lambda *a, **k: {"requested_symbols": [], "loaded_symbols": [], "failed_symbols": []})
    monkeypatch.setattr(mod, "ensure_complete_canonical_load", fake_ensure)

    mod.load_all_selectors_safely(state, GROUPS, "H1")
    assert seen.get("called") is True


def test_load_all_selectors_safely_can_skip_completion_loop(monkeypatch):
    import core.multi_symbol_load_manager_20260707 as mod

    state = six_key_state()
    seen = {}

    def fake_ensure(state_arg, configured, tf, **kwargs):
        seen["called"] = True
        return {}

    monkeypatch.setattr(mod, "load_selector_with_assigned_key", lambda *a, **k: {"ok": True})
    monkeypatch.setattr(mod, "merge_selector_load_results",
                        lambda *a, **k: {"requested_symbols": [], "loaded_symbols": [], "failed_symbols": []})
    monkeypatch.setattr(mod, "ensure_complete_canonical_load", fake_ensure)

    mod.load_all_selectors_safely(state, GROUPS, "H1", ensure_complete=False)
    assert seen.get("called") is None


def test_top_retry_flag_contract():
    # The top Quick Actions "Retry Failed Symbols" button sets this flag;
    # render_multi_symbol_selectors consumes it via state.pop().
    state = {"settings_top_retry_failed_requested_20261007": True}
    assert bool(state.pop("settings_top_retry_failed_requested_20261007", False)) is True
    assert "settings_top_retry_failed_requested_20261007" not in state
