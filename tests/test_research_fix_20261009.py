"""QA tests for the 2026-10-09 exit-registry research fix (command section 18).

Scope: the NEW ``*_20261009`` modules only. No app file is modified by these
tests. Everything asserted here is BEHAVIOR (computed outputs on constructed
inputs), not a restatement of implementation constants.

Test-only pytz shim: this sandbox's pytz lacks ``Asia/Rangoon`` (pre-existing
env issue). The shim below aliases it to ``Asia/Yangon`` (identical UTC+6:30,
no DST) for THIS test module only. It is installed at import time of this
module, so runs that exclude this file (e.g. the pre-existing suite failure-set
comparison) are unaffected.
"""

import csv
import hashlib
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

# --- test-only timezone shim (see module docstring) ---------------------------
import pytz as _pytz

_orig_pytz_timezone = _pytz.timezone


def _rangoon_shim(name, *args, **kwargs):
    if name == "Asia/Rangoon":
        return _orig_pytz_timezone("Asia/Yangon", *args, **kwargs)
    return _orig_pytz_timezone(name, *args, **kwargs)


_pytz.timezone = _rangoon_shim
# ------------------------------------------------------------------------------

import numpy as np
import pandas as pd
import pytest

APP_DIR = Path(__file__).resolve().parents[1]
ORIG_DIR = Path("/home/hatch/workspace/fx_fix/work/app_orig/Forex_App_Updated")
RESEARCH_DIR = Path("/home/hatch/workspace/fx_fix/work/results/results")

sys.path.insert(0, str(APP_DIR))

from core import exit_registry_20261009 as reg
from core import tpsl_price_calc_20261009 as calc
from core import cost_model_20261009 as cost
from core import replay_fixed_20261009 as replay
from core import validation_states_20261009 as vs
from core import metrics_honest_20261009 as mh
from core import drawdown_20261009 as dd
from core import cache_version_20261009 as cache
from core import exports_20261009 as exports


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

def _times(start, n):
    start = pd.Timestamp(start, tz="UTC")
    return pd.DatetimeIndex([start + pd.Timedelta(hours=i) for i in range(n)])


def _mk_tape(times, rows, *, pip=0.0001, bias=None, atr=0.0012,
             bar_range=0.0010, body=0.0001, friday=None, known=True):
    """Hand-built H1 tape in the shape replay_trade_fixed consumes.

    ``rows``: (n, 4) open/high/low/close. ``bias``/``atr``/``bar_range``/``body``
    are the COMPLETED-bar (shifted) exit features, i.e. what the engine is
    allowed to see when evaluating bar j.
    """
    n = len(times)
    prices = np.asarray(rows, dtype=float)
    assert prices.shape == (n, 4), prices.shape
    return {
        "lookup": {t: i for i, t in enumerate(times)},
        "pip": pip,
        "prices": prices,
        "times": times,
        "friday": np.zeros(n, dtype=bool) if friday is None else np.asarray(friday, dtype=bool),
        "exit_known": np.ones(n, dtype=bool) if known is True else np.asarray(known, dtype=bool),
        "exit_bias": np.zeros(n, dtype=int) if bias is None else np.asarray(bias, dtype=int),
        "exit_atr": np.full(n, float(atr)),
        "exit_range": np.full(n, float(bar_range)),
        "exit_body": np.full(n, float(body)),
    }


def _mk_signal(check, *, symbol="EURUSD", direction="BUY",
               eq="EQ-1", scol="S1", danger=False):
    """A replay signal whose fill bar is exactly check + 30 minutes."""
    check = pd.Timestamp(check, tz="UTC")
    entry = check + pd.Timedelta(minutes=30)
    return {"Datetime": entry.tz_localize(None), "check_at": check,
            "Direction": direction, "Symbol": symbol, "Equation ID": eq,
            "Active S Column": scol, "Danger Enabled": danger}


@pytest.fixture(scope="module")
def registry():
    return reg.load_registry(APP_DIR / "data" / "exit_registry_240.json")


@pytest.fixture(scope="module")
def research_rows():
    with open(RESEARCH_DIR / "strategy_recommendations_240.csv",
              newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _write_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


# ---------------------------------------------------------------------------
# 1. 240 mappings: identity, coverage, namespace separation
# ---------------------------------------------------------------------------

class TestRegistryIdentity:
    def test_exactly_240_entries(self, registry):
        assert len(registry["entries"]) == 240

    def test_identity_validation_passes(self, registry):
        assert reg.validate_identity(registry) == []

    def test_20_symbols_x_12_months(self, registry):
        entries = registry["entries"]
        assert {e["symbol"] for e in entries} and len({e["symbol"] for e in entries}) == 20
        assert {int(e["month"]) for e in entries} == set(range(1, 13))
        assert len({(e["symbol"], int(e["month"])) for e in entries}) == 240

    def test_s1_s240_each_maps_to_exactly_one_equation(self, registry):
        cols = [e["s_column"] for e in registry["entries"]]
        assert len(cols) == len(set(cols)) == 240
        assert sorted(cols, key=lambda c: int(c[1:])) == [f"S{i}" for i in range(1, 241)]
        # no S column is shared by two equations and no equation is orphaned
        pairs = [(e["s_column"], e["equation_id"]) for e in registry["entries"]]
        assert len(set(pairs)) == 240

    def test_every_entry_carries_expected_param_version(self, registry):
        assert all(e["parameter_version"] == reg.EXIT_PARAMS_VERSION
                   for e in registry["entries"])

    def test_strict_valid_is_no_everywhere(self, registry):
        assert all(e["strict_valid"] == "NO" for e in registry["entries"])

    def test_registry_never_imports_legacy_gating(self):
        """Namespace separation: the registry cannot consult a legacy
        S1-S120 BUY/SELL allowlist because it never imports legacy code —
        stdlib only."""
        import re
        src = Path(reg.__file__).read_text()
        # no import of any legacy entry/gating module (provenance strings in
        # the docstring may name them, but nothing is imported or called)
        assert not re.search(
            r"^\s*(from|import)\s+core\.(improved_strategy_config|monthly_runtime|"
            r"monthly_backtest|monthly_equations|live_execution)\b", src, re.M)
        assert "gate_signals(" not in src
        assert "ENFORCE_PAIR_ALLOWLIST" not in src
        # the only "allowlist" mention is the docstring's negative claim
        mentions = [ln for ln in src.lower().splitlines() if "allowlist" in ln]
        assert len(mentions) == 1 and "no legacy" in mentions[0]

    def test_no_new_module_consults_legacy_allowlist(self):
        for mod in (calc, cost, replay, vs, mh, dd, cache, exports):
            src = Path(mod.__file__).read_text()
            assert "ENFORCE_PAIR_ALLOWLIST" not in src, mod.__name__
            assert "gate_signals" not in src, mod.__name__

    def test_build_registry_takes_no_allowlist_input(self):
        assert list(inspect.signature(reg.build_registry).parameters) == [
            "app_root", "research_dir"]

    def test_mode_d_overrides_decided_from_registry_only(self, registry):
        """Admission overrides come from registry risk checks alone: every one
        of the 240 keys resolves to either tp/sl or a labelled rejection."""
        ov = reg.mode_d_overrides(registry)
        assert len(ov) == 240
        for key, val in ov.items():
            assert ("tp_pips" in val and "sl_pips" in val) or "rejected" in val, key
        rejected = reg.rejected_summary(registry)
        assert rejected["total_rejected"] == sum(
            1 for v in ov.values() if "rejected" in v)
        assert set(rejected["by_reason"]) <= {
            "REJECT_REWARD_RISK", "REJECT_STOP_BUDGET", "REJECT_MISSING_PARAMS"}


# ---------------------------------------------------------------------------
# 2. Original entry-signal parity: fixed copy vs pristine original copy
# ---------------------------------------------------------------------------

PARITY_PROBE = r'''
import os, sys, json, hashlib
APP = os.environ["APP_DIR"]
sys.path.insert(0, APP)
import pytz
_o = pytz.timezone
pytz.timezone = lambda n, *a, **k: _o("Asia/Yangon", *a, **k) if n == "Asia/Rangoon" else _o(n, *a, **k)
import numpy as np, pandas as pd
from core.monthly_runtime import build_history, raw_frame, ENGINE_VERSION
from core.monthly_strategy_columns import evaluate_check_columns, STRATEGY_COLUMNS
from core.monthly_backtest import make_tapes

rng = np.random.default_rng(7)
times = pd.date_range("2025-12-01 00:00", "2026-02-03 23:00", freq="h", tz="UTC")
times = times[times.dayofweek < 5]
n = len(times)
px = 1.10 + np.cumsum(rng.normal(0, 0.0012, n))
df = pd.DataFrame({"Datetime": times.tz_localize(None), "Symbol": "EURUSD",
                   "Open": px,
                   "High": px + np.abs(rng.normal(0, 0.0008, n)) + 0.0002,
                   "Low": px - np.abs(rng.normal(0, 0.0008, n)) - 0.0002,
                   "Close": px + rng.normal(0, 0.0005, n)})

# (a) full entry-signal frame: all 240 strategy columns + metadata
hist = build_history(df)
scols = [c for c in hist.columns if c in set(STRATEGY_COLUMNS)]
mcols = ["check_at", "Symbol", "Equation ID", "Active S Column", "Direction",
         "Strategy Hit Count", "Equation Month", "Improved Rank", "ranking_score",
         "Signal ATR", "Research Middle Bias", "signal_bar_open", "signal_at",
         "Suggested TP Pips", "Suggested SL Pips", "Strategy Engine",
         "Max Hold Hours", "Danger Enabled"]
frame = hist[[c for c in mcols + scols if c in hist.columns]].copy()
for c in frame.columns:
    if frame[c].dtype.kind == "M":
        frame[c] = pd.to_datetime(frame[c], utc=True, errors="coerce").astype(str)
fp_hist = hashlib.sha256(frame.to_csv(index=False).encode()).hexdigest()

# (b) check-time candidate selection at 3 sample check timestamps
raw = raw_frame(df)
tapes = make_tapes(raw)
candles = {"EURUSD": tapes["EURUSD"]["frame"]}
checks = ["2026-01-12 06:30:00+00:00", "2026-01-13 11:30:00+00:00",
          "2026-02-02 12:30:00+00:00"]
fp_checks = {}
for t in checks:
    res = evaluate_check_columns(candles, pd.Timestamp(t))
    tab = res["table"].copy()
    sel = json.dumps(res["selected"], default=str, sort_keys=True)
    fp_checks[t] = hashlib.sha256(
        (tab.to_csv(index=False) + "|" + sel).encode()).hexdigest()

print(json.dumps({"engine": ENGINE_VERSION, "rows": len(hist),
                  "hist": fp_hist, "checks": fp_checks}))
'''


class TestEntrySignalParity:
    """Diff-test: the NEW replay module builds entry signals via
    ``core.monthly_runtime.build_history``; that path must produce byte-identical
    outputs in the fixed copy and the pristine original copy.

    Compared, on one deterministic synthetic EURUSD H1 slice (~1300 bars):
      (a) the full build_history frame — all 240 S1..S240 signal columns plus
          signal metadata (check_at, Equation ID, Direction, hit count,
          equation month, ranks, ATR, bias, suggested TP/SL, engine id);
      (b) check-time candidate selection (evaluate_check_columns: 20-symbol x
          240-column table + selected candidate) at 3 check timestamps
          (2026-01-12 06:30, 2026-01-13 11:30, 2026-02-02 12:30 UTC).
    Each side runs in its own subprocess with the app dir first on sys.path;
    only stdout fingerprints are compared (read-only import of both copies).
    """

    @pytest.fixture(scope="class")
    def fingerprints(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("parity")
        probe = tmp / "parity_probe.py"
        probe.write_text(PARITY_PROBE)
        outs = {}
        for name, appdir in (("fixed", APP_DIR), ("orig", ORIG_DIR)):
            env = dict(os.environ, APP_DIR=str(appdir),
                       PYTHONDONTWRITEBYTECODE="1")
            r = subprocess.run([sys.executable, str(probe)], env=env,
                               capture_output=True, text=True, timeout=900,
                               cwd=str(appdir))
            assert r.returncode == 0, (
                f"parity probe failed in {name} copy:\n{r.stderr[-3000:]}")
            outs[name] = json.loads(r.stdout)
        return outs

    def test_engine_version_identical(self, fingerprints):
        assert fingerprints["fixed"]["engine"] == fingerprints["orig"]["engine"]

    def test_signal_frame_identical(self, fingerprints):
        assert fingerprints["fixed"]["rows"] == fingerprints["orig"]["rows"] > 0
        assert fingerprints["fixed"]["hist"] == fingerprints["orig"]["hist"]

    def test_check_time_selection_identical(self, fingerprints):
        assert fingerprints["fixed"]["checks"] == fingerprints["orig"]["checks"]
        assert len(fingerprints["fixed"]["checks"]) == 3


# ---------------------------------------------------------------------------
# 3. Completed-bar / future-data exclusion (no lookahead)
# ---------------------------------------------------------------------------

class TestCompletedBarExclusion:
    @pytest.fixture(scope="class")
    def ohlc(self):
        """Two weeks of contiguous weekday H1 bars (session filter keeps all;
        Datetime order == positional order)."""
        from core.monthly_runtime import raw_frame
        rng = np.random.default_rng(21)
        # Monday start: the NY session mask in session_filter then keeps every
        # bar, so raw positional rows == session-filtered positional rows.
        bars = pd.date_range("2026-01-05 00:00", "2026-01-16 21:00",
                             freq="h", tz="UTC")
        bars = bars[bars.dayofweek < 5]
        # Friday 22:00/23:00 UTC = Friday evening New York: the app's NY
        # session mask drops those two bars; exclude them up front so raw
        # positional rows == session-filtered positional rows.
        bars = bars[~((bars.dayofweek == 4) & (bars.hour >= 22))]
        n = len(bars)
        px = 1.10 + np.cumsum(rng.normal(0, 0.0009, n))
        op = px
        cl = px + rng.normal(0, 0.0004, n)
        hi = np.maximum(op, cl) + np.abs(rng.normal(0, 0.0006, n)) + 0.0002
        lo = np.minimum(op, cl) - np.abs(rng.normal(0, 0.0006, n)) - 0.0002
        df = pd.DataFrame({"Datetime": bars.tz_localize(None), "Symbol": "EURUSD",
                           "Open": op, "High": hi, "Low": lo, "Close": cl})
        raw = raw_frame(df)
        from core import monthly_equations as _eng
        g = _eng.session_filter(raw)
        assert len(g) == len(raw) and len(g) >= 200
        return raw

    def _check_row(self, raw):
        # first row with a valid check: utc_check = Datetime - 30min at 06:30,
        # away from the weekend gap, index >= 122
        dt = pd.to_datetime(raw["Datetime"])
        chk = dt - pd.Timedelta(minutes=30)
        for i in range(130, len(raw)):
            if (chk.iloc[i].hour == 6 and chk.iloc[i].dayofweek < 5
                    and (dt.iloc[i] - dt.iloc[i - 2]) == pd.Timedelta(hours=2)):
                return i
        raise AssertionError("no eligible check row found")

    def test_forming_bars_cannot_change_signal(self, ohlc):
        """Mutating the forming bar (i) and the just-closed bar (i-1) with a
        wild-but-valid spike must not change any S-column at check row i."""
        from core.monthly_strategy_columns import build_replay_columns, STRATEGY_COLUMNS
        raw = ohlc
        i = self._check_row(raw)
        b1 = build_replay_columns(raw)
        mut = raw.copy()
        for j in (i - 1, i):
            mut.loc[j, ["Open", "Close"]] = 2.0
            mut.loc[j, "High"] = 2.02
            mut.loc[j, "Low"] = 1.98
        b2 = build_replay_columns(mut)
        scols = [c for c in b1.columns if c in set(STRATEGY_COLUMNS)]
        assert len(scols) == 240
        pd.testing.assert_frame_equal(b1[scols].iloc[[i]], b2[scols].iloc[[i]])
        # causality: earlier rows are untouched by later-bar mutations too
        pd.testing.assert_frame_equal(b1[scols].iloc[:i], b2[scols].iloc[:i])

    def test_two_bar_lag_is_real_not_vacuous(self, ohlc):
        """Positive control: the same mutation DOES move the documented
        shifted features two bars later (shift(2) contract)."""
        from core import monthly_equations as eng
        from core.monthly_runtime import raw_frame
        raw = ohlc
        i = self._check_row(raw)
        g = eng.session_filter(raw_frame(raw))
        gm = g.copy()
        for j in (i - 1, i):
            gm.loc[j, ["Open", "Close"]] = 2.0
            gm.loc[j, "High"] = 2.02
            gm.loc[j, "Low"] = 1.98
        f1, f2 = eng.make_features(g), eng.make_features(gm)
        s1 = f1[eng.ALL_FEATURES].shift(2)
        s2 = f2[eng.ALL_FEATURES].shift(2)
        pd.testing.assert_frame_equal(s1.iloc[[i]], s2.iloc[[i]])
        assert not s1.iloc[i + 2].equals(s2.iloc[i + 2])

    def test_entry_fill_uses_bar_open_only(self):
        """The replay fill is the entry bar's OPEN; the forming bar's
        high/low/close are never peeked at for the fill price."""
        times = _times("2026-01-12 07:00", 3)
        tape = _mk_tape(times, [[1.1000, 1.1500, 1.0995, 1.1490],   # wild forming bar
                                [1.1490, 1.1495, 1.1485, 1.1490],
                                [1.1490, 1.1495, 1.1485, 1.1490]])
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False)
        assert tr["entry_price"] == pytest.approx(1.1000)  # the open, exactly
        assert tr["exit_reason"] == "TP"
        assert tr["exit_price"] == pytest.approx(1.1030)   # target from the open


# ---------------------------------------------------------------------------
# 4. Myanmar/UTC conversion + month boundaries
# ---------------------------------------------------------------------------

class TestMyanmarMonthConvention:
    def test_boundary_check_uses_myanmar_month(self, registry):
        # 2026-01-31 19:30 UTC = 2026-02-01 02:00 +06:30 (verified: 19:30+6:30).
        # UTC month is January; Myanmar month is February.
        check = pd.Timestamp("2026-01-31 19:30", tz="UTC")
        local = check.tz_convert("Asia/Rangoon")
        assert (local.year, local.month, local.day,
                local.hour, local.minute) == (2026, 2, 1, 2, 0)
        assert check.month == 1 and local.month == 2
        # the registry documents exactly this convention for equation months
        entry = registry["entries"][0]
        assert entry["month_timezone"] == "Asia/Rangoon (Myanmar)"
        assert "Myanmar month of the check timestamp" in entry["month_selection_note"]

    def test_legacy_ktp_lookup_kept_as_utc_month(self, registry):
        """Mode B/E k_tp lookup deliberately keeps legacy UTC-month semantics;
        the registry documents the contrast instead of reinterpreting it."""
        entry = registry["entries"][0]
        assert "UTC month" in entry["exit_modes"]["B_legacy_app"]["k_tp_cell_key_semantics"]
        assert "not reinterpreted" in entry["month_selection_note"]


# ---------------------------------------------------------------------------
# 5. Parameter imports: malformed rows fail safe with labelled reasons;
#    stale parameter versions are rejected
# ---------------------------------------------------------------------------

class TestParameterImports:
    def _corrupted_csv(self, tmp_path, research_rows, mutate):
        rows = [dict(r) for r in research_rows]
        by_id = {r["Strategy ID"]: r for r in rows}
        mutate(by_id)
        path = tmp_path / "strategy_recommendations_240.csv"
        _write_csv(rows, path)
        return tmp_path

    def test_malformed_rows_labelled_not_silent(self, tmp_path, research_rows):
        research_dir = self._corrupted_csv(
            tmp_path, research_rows,
            lambda b: (b["S1"].__setitem__("Compatible SL pips", ""),   # missing SL
                       b["S2"].__setitem__("Compatible TP pips", "-50")))  # negative TP
        registry = reg.build_registry(APP_DIR, research_dir)
        by_col = {e["s_column"]: e for e in registry["entries"]}

        e1 = by_col["S1"]
        c1 = e1["exit_modes"]["C_compatible_research"]
        assert c1["available"] is False
        assert "FALLBACK" in c1["reason"]  # explicitly labelled, never silent
        d1 = e1["exit_modes"]["D_active_compatible"]
        assert d1["available"] is False
        assert d1["rejection_reason"] == "REJECT_MISSING_PARAMS"

        e2 = by_col["S2"]
        d2 = e2["exit_modes"]["D_active_compatible"]
        assert d2["available"] is False
        assert d2["rejection_reason"] == "REJECT_REWARD_RISK"

        # the overrides map surfaces the same labelled rejections to admission
        ov = reg.mode_d_overrides(registry)
        assert ov[(e1["symbol"], e1["equation_id"])] == {
            "rejected": "REJECT_MISSING_PARAMS"}
        assert ov[(e2["symbol"], e2["equation_id"])] == {
            "rejected": "REJECT_REWARD_RISK"}

    def test_month_13_rejected_with_reason(self, tmp_path, research_rows):
        research_dir = self._corrupted_csv(
            tmp_path, research_rows,
            lambda b: b["S3"].__setitem__("Month", "13"))
        with pytest.raises(reg.RegistryError) as excinfo:
            reg.build_registry(APP_DIR, research_dir)
        assert "months incomplete" in str(excinfo.value)

    def test_stale_parameter_version_rejected(self):
        def fp(exit_params_version, cost_scenario):
            return cache.fingerprint(
                equation_ids=["EQ-1"], engine_version="monthly-240-v1",
                exit_params_version=exit_params_version,
                check_schedule={"hours_utc": [6, 7, 10, 11, 12, 13], "minute": 30},
                admission_rules={"k": 4}, filters={},
                cost_model={"scenario": cost_scenario},
                intrabar_priority="SL_FIRST", holding_policy={"cap_hours": 48},
                censorship_policy="research_release_unknown",
                source_sha256="abc")

        current = fp(reg.EXIT_PARAMS_VERSION, "legacy_1pip")
        stale_params = fp("v2-20990101", "legacy_1pip")
        stale_cost = fp(reg.EXIT_PARAMS_VERSION, "sensitivity_3pip")
        assert stale_params != current and stale_cost != current

        stored = cache.wrap({"net_pips": 1.0}, input_fingerprint=stale_params,
                            config_label="run", data_period="2026")
        with pytest.raises(cache.StaleCacheError):
            cache.check(stored, current_fingerprint=current)

        # a matching fingerprint passes through untouched
        fresh = cache.wrap({"net_pips": 1.0}, input_fingerprint=current,
                           config_label="run", data_period="2026")
        assert cache.check(fresh, current_fingerprint=current)["net_pips"] == 1.0


# ---------------------------------------------------------------------------
# 6. BUY/SELL target prices; JPY (0.01) vs non-JPY (0.0001) pip sizes
# ---------------------------------------------------------------------------

class TestTargetPrices:
    def test_buy_nonjpy(self):
        r = calc.target_prices(1.1000, "BUY", 30, 10, "EURUSD")
        assert r["pip_size"] == 0.0001
        assert r["tp_price"] == pytest.approx(1.1030)   # 1.1000 + 30 x 0.0001
        assert r["sl_price"] == pytest.approx(1.0990)   # 1.1000 - 10 x 0.0001
        assert r["side"] == "BUY"

    def test_sell_nonjpy(self):
        r = calc.target_prices(1.1000, "SELL", 30, 10, "EURUSD")
        assert r["tp_price"] == pytest.approx(1.0970)   # 1.1000 - 30 x 0.0001
        assert r["sl_price"] == pytest.approx(1.1010)   # 1.1000 + 10 x 0.0001

    def test_buy_jpy(self):
        r = calc.target_prices(150.00, "BUY", 30, 10, "USDJPY")
        assert r["pip_size"] == 0.01
        assert r["tp_price"] == pytest.approx(150.30)   # 150.00 + 30 x 0.01
        assert r["sl_price"] == pytest.approx(149.90)   # 150.00 - 10 x 0.01

    def test_sell_jpy(self):
        r = calc.target_prices(150.00, "SELL", 30, 10, "USDJPY")
        assert r["tp_price"] == pytest.approx(149.70)   # 150.00 - 30 x 0.01
        assert r["sl_price"] == pytest.approx(150.10)   # 150.00 + 10 x 0.01

    def test_buy_sell_mirror_symmetry(self):
        b = calc.target_prices(1.1000, "BUY", 30, 10, "EURUSD")
        s = calc.target_prices(1.1000, "SELL", 30, 10, "EURUSD")
        assert (b["tp_price"] - 1.1000) == pytest.approx(1.1000 - s["tp_price"])
        assert (1.1000 - b["sl_price"]) == pytest.approx(s["sl_price"] - 1.1000)

    def test_price_basis_labels(self):
        r = calc.target_prices(1.1000, "BUY", 30, 10, "EURUSD",
                               price_basis="RESEARCH_FILL")
        assert r["price_basis"] == "RESEARCH_FILL"
        assert "RESEARCH FILL" in r["price_basis_label"]

    def test_invalid_inputs_raise(self):
        with pytest.raises(ValueError):
            calc.target_prices(0, "BUY", 30, 10, "EURUSD")       # entry <= 0
        with pytest.raises(ValueError):
            calc.target_prices(1.1, "BUY", 0, 10, "EURUSD")       # TP <= 0
        with pytest.raises(ValueError):
            calc.target_prices(1.1, "BUY", 30, -5, "EURUSD")      # SL < 0
        with pytest.raises(ValueError):
            calc.target_prices(float("nan"), "BUY", 30, 10, "EURUSD")
        with pytest.raises(ValueError):
            calc.target_prices(1.1, "BUY", 30, 10, "EURUSD",
                               price_basis="EXECUTABLE_GUESS")    # unknown basis
        with pytest.raises(ValueError):
            calc.target_prices(1.1, "HOLD", 30, 10, "EURUSD")     # unknown side


# ---------------------------------------------------------------------------
# 7. Missing/invalid exit settings -> explicitly labelled fallback
# ---------------------------------------------------------------------------

class TestFallbackLabelling:
    def test_unknown_equation_records_labelled_rejection(self, tmp_path):
        """Admission with no registry entry for an equation records
        NO_REGISTRY_ENTRY on the check decision — never silently skipped."""
        env = _portfolio_env()
        sig = _portfolio_signals(env, [5, 4, 3, 2, 1])
        res = replay.replay_portfolio_fixed(
            env["raw"], signals=sig, exit_overrides={},   # nothing registered
            entry_start=env["check"] - pd.Timedelta(hours=2),
            entry_end=env["check"] + pd.Timedelta(hours=2))
        assert len(res["trades"]) == 0
        row = res["checks"].loc[res["checks"].check_at == env["check"]].iloc[0]
        assert "NO_REGISTRY_ENTRY" in row["exit_rejections"]

    def test_rejected_equation_records_gate_reason(self):
        env = _portfolio_env()
        sig = _portfolio_signals(env, [5])
        ov = {(env["symbols"][0], "EQ-" + env["symbols"][0]):
              {"rejected": "REJECT_STOP_BUDGET"}}
        res = replay.replay_portfolio_fixed(
            env["raw"], signals=sig, exit_overrides=ov,
            entry_start=env["check"] - pd.Timedelta(hours=2),
            entry_end=env["check"] + pd.Timedelta(hours=2))
        assert len(res["trades"]) == 0
        row = res["checks"].loc[res["checks"].check_at == env["check"]].iloc[0]
        assert "REJECT_STOP_BUDGET" in row["exit_rejections"]


# ---------------------------------------------------------------------------
# 8. Reward/risk gate: (TP - cost) >= 0.5 x SL, with cost sensitivity
# ---------------------------------------------------------------------------

class TestRiskGate:
    def test_pass(self):
        checks = reg.risk_gate(30, 10)          # (30-1)=29 >= 5 ; 10 <= 103
        assert all(c["passed"] for c in checks)
        assert all(c["rejection_reason"] is None for c in checks)

    def test_reward_risk_rejection(self):
        checks = reg.risk_gate(10, 30)          # (10-1)=9 < 15
        failed = [c for c in checks if not c["passed"]]
        assert any(c["rejection_reason"] == "REJECT_REWARD_RISK" for c in failed)
        assert all("REJECT_REWARD_RISK" in (c["rejection_reason"] or "")
                   for c in failed if c["check"] == "reward_risk")

    def test_stop_budget_rejection(self):
        checks = reg.risk_gate(300, 200)        # (300-1)=299 >= 100 but 200 > 103
        failed = [c for c in checks if not c["passed"]]
        assert any(c["rejection_reason"] == "REJECT_STOP_BUDGET" for c in failed)

    def test_cost_sensitivity(self):
        # TP=17, SL=30: (17-1)=16 >= 15 passes at 1 pip cost,
        #               (17-3)=14 <  15 fails at 3 pips cost.
        assert all(c["passed"] for c in reg.risk_gate(17, 30, cost_pips=1.0))
        failed = [c for c in reg.risk_gate(17, 30, cost_pips=3.0)
                  if not c["passed"]]
        assert any(c["rejection_reason"] == "REJECT_REWARD_RISK" for c in failed)

    def test_boundary_is_inclusive(self):
        # (TP - cost) exactly equals 0.5 x SL -> passes
        assert all(c["passed"] for c in reg.risk_gate(16, 30, cost_pips=1.0))


# ---------------------------------------------------------------------------
# Portfolio-test scaffolding (synthetic market + signals at one check)
# ---------------------------------------------------------------------------

def _portfolio_env(*, touch_entry_bar=True, flat=False, seed=11):
    """5-symbol synthetic H1 market around one Monday 06:30 UTC check.

    touch_entry_bar=True: the 07:00 entry bar straddles 5-pip barriers so a
    5/5-pip trade exits ambiguously on the entry bar itself.
    flat=True: all bars pinned (no barrier can touch) — for censorship tests.
    """
    from core.monthly_backtest import make_tapes
    from core.monthly_runtime import raw_frame
    rng = np.random.default_rng(seed)
    symbols = ["EURUSD", "GBPUSD", "USDCHF", "USDCAD", "NZDUSD"]
    check = pd.Timestamp("2026-01-12 06:30", tz="UTC")      # a Monday
    entry = check + pd.Timedelta(minutes=30)
    bars = pd.date_range("2026-01-09 00:00", "2026-01-13 23:00",
                         freq="h", tz="UTC")
    bars = bars[bars.dayofweek < 5]
    frames = []
    for s in symbols:
        n = len(bars)
        if flat:
            px = np.full(n, 1.1000)
        else:
            px = 1.10 + np.cumsum(rng.normal(0, 0.0006, n))
        op = px
        cl = px + rng.normal(0, 0.0003, n)
        hi = np.maximum(op, cl) + np.abs(rng.normal(0, 0.0004, n)) + 0.0002
        lo = np.minimum(op, cl) - np.abs(rng.normal(0, 0.0004, n)) - 0.0002
        f = pd.DataFrame({"Datetime": bars.tz_localize(None), "Symbol": s,
                          "Open": op, "High": hi, "Low": lo, "Close": cl})
        if touch_entry_bar:
            m = f["Datetime"] == entry.tz_localize(None)
            o = f.loc[m, "Open"].to_numpy()
            f.loc[m, "High"] = o + 0.0010
            f.loc[m, "Low"] = o - 0.0010
        elif flat:
            f["High"] = f["Open"]
            f["Low"] = f["Open"]
            f["Close"] = f["Open"]
        frames.append(f)
    raw = raw_frame(pd.concat(frames, ignore_index=True))
    return {"check": check, "entry": entry, "raw": raw,
            "tapes": make_tapes(raw), "symbols": symbols}


def _portfolio_signals(env, ranks, *, dup_symbol=False):
    from core.monthly_runtime import ENGINE_VERSION
    rows = []
    for k, (sym, rank) in enumerate(zip(env["symbols"], ranks)):
        rows.append({"Datetime": env["entry"].tz_localize(None),
                     "check_at": env["check"], "Strategy Hit Count": 1,
                     "Symbol": sym, "Equation ID": f"EQ-{sym}",
                     "Active S Column": f"S{k + 1}", "Direction": "BUY",
                     "Strategy Engine": ENGINE_VERSION,
                     "Improved Rank": rank, "Danger Enabled": False})
    if dup_symbol:
        rows.append({"Datetime": env["entry"].tz_localize(None),
                     "check_at": env["check"], "Strategy Hit Count": 1,
                     "Symbol": env["symbols"][0],
                     "Equation ID": f"EQ-{env['symbols'][0]}-B",
                     "Active S Column": "S99", "Direction": "BUY",
                     "Strategy Engine": rows[0]["Strategy Engine"],
                     "Improved Rank": 1, "Danger Enabled": False})
    return pd.DataFrame(rows)


def _overrides(env, symbols, *, tp=5.0, sl=5.0):
    return {(s, f"EQ-{s}"): {"tp_pips": tp, "sl_pips": sl} for s in symbols}


def _run_portfolio(env, signals, overrides, **kw):
    kw.setdefault("entry_start", env["check"] - pd.Timedelta(hours=2))
    kw.setdefault("entry_end", env["check"] + pd.Timedelta(hours=2))
    return replay.replay_portfolio_fixed(env["raw"], signals=signals,
                                         exit_overrides=overrides, **kw)


# ---------------------------------------------------------------------------
# 9. Intrabar exits: TP-only / SL-only / dual-touch / gaps / caps / Friday
# ---------------------------------------------------------------------------

class TestIntrabarExits:
    """Hand-computed: BUY EURUSD @1.1000, TP 30 pips -> 1.1030,
    SL 10 pips -> 1.0990, cost 1 pip."""

    def _trade(self, rows, **kw):
        times = _times("2026-01-12 07:00", len(rows))
        tape = _mk_tape(times, rows, **kw.pop("tape_kw", {}))
        sig = _mk_signal("2026-01-12 06:30")
        return replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                         hold_hours=48, danger_enabled=False,
                                         **kw)

    def test_tp_only_candle(self):
        tr = self._trade([[1.1000, 1.1035, 1.0995, 1.1010],
                          [1.1010, 1.1015, 1.1005, 1.1010],
                          [1.1010, 1.1015, 1.1005, 1.1010]])
        assert tr["exit_reason"] == "TP"
        assert tr["exit_price"] == pytest.approx(1.1030)
        assert tr["gross_pips"] == pytest.approx(30.0)
        assert tr["net_pips"] == pytest.approx(29.0)      # 30 - 1 pip, once
        assert tr["ambiguous"] is False
        assert tr["exit_at"] == pd.Timestamp("2026-01-12 08:00", tz="UTC")

    def test_sl_only_candle(self):
        tr = self._trade([[1.1000, 1.1005, 1.0985, 1.0990],
                          [1.0990, 1.0995, 1.0985, 1.0990]])
        assert tr["exit_reason"] == "SL"
        assert tr["exit_price"] == pytest.approx(1.0990)
        assert tr["gross_pips"] == pytest.approx(-10.0)
        assert tr["net_pips"] == pytest.approx(-11.0)
        assert tr["ambiguous"] is False

    def test_dual_touch_defaults_to_sl(self):
        tr = self._trade([[1.1000, 1.1040, 1.0985, 1.1000],
                          [1.1000, 1.1005, 1.0995, 1.1000]])
        assert tr["ambiguous"] is True
        assert tr["exit_reason"] == "SL"                  # SL_FIRST default
        assert tr["net_pips"] == pytest.approx(-11.0)
        assert tr["net_pips_sl_first"] == pytest.approx(-11.0)
        assert tr["net_pips_tp_first"] == pytest.approx(29.0)
        assert tr["intrabar_priority"] == "SL_FIRST"

    def test_dual_touch_legacy_mode_takes_tp(self):
        tr = self._trade([[1.1000, 1.1040, 1.0985, 1.1000],
                          [1.1000, 1.1005, 1.0995, 1.1000]],
                         priority="TP_FIRST")
        assert tr["ambiguous"] is True
        assert tr["exit_reason"] == "TP"                  # legacy comparison mode
        assert tr["net_pips"] == pytest.approx(29.0)
        assert tr["net_pips_sl_first"] == pytest.approx(-11.0)
        assert tr["net_pips_tp_first"] == pytest.approx(29.0)

    def test_bad_priority_raises(self):
        with pytest.raises(ValueError):
            self._trade([[1.1000, 1.1005, 1.0995, 1.1000]], priority="MIDDLE")

    def test_adverse_gap_fills_at_observed_open(self):
        tr = self._trade([[1.1000, 1.1005, 1.0995, 1.1000],   # entry bar: calm
                          [1.0980, 1.0985, 1.0975, 1.0980]])  # gaps through stop
        assert tr["exit_reason"] == "SL"
        assert tr["exit_price"] == pytest.approx(1.0980)  # observed open...
        assert tr["exit_price"] != pytest.approx(1.0990)  # ...never the stop
        assert tr["stop_gap"] is True
        assert tr["gross_pips"] == pytest.approx(-20.0)   # (1.0980-1.1000)/pip

    def test_favourable_gap_fills_at_target(self):
        tr = self._trade([[1.1000, 1.1005, 1.0995, 1.1000],
                          [1.1040, 1.1045, 1.1035, 1.1040]])  # gaps through target
        assert tr["exit_reason"] == "TP"
        assert tr["exit_price"] == pytest.approx(1.1030)

    def test_holding_cap_closes_at_scheduled_bar(self):
        times = _times("2026-01-12 07:00", 5)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000]] * 5      # never touches
        tape = _mk_tape(times, rows)
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=2, danger_enabled=False)
        assert tr["exit_reason"] == "HOLD_CAP"
        assert tr["exit_at"] == pd.Timestamp("2026-01-12 09:00", tz="UTC")
        assert tr["exit_price"] == pytest.approx(1.1000)  # bar open

    def test_friday_close(self):
        times = _times("2026-01-12 07:00", 3)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000],
                [1.1002, 1.1008, 1.0998, 1.1004],           # Friday bar
                [1.1004, 1.1009, 1.0999, 1.1005]]
        tape = _mk_tape(times, rows, friday=[False, True, False])
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False)
        assert tr["exit_reason"] == "FRIDAY_CLOSE"
        assert tr["exit_price"] == pytest.approx(1.1004)  # bar close
        assert tr["exit_at"] == pd.Timestamp("2026-01-12 08:00", tz="UTC") + \
            pd.Timedelta(hours=1)

    def test_scheduled_exit_beats_barrier(self):
        """Documented deviation from legacy: a Friday bar that also touches the
        stop closes as FRIDAY_CLOSE (scheduled exits evaluate first)."""
        times = _times("2026-01-12 07:00", 3)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000],
                [1.1002, 1.1008, 1.0980, 1.1004],           # Friday + SL touch
                [1.1004, 1.1009, 1.0999, 1.1005]]
        tape = _mk_tape(times, rows, friday=[False, True, False])
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False)
        assert tr["exit_reason"] == "FRIDAY_CLOSE"
        assert tr["exit_price"] == pytest.approx(1.1004)

    def test_eval_order_is_documented(self):
        assert replay.EXIT_EVAL_ORDER == ("OPEN_CHECKS", "FRIDAY_CLOSE",
                                          "HOLD_CAP", "BIAS_FLIP", "DANGER",
                                          "BARRIERS")


# ---------------------------------------------------------------------------
# 10. Bias-flip and danger exits (from completed-bar information only)
# ---------------------------------------------------------------------------

class TestBiasDangerExits:
    def _tape(self, *, bias, atr=0.0012, bar_range=0.0010, body=0.0001,
              danger_enabled=False):
        times = _times("2026-01-12 07:00", 4)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000]] * 4     # flat, no touches
        tape = _mk_tape(times, rows, bias=bias, atr=atr,
                        bar_range=bar_range, body=body)
        sig = _mk_signal("2026-01-12 06:30", danger=danger_enabled)
        return replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                         hold_hours=48,
                                         danger_enabled=danger_enabled)

    def test_bias_flip_closes_with_reason(self):
        tr = self._tape(bias=[1, 1, -1, 1])               # flips vs BUY at bar 2
        assert tr["exit_reason"] == "BIAS_FLIP"
        assert tr["exit_price"] == pytest.approx(1.1000)  # bar open
        assert tr["exit_at"] == pd.Timestamp("2026-01-12 09:00", tz="UTC")

    def test_current_bar_bias_cannot_trigger(self):
        """No-lookahead control: exit_bias is the completed-bar value; a flip
        that exists only in unshifted data must not exit."""
        tr = self._tape(bias=[1, 1, 1, 1])
        assert tr["exit_reason"] != "BIAS_FLIP"

    def test_danger_exit_closes_with_reason(self):
        # range 40 pips > 3 x ATR(10 pips); adverse body -6 pips < -0.5 x ATR
        tape_times = _times("2026-01-12 07:00", 4)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000]] * 4
        tape = _mk_tape(tape_times, rows, bias=[1, 1, 1, 1], atr=0.0012,
                        bar_range=0.0010, body=0.0001)
        tape["exit_atr"][2] = 0.0010
        tape["exit_range"][2] = 0.0040
        tape["exit_body"][2] = -0.0006
        sig = _mk_signal("2026-01-12 06:30", danger=True)
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=True)
        assert tr["exit_reason"] == "DANGER"
        assert tr["exit_price"] == pytest.approx(1.1000)
        assert tr["exit_at"] == pd.Timestamp("2026-01-12 09:00", tz="UTC")

    def test_danger_disabled_no_exit(self):
        tape_times = _times("2026-01-12 07:00", 4)
        rows = [[1.1000, 1.1005, 1.0995, 1.1000]] * 4
        tape = _mk_tape(tape_times, rows, bias=[1, 1, 1, 1])
        tape["exit_atr"][2] = 0.0010
        tape["exit_range"][2] = 0.0040
        tape["exit_body"][2] = -0.0006
        sig = _mk_signal("2026-01-12 06:30", danger=False)
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False)
        assert tr["exit_reason"] != "DANGER"


# ---------------------------------------------------------------------------
# 11-13. Admission: no duplicate symbols, 1/2/4-entry modes, unresolved held
# ---------------------------------------------------------------------------

class TestAdmission:
    def test_no_duplicate_symbol_holdings(self, monkeypatch):
        env = _portfolio_env()
        sig = _portfolio_signals(env, [10, 5], dup_symbol=True)  # 2x EURUSD
        sig.loc[sig["Equation ID"] == "EQ-EURUSD-B", "Improved Rank"] = 1
        ov = _overrides(env, env["symbols"])
        ov[("EURUSD", "EQ-EURUSD-B")] = {"tp_pips": 5.0, "sl_pips": 5.0}
        res = _run_portfolio(env, sig, ov)
        eurusd = res["trades"].loc[res["trades"].Symbol == "EURUSD"]
        assert len(eurusd) == 1
        # the higher-ranked equation won the single slot
        assert eurusd.iloc[0]["Equation ID"] == "EQ-EURUSD"

    @pytest.mark.parametrize("k,expected", [(1, 1), (2, 2), (4, 4)])
    def test_entry_modes_1_2_4(self, monkeypatch, k, expected):
        env = _portfolio_env()
        sig = _portfolio_signals(env, [5, 4, 3, 2, 1])   # 5 ranked candidates
        ov = _overrides(env, env["symbols"])
        monkeypatch.setattr(replay, "K_ENTRIES_PER_CHECK", k)
        res = _run_portfolio(env, sig, ov)
        assert len(res["trades"]) == expected
        row = res["checks"].loc[res["checks"].check_at == env["check"]].iloc[0]
        assert len(row["selected"].split(",")) == expected
        # top-ranked candidates were taken
        assert set(row["selected"].split(",")) == set(env["symbols"][:expected])

    def test_unresolved_positions_stay_open_unknown(self):
        env = _portfolio_env(flat=True, touch_entry_bar=False)
        sig = _portfolio_signals(env, [5, 4, 3, 2, 1])
        ov = _overrides(env, env["symbols"])
        res = _run_portfolio(env, sig, ov,
                             research_end=env["entry"] + pd.Timedelta(minutes=90))
        assert len(res["trades"]) == 4   # K_ENTRIES_PER_CHECK default is 4
        assert (res["trades"]["outcome_state"] == "UNRESOLVED_UNKNOWN").all()
        assert res["trades"]["net_pips"].isna().all()
        # never auto-zeroed
        assert not (res["trades"]["net_pips"] == 0.0).any()
        assert (res["trades"]["exit_reason"] == "CENSORED").all()


# ---------------------------------------------------------------------------
# 14. Once-only costs: net = gross - total_cost exactly once
# ---------------------------------------------------------------------------

class TestOnceOnlyCosts:
    def test_net_is_gross_minus_cost_once(self):
        times = _times("2026-01-12 07:00", 2)
        tape = _mk_tape(times, [[1.1000, 1.1035, 1.0995, 1.1010],
                                [1.1010, 1.1015, 1.1005, 1.1010]])
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False,
                                       cost_scenario="legacy_1pip")
        expected_cost = cost.total_cost_pips("legacy_1pip", fill_type="OHLC_MID")
        assert expected_cost == pytest.approx(1.0)
        assert tr["gross_pips"] == pytest.approx(30.0)
        assert tr["net_pips"] == pytest.approx(tr["gross_pips"] - expected_cost)
        assert tr["net_pips"] == pytest.approx(29.0)
        # and not deducted twice:
        assert tr["net_pips"] == pytest.approx(
            cost.net_pips(tr["gross_pips"], "legacy_1pip"))

    def test_broker_bid_ask_never_double_deducts_spread(self):
        # spread is embedded in broker fills -> no additional spread deduction
        assert cost.total_cost_pips("legacy_1pip",
                                    fill_type="BROKER_BID_ASK") == pytest.approx(0.0)
        assert cost.net_pips(30.0, "legacy_1pip",
                             fill_type="BROKER_BID_ASK") == pytest.approx(30.0)

    def test_unknown_stays_unknown(self):
        assert np.isnan(cost.net_pips(float("nan"), "legacy_1pip"))

    def test_sensitivity_label(self):
        assert cost.total_cost_pips("sensitivity_3pip") == pytest.approx(3.0)
        assert cost.SENSITIVITY_LABEL == "sensitivity — NOT a measured broker cost"


# ---------------------------------------------------------------------------
# 15. Realized vs floating (mark-to-H1-close) accounting
# ---------------------------------------------------------------------------

class TestRealizedVsFloating:
    @pytest.fixture(scope="class")
    def book(self):
        times = _times("2026-01-12 07:00", 4)   # t0..t3
        closes = [1.1000, 1.1000, 1.0800, 1.0900]
        tape = _mk_tape(times, [[c, c + 0.0005, c - 0.0005, c] for c in closes])
        tapes = {"EURUSD": tape}
        trades = pd.DataFrame([
            {"trade_id": 1, "Symbol": "EURUSD", "entry_side": "BUY",
             "entry_price": 1.1000, "entry_at": times[0], "exit_at": times[1],
             "net_pips": 500.0},     # closed +500
            {"trade_id": 2, "Symbol": "EURUSD", "entry_side": "BUY",
             "entry_price": 1.1000, "entry_at": times[1], "exit_at": times[3],
             "net_pips": -50.0},     # still held at t2, floating -200
        ])
        floating = dd.priced_close_floating(trades, tapes)
        return trades, tapes, floating, times

    def test_realized_drawdown_from_closed_only(self, book):
        trades, _, _, _ = book
        r = dd.realized_drawdown(pd.Series([500.0]))   # one closed +500 trade
        assert r["basis"] == "realized closed-trade pips"
        assert r["max_dd_pips"] == pytest.approx(0.0)   # no drawdown
        r2 = dd.realized_drawdown(pd.Series([500.0, -50.0]))
        assert r2["max_dd_pips"] == pytest.approx(-50.0)
        # monotone-profitable equity has NO drawdown (never positive)
        r3 = dd.realized_drawdown(pd.Series([500.0, 100.0]))
        assert r3["max_dd_pips"] == pytest.approx(0.0)
        assert r3["max_dd_pips"] <= 0.0
        s = mh.summarize_trades(trades)
        assert s["net_pips"] == pytest.approx(450.0)

    def test_floating_is_priced_h1_closes_only(self, book):
        trades, _, floating, times = book
        b2 = floating.loc[floating.trade_id == 2].set_index("at")["floating_pips"]
        assert b2[times[1]] == pytest.approx(0.0)
        assert b2[times[2]] == pytest.approx(-200.0)    # (1.0980-1.1000)/pip
        assert b2[times[3]] == pytest.approx(-100.0)

    def test_no_double_counting_after_close(self, book):
        trades, _, floating, times = book
        # trade 1 exited at t1: it contributes no floating rows past its exit
        t1_rows = floating.loc[floating.trade_id == 1, "at"]
        assert (t1_rows <= times[1]).all()
        # combined at t2 is trade 2 alone (-200), not trade 1 + trade 2
        combined = floating.groupby("at")["floating_pips"].sum()
        assert combined[times[2]] == pytest.approx(-200.0)

    def test_mtm_equity_composition(self, book):
        trades, _, floating, _ = book
        summary = dd.floating_summary(floating, trades)
        assert summary["max_combined_floating_loss_pips"] == pytest.approx(-200.0)
        assert summary["max_single_position_floating_loss_pips"] == pytest.approx(-200.0)
        realized_equity = 500.0                            # closed trade
        floating_loss = summary["max_combined_floating_loss_pips"]
        assert realized_equity + floating_loss == pytest.approx(300.0)

    def test_unknown_outcomes_excluded_from_floating(self, book):
        trades, tapes, _, _ = book
        t3 = trades.copy()
        t3.loc[1, "net_pips"] = np.nan                   # outcome unknown
        fl = dd.priced_close_floating(t3, tapes)
        assert set(fl["trade_id"].unique()) == {1}        # no value invented
        s = dd.floating_summary(fl, t3)
        assert s["unknown_unpriced_exposure_trades"] == 1


# ---------------------------------------------------------------------------
# 16. Strict_Valid stays NO; promotion requires fresh-data evidence
# ---------------------------------------------------------------------------

class TestStrictValid:
    def test_all_strict_valid_no(self, registry):
        assert all(e["strict_valid"] == "NO" for e in registry["entries"])

    def test_manifest_never_approves_without_fresh_data(self):
        m = vs.build_validation_manifest(
            strategy_version="monthly-240-v1",
            exit_params_version=reg.EXIT_PARAMS_VERSION,
            test_period="2025-10-01 -> 2026-10-05", sample_trades=3629)
        assert m["status"] == "pending — no fresh data"
        assert m["live_approved"] is False
        assert any("no fresh data" in b for b in m["blockers"])
        assert "FRESH VALIDATION PASSED" not in json.dumps(m)

    def test_classify_never_promotes(self):
        for trades, classification, want in [
                (0, None, "INSUFFICIENT SAMPLE"),
                (12, None, "INSUFFICIENT SAMPLE"),
                (100, None, "RESEARCH ONLY"),
                (100, "REMOVE FROM RESEARCH", "FAILED DIAGNOSTIC"),
                (45, "keep", "RESEARCH ONLY")]:
            got = vs.classify_equation(trades, classification)
            assert got == want
            assert got != "FRESH VALIDATION PASSED"


# ---------------------------------------------------------------------------
# 17. Cache invalidation: key follows inputs; stale results rejected
# ---------------------------------------------------------------------------

def _cache_fp(cost_scenario="legacy_1pip", priority="SL_FIRST", hours=(6, 7, 10, 11, 12, 13)):
    return cache.fingerprint(
        equation_ids=["EQ-1"], engine_version="monthly-240-v1",
        exit_params_version=reg.EXIT_PARAMS_VERSION,
        check_schedule={"hours_utc": list(hours), "minute": 30},
        admission_rules={"k": 4}, filters={},
        cost_model={"scenario": cost_scenario},
        intrabar_priority=priority, holding_policy={"cap_hours": 48},
        censorship_policy="research_release_unknown", source_sha256="abc")


class TestCacheInvalidation:
    def test_key_changes_when_cost_model_changes(self):
        assert _cache_fp("legacy_1pip") != _cache_fp("sensitivity_3pip")

    def test_key_changes_when_priority_or_schedule_changes(self):
        assert _cache_fp(priority="SL_FIRST") != _cache_fp(priority="TP_FIRST")
        assert _cache_fp(hours=(6, 7, 10, 11, 12, 13)) != \
            _cache_fp(hours=(6, 7, 10, 11, 12))

    def test_stale_result_rejected(self):
        stored = cache.wrap({"net_pips": 1.0},
                            input_fingerprint=_cache_fp("legacy_1pip"),
                            config_label="run", data_period="2026")
        with pytest.raises(cache.StaleCacheError):
            cache.check(stored,
                        current_fingerprint=_cache_fp("sensitivity_3pip"))

    def test_describe_carries_config_and_period(self):
        d = cache.describe(config_label="mode-D SL-first",
                           data_period="2022-10-05 -> 2026-10-05")
        assert d["config"] == "mode-D SL-first"
        assert "2022-10-05" in d["data_period"]


# ---------------------------------------------------------------------------
# 18. Display/export consistency: exports match what the replay used
# ---------------------------------------------------------------------------

class TestExportConsistency:
    def _active_config(self):
        return {"cost_model": {"scenario": "legacy_1pip",
                               "deducted_once_pips": 1.0},
                "intrabar_priority": "SL_FIRST",
                "check_schedule": {"hours_utc": [6, 7, 10, 11, 12, 13],
                                   "minute": 30, "timezone": "UTC"},
                "holding_policy": {"cap_hours": 48},
                "exit_params_version": reg.EXIT_PARAMS_VERSION}

    def _fp_of(self, cfg):
        return cache.fingerprint(
            equation_ids=["EQ-1"], engine_version="monthly-240-v1",
            exit_params_version=cfg["exit_params_version"],
            check_schedule=cfg["check_schedule"],
            admission_rules={"k": 4}, filters={},
            cost_model=cfg["cost_model"],
            intrabar_priority=cfg["intrabar_priority"],
            holding_policy=cfg["holding_policy"],
            censorship_policy="research_release_unknown",
            source_sha256="abc")

    def test_export_roundtrip_preserves_cache_key(self):
        active = self._active_config()
        key_before = self._fp_of(active)
        name, payload, mime = exports.active_config_json(active)
        assert name.endswith(".json") and mime == "application/json"
        reloaded = json.loads(payload.decode())
        # the exported config says what the replay actually used
        assert reloaded["cost_model"]["scenario"] == "legacy_1pip"
        assert reloaded["intrabar_priority"] == "SL_FIRST"
        assert reloaded["check_schedule"]["hours_utc"] == [6, 7, 10, 11, 12, 13]
        assert reloaded["holding_policy"]["cap_hours"] == 48
        assert self._fp_of(reloaded) == key_before

    def test_replay_used_values_match_export(self):
        """The ledger rows carry the same cost model / priority the exported
        config declares."""
        times = _times("2026-01-12 07:00", 2)
        tape = _mk_tape(times, [[1.1000, 1.1035, 1.0995, 1.1010],
                                [1.1010, 1.1015, 1.1005, 1.1010]])
        sig = _mk_signal("2026-01-12 06:30")
        tr = replay.replay_trade_fixed(sig, tape, tp_pips=30, sl_pips=10,
                                       hold_hours=48, danger_enabled=False,
                                       priority="SL_FIRST",
                                       cost_scenario="legacy_1pip")
        active = self._active_config()
        assert tr["intrabar_priority"] == active["intrabar_priority"]
        assert tr["cost_scenario"] == active["cost_model"]["scenario"]

    def test_registry_csv_has_240_rows(self, registry):
        name, payload, mime = exports.registry_csv(registry)
        assert name.endswith(".csv") and mime == "text/csv"
        rows = list(csv.DictReader(payload.decode().splitlines()))
        assert len(rows) == 240
        assert {r["S Column"] for r in rows} == {f"S{i}" for i in range(1, 241)}
        assert all(r["Strict Valid"] == "NO" for r in rows)

    def test_glossary_documents_both_priorities(self):
        _, text, _ = exports.exit_reason_glossary()
        assert "SL_FIRST (default)" in text
        assert "TP_FIRST (legacy comparison)" in text
        assert "UNRESOLVED_UNKNOWN" in text
