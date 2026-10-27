"""Check-minute data -> actual evaluator -> visible table regression tests.

Provider responses here are deterministic fixtures, not live market evidence.
"""
from contextlib import nullcontext
from pathlib import Path
import time

import numpy as np
import pandas as pd
import pytest

from core import check_candle_runtime as runtime
from core import twelve_data_key_pool as keys

SYMBOLS = ("AUDCAD", "AUDCHF", "AUDJPY", "AUDNZD", "AUDUSD", "CHFJPY", "EURAUD",
           "EURCAD", "EURCHF", "EURGBP", "EURJPY", "EURNZD", "EURUSD", "GBPJPY",
           "GBPUSD", "NZDCAD", "NZDUSD", "USDCAD", "USDCHF", "USDJPY")
ENTRY = pd.Timestamp.now(tz="UTC").tz_localize(None).floor("h")


def candles(index, price=1.1):
    return pd.DataFrame(dict(Open=price, High=price + .0003, Low=price - .0003,
                             Close=price + .0001, Volume=100.0), index=pd.DatetimeIndex(index))


class Repo:
    def __init__(self, frames):
        self.frames, self.writes = frames, []

    def load(self, sym, tf, **kwargs):
        return self.frames.get((sym, tf))

    def upsert(self, raw, **kwargs):
        self.writes.append(raw.copy())
        return {"inserted": len(raw), "rejected": 0}


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch):
    keys._GLOBAL_POOL_RUNTIME.clear()
    keys._GLOBAL_POOL_RUNTIME["keys"] = {}
    monkeypatch.setattr(keys, "_secret_path", lambda *args: "")
    from core.connectors import credential_vault
    monkeypatch.setattr(credential_vault, "load_credential", lambda *args: "")


def state_keys():
    return {f"twelve_api_key_{i}": f"FIXTURE-KEY-{i}" for i in range(1, 4)}


def install_provider(monkeypatch, *, missing_entry=False, h1_complete=False):
    history = candles(pd.date_range(end=ENTRY if h1_complete else ENTRY-pd.Timedelta(hours=1),
                                    periods=400, freq="h"))
    repo = Repo({(s, "H1"): history.copy() for s in SYMBOLS})
    monkeypatch.setattr(runtime, "_repository", lambda: repo)
    import core.connectors.data_parts.fetchers as fetchers
    calls = []

    def provider(sym, key, interval, bars, **kwargs):
        calls.append((sym, interval, bars, kwargs))
        if interval == "1h":
            return history, True, "fixture"
        end = ENTRY - pd.Timedelta(minutes=15) if missing_entry else ENTRY
        raw = candles(pd.date_range(end=end, periods=2000, freq="15min"))
        return raw, True, "fixture"

    monkeypatch.setattr(fetchers, "fetch_twelve", provider)
    return repo, calls


def test_exact_hour_open_accepts_single_m15_bar():
    row = runtime.entry_candle_from_m15(candles([ENTRY], 210.233), ENTRY, asof=ENTRY)
    assert row.loc[ENTRY, "Open"] == 210.233
    assert row.attrs["is_partial_hour"]


def test_missing_first_bar_never_uses_later_bar():
    assert runtime.entry_candle_from_m15(candles([ENTRY+pd.Timedelta(minutes=15)]),
                                          ENTRY, asof=ENTRY+pd.Timedelta(minutes=20)) is None


def test_completed_hour_requires_all_quarters():
    raw = candles(pd.date_range(ENTRY, periods=4, freq="15min"))
    assert runtime.entry_candle_from_m15(raw, ENTRY, asof=ENTRY+pd.Timedelta(hours=2)) is not None
    assert runtime.entry_candle_from_m15(raw.iloc[[0, 1, 3]], ENTRY,
                                          asof=ENTRY+pd.Timedelta(hours=2)) is None


def test_future_bars_do_not_change_forming_hour():
    raw = candles(pd.date_range(ENTRY, periods=8, freq="15min"))
    before = runtime.entry_candle_from_m15(raw, ENTRY, asof=ENTRY)
    raw.iloc[1:, :4] *= 5
    pd.testing.assert_frame_equal(before, runtime.entry_candle_from_m15(raw, ENTRY, asof=ENTRY))
    assert runtime.entry_candle_from_m15(raw, ENTRY, asof=ENTRY-pd.Timedelta(seconds=1)) is None


@pytest.mark.parametrize("value", [np.nan, np.inf, -1.0, 0.0])
def test_invalid_entry_open_rejected(value):
    raw = candles([ENTRY]); raw.loc[ENTRY, "Open"] = value
    assert runtime.entry_candle_from_m15(raw, ENTRY, asof=ENTRY) is None


def test_timezone_and_lowercase_index_normalization():
    raw = candles([ENTRY]).rename(columns=str.lower)
    raw.index = raw.index.tz_localize("UTC").tz_convert("Asia/Rangoon")
    norm = runtime.normalize_ohlc(raw)
    assert norm.index[0] == ENTRY and norm.index.tz is None
    assert norm.Open.iloc[0] == 1.1


def test_20_symbol_boundary_direct_m15_then_shared_memo(monkeypatch):
    repo, calls = install_provider(monkeypatch)
    state = state_keys(); need = [ENTRY-pd.Timedelta(hours=1), ENTRY]
    frames, latest, diag = runtime.fetch_check_frames(state, SYMBOLS, need)
    assert diag["ready"] == 20 and latest == ENTRY
    assert len(calls) == 20 and {c[1] for c in calls} == {"15min"}
    assert all(f.loc[ENTRY, "Open"] == 1.1 for f in frames.values())
    again = runtime.fetch_check_frames(state, SYMBOLS, need)
    assert again is state[runtime.H1_MEMO_KEY]["result"] and len(calls) == 20
    # Only complete, real M15 goes to durable history. Never a partial H1.
    assert repo.writes and all((f.timeframe == "M15").all() and f.is_complete.all() for f in repo.writes)


def test_native_h1_uses_zero_provider_calls(monkeypatch):
    _, calls = install_provider(monkeypatch, h1_complete=True)
    _, _, diag = runtime.fetch_check_frames(state_keys(), SYMBOLS, [ENTRY-pd.Timedelta(hours=1), ENTRY])
    assert diag["ready"] == 20 and not calls


def test_force_refresh_does_not_exhaust_credits_on_late_h1(monkeypatch):
    _, calls = install_provider(monkeypatch)
    state = state_keys(); state["force_signal_refresh"] = True
    _, _, diag = runtime.fetch_check_frames(state, SYMBOLS, [ENTRY-pd.Timedelta(hours=1), ENTRY])
    assert diag["ready"] == 20 and {c[1] for c in calls} == {"15min"}
    assert all(c[3]["force_live"] for c in calls)


def test_refresh_timer_aligns_before_and_during_check(monkeypatch):
    from core import signal_mode
    monkeypatch.setattr(signal_mode, "active_check_hours", lambda: (15, 17, 18))
    assert runtime.check_refresh_interval_ms("2026-10-26 17:59:57") == 3000
    assert runtime.check_refresh_interval_ms("2026-10-26 18:00:02") == 5000
    assert runtime.check_refresh_interval_ms("2026-10-26 18:02") == 30000


def test_missing_m15_is_incomplete_and_retries_same_window(monkeypatch):
    _, calls = install_provider(monkeypatch, missing_entry=True)
    state = state_keys(); need = [ENTRY-pd.Timedelta(hours=1), ENTRY]
    _, _, diag = runtime.fetch_check_frames(state, SYMBOLS, need)
    assert diag["ready"] == 0 and len(diag["missing_symbols"]) == 20
    assert len(calls) == 20
    runtime.fetch_check_frames(state, SYMBOLS, need)
    assert len(calls) == 20
    state[runtime.H1_MEMO_KEY]["at"] -= runtime.RETRY_SECONDS+1
    for item in state[runtime.M15_MEMO_KEY].values():
        item["attempt"] -= runtime.RETRY_SECONDS+1
    import core.connectors.data_parts.fetchers as f
    monkeypatch.setattr(f, "fetch_twelve", lambda *a, **k: (candles(pd.date_range(end=ENTRY, periods=2000, freq="15min")), True, "fixture"))
    # Reset test credits for next-minute recovery.
    state.pop(keys._POOL_STATE_KEY, None)
    keys._GLOBAL_POOL_RUNTIME["keys"] = {}
    _, _, diag = runtime.fetch_check_frames(state, SYMBOLS, need)
    assert diag["ready"] == 20


def test_new_m15_boundary_bypasses_old_failure_cooldown(monkeypatch):
    monkeypatch.setattr(runtime, "_repository", lambda: None)
    state = state_keys()
    old = ENTRY-pd.Timedelta(minutes=15)
    state[runtime.M15_MEMO_KEY] = {"EURUSD": dict(frame=candles([old]), attempt=time.monotonic(), required=old)}
    calls = []
    monkeypatch.setattr(runtime, "_direct_fetch", lambda *a, **k: (calls.append(a) or {"EURUSD": candles([ENTRY])}, []))
    frames = runtime.fetch_m15_frames(state, ["EURUSD"], need_entry=ENTRY)
    assert calls and ENTRY in frames["EURUSD"].index


def test_deep_m15_refreshes_stale_repository_and_preserves_volume(monkeypatch):
    repo = Repo({("EURUSD", "M15"): candles(pd.date_range(end=ENTRY-pd.Timedelta(hours=3), periods=2000, freq="15min"))})
    monkeypatch.setattr(runtime, "_repository", lambda: repo)
    fresh = candles(pd.date_range(end=ENTRY, periods=2000, freq="15min"))
    monkeypatch.setattr(runtime, "_direct_fetch", lambda *a, **k: ({"EURUSD": fresh}, []))
    frames = runtime.fetch_m15_frames(state_keys(), ["EURUSD"])
    assert len(frames["EURUSD"]) >= 2000
    assert frames["EURUSD"].index.max() == ENTRY
    assert frames["EURUSD"].Volume.iloc[-1] == 100


def test_provider_deadline_does_not_wait_for_worker(monkeypatch):
    import core.connectors.data_parts.fetchers as f
    def slow(*args, **kwargs):
        time.sleep(.4)
        return candles([ENTRY]), True, "fixture"
    monkeypatch.setattr(f, "fetch_twelve", slow)
    start = time.monotonic()
    frames, errors = runtime._direct_fetch(state_keys(), ["EURUSD"], "M15", deadline=start+.04)
    assert time.monotonic()-start < .3
    assert not frames and any("deadline" in e for e in errors)


def test_root_secrets_and_env_work_after_restart(monkeypatch):
    monkeypatch.setattr(keys, "_secret_path", lambda *p: "SECRET-FIXTURE" if p == ("TWELVE_DATA_API_KEY",) else "")
    assert keys.resolve_twelve_key({}, "TWELVE_KEY_1") == "SECRET-FIXTURE"
    monkeypatch.setattr(keys, "_secret_path", lambda *p: "")
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "ENV-FIXTURE")
    assert keys.resolve_twelve_key({}, "TWELVE_KEY_1") == "ENV-FIXTURE"
    assert keys.resolve_twelve_key({}, "TWELVE_KEY_2") == ""


def test_duplicate_api_key_does_not_multiply_quota():
    pool = keys.TwelveDataKeyPool({"twelve_api_key_1": "same", "twelve_api_key_2": "same"})
    assert pool.active_key_count() == 1
    assert sum(pool.reserve_key() is not None for _ in range(20)) == 8


def test_temporary_key_overrides_secret(monkeypatch):
    monkeypatch.setattr(keys, "_secret_path", lambda *p: "old-secret")
    assert keys.resolve_twelve_key({"twelve_api_key": "replacement"}, "TWELVE_KEY_1") == "replacement"


def test_saved_vault_key_cannot_shadow_new_deployment_secret(monkeypatch):
    monkeypatch.setattr(keys, "_secret_path", lambda *p: "new-secret" if p == ("TWELVE_DATA_API_KEY",) else "")
    state = {"twelve_api_key": "old-key", "twelve_api_key_source": "vault"}
    assert keys.resolve_twelve_key(state, "TWELVE_KEY_1") == "new-secret"


def test_no_key_never_enters_sidebar_capacity_sleep(monkeypatch):
    from core import multi_symbol_load_manager_20260707 as manager
    sleeps = []
    monkeypatch.setattr(manager.time, "sleep", lambda seconds: sleeps.append(seconds))
    assert manager._wait_for_pool_capacity({}, max_wait_seconds=75) is False
    assert not sleeps


def test_startup_can_recover_after_key_is_added(monkeypatch):
    from core import auto_load_startup_20261019 as startup
    state = {}
    monkeypatch.setattr(startup, "_resolve_twelve_key", lambda s: ("", ""))
    assert startup.maybe_auto_load_field3(state)["reason"] == "no_twelve_key_found"
    assert not state.get(startup.AUTO_LOAD_FLAG)


def test_per_key_limit_can_be_set_to_actual_plan_in_secrets(monkeypatch):
    monkeypatch.setattr(keys, "_secret_path", lambda *p: "32" if p == ("twelve_data", "per_key_minute_limit") else "")
    pool = keys.TwelveDataKeyPool({"twelve_api_key": "plan-fixture"})
    assert pool.minute_limit == 32


def test_wrapper_m15_memo_cannot_hide_new_check_data(monkeypatch):
    from core import cycle93_best as cycle
    stale = {"EURUSD": candles([ENTRY-pd.Timedelta(hours=2)])}
    monkeypatch.setitem(cycle._M15_FETCH_MEMO, "ts", time.monotonic())
    monkeypatch.setitem(cycle._M15_FETCH_MEMO, "frames", stale)
    fresh = {"EURUSD": candles([ENTRY])}
    monkeypatch.setattr(cycle, "fetch_cycle78_m15_frames", lambda **kwargs: fresh)
    assert cycle.fetch_cycle93_m15_frames({}) is fresh


def test_combined_best_data_failure_cannot_fall_through(monkeypatch):
    from core import signal_mode as mode
    calls = []
    def unavailable(system, *args, **kwargs):
        calls.append(system)
        empty = pd.DataFrame(); empty.attrs["status"] = "insufficient_m15_history"
        return empty
    monkeypatch.setattr(mode, "_evaluate_and_select_for", unavailable)
    out, source = mode.evaluate_combined_entries(11, {}, ENTRY)
    assert source == "BEST" and len(calls) == 1 and out.attrs["status"]


def test_real_october_engine_native_vs_m15_entry_parity():
    from core.cycle92_best import evaluate_cycle92_signals, select_cycle92_entries
    # Use the package's existing quote fixture and its actual frozen evaluator.
    raw = pd.read_csv(Path(__file__).parent/"fixtures/monthly_h1_quotes.csv")
    frames = {s: runtime.normalize_ohlc(d) for s, d in raw.groupby("Symbol")}
    compared = fired = 0
    times = sorted(set.intersection(*(set(f.index) for f in frames.values())))
    for entry in [t for t in times if t.month == 10 and t.hour in (15, 17, 18)][-18:]:
        if not all(entry-pd.Timedelta(hours=1) in f.index for f in frames.values()):
            continue
        native = {s: f.loc[:entry].copy() for s, f in frames.items()}
        fallback = {}
        for s, f in native.items():
            row = runtime.entry_candle_from_m15(candles([entry], float(f.loc[entry, "Open"])), entry, asof=entry)
            fallback[s] = runtime._merge(f.loc[f.index < entry], row, 5000)
        check = entry+pd.Timedelta(minutes=30)
        a, b = evaluate_cycle92_signals(native, check), evaluate_cycle92_signals(fallback, check)
        pd.testing.assert_frame_equal(a, b)
        pd.testing.assert_frame_equal(select_cycle92_entries(a), select_cycle92_entries(b))
        fired += len(a); compared += 1
    assert compared >= 6
    assert fired > 0  # Verify positive signals as well as genuinely silent checks.


def test_price_display_known_sell_format():
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    candidate = pd.DataFrame([dict(symbol="GBPJPY", direction="SELL", entry_px=210.233,
                                   tp_pips=10, sl_pips=100, score=100, equation="FIXTURE")])
    display = panel._c22_signals_to_display(candidate)
    assert display.iloc[0]["Quick look"] == "GBPJPY-S-T210.133,S211.233"
    assert display.iloc[0]["Entry"] == 210.233


def test_no_signal_table_has_20_rows_and_real_prices():
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    need = [ENTRY-pd.Timedelta(hours=1), ENTRY]
    frames = {s: candles(need) for s in SYMBOLS}
    ranking = panel._c22_build_check_ranking(pd.DataFrame(), pd.DataFrame(), frames, need)
    assert len(ranking) == 20 and set(ranking.Symbol) == set(SYMBOLS)
    assert ranking.Entry.eq(1.1).all() and ranking["Signal close"].eq(1.1001).all()
    assert ranking.Score.eq(0).all()


def test_full_20_symbol_fetch_real_engine_and_visible_entry(monkeypatch):
    """One continuous controlled path, rather than independent layer mocks."""
    from streamlit.testing.v1 import AppTest
    from core import cycle92_best as engine
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    import core.connectors.data_parts.fetchers as fetchers
    raw = pd.read_csv(Path(__file__).parent/"fixtures/monthly_h1_quotes.csv")
    base = {s: runtime.normalize_ohlc(d) for s, d in raw.groupby("Symbol")}
    times = sorted(set.intersection(*(set(f.index) for f in base.values())))
    entry = [t for t in times if t.month == 10 and t.hour in (15, 17, 18)][-17]
    native = {s: base.get(s, base["EURJPY"] if s.endswith("JPY") else base["AUDCAD"]).loc[:entry].copy()
              for s in SYMBOLS}
    expected = engine.select_cycle92_entries(engine.evaluate_cycle92_signals(native, entry+pd.Timedelta(minutes=30)))
    assert len(expected) > 0
    repo = Repo({(s, "H1"): f.loc[f.index < entry] for s, f in native.items()})
    monkeypatch.setattr(runtime, "_repository", lambda: repo)
    calls = []
    def provider(sym, key, interval, bars, **kwargs):
        calls.append(interval)
        # Controlled quarter-hour fixture with the native H1 opening tick.
        row = native[sym].loc[entry]
        data = pd.DataFrame([row.to_dict() for _ in range(4)],
                            index=pd.date_range(entry, periods=4, freq="15min"))
        return data, True, "controlled fixture"
    monkeypatch.setattr(fetchers, "fetch_twelve", provider)
    monkeypatch.setattr(panel, "_record_eval_history", lambda *a, **k: None)
    monkeypatch.setattr(panel, "_latest_entry_window_utc", lambda *a, **k: entry)
    monkeypatch.setattr(panel, "_c22_data_loaded", lambda *a: True)
    at = AppTest.from_string("import streamlit as st\nfrom ui.field3_multisymbol_regime_summary_20260722 import _render_cycle92_signals_table\n_render_cycle92_signals_table(st, st.session_state)")
    for key, value in state_keys().items():
        at.session_state[key] = value
    at.run(timeout=20)
    assert not at.exception and not at.error
    payload = at.session_state[panel._C92_SIG_STATE_KEY]
    assert payload["n_evaluable"] == 20 and payload["diag"]["ready"] == 20
    pd.testing.assert_frame_equal(payload["signals"], panel._c22_signals_to_display(expected))
    assert len(calls) == 20 and set(calls) == {"15min"}
    assert any("ENTRY:" in str(e.value) for e in at.markdown)


def test_partial_universe_and_engine_errors_stay_retryable(monkeypatch):
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    from core import cycle92_best as engine
    monkeypatch.setattr(panel, "_record_eval_history", lambda *a, **k: None)
    now = pd.Timestamp("2026-10-26 18:00")
    frames = {s: candles([now-pd.Timedelta(hours=1), now]) for s in SYMBOLS}
    monkeypatch.setattr(panel, "_fetch_c22_frames", lambda *a, **k: (frames, now, {}))
    def broken(*args, **kwargs):
        raise RuntimeError("fixture error")
    monkeypatch.setattr(engine, "evaluate_cycle92_signals", broken)
    payload = panel._evaluate_c92_window({}, 18, day=now)
    assert payload["n_evaluable"] == 20 and panel._payload_data_failed(payload)
    assert payload["diag"]["evaluation_error"] and payload["signals"].empty
    frames.pop("USDJPY")
    payload = panel._evaluate_c92_window({}, 18, day=now)
    assert payload["n_evaluable"] == 19 and panel._payload_data_failed(payload)
    assert len(payload["ranking"]) == 20


@pytest.mark.parametrize("entry", [True, False])
def test_streamlit_panel_renders_entry_or_numeric_no_trade(monkeypatch, entry):
    from streamlit.testing.v1 import AppTest
    from ui import field3_multisymbol_regime_summary_20260722 as panel
    now = pd.Timestamp("2026-10-26 18:00")
    need = [now-pd.Timedelta(hours=1), now]
    frames = {s: candles(need) for s in SYMBOLS}
    sig = pd.DataFrame([dict(symbol="GBPJPY", direction="SELL", entry_px=210.233,
                             tp_pips=10, sl_pips=100, score=100)]) if entry else pd.DataFrame()
    payload = dict(window_utc=now, window_mmt="00:30", evaluated_at_utc=now, n_symbols=20,
                   n_evaluable=20, diag={}, signals=panel._c22_signals_to_display(sig),
                   ranking=panel._c22_build_check_ranking(sig, sig, frames, need))
    monkeypatch.setattr(panel, "_latest_entry_window_utc", lambda *a, **k: now)
    monkeypatch.setattr(panel, "_c22_data_loaded", lambda *a: True)
    monkeypatch.setattr(panel, "_evaluate_c92_window", lambda *a, **k: payload)
    at = AppTest.from_string("import streamlit as st\nfrom ui.field3_multisymbol_regime_summary_20260722 import _render_cycle92_signals_table\n_render_cycle92_signals_table(st, st.session_state)").run(timeout=20)
    assert not at.exception and not at.error
    text = " ".join(str(e.value) for e in at.markdown)
    assert ("ENTRY:" in text) == entry
    assert len(at.table) >= 1
    if not entry:
        assert any("No Cycle" in str(e.value) for e in at.info)
