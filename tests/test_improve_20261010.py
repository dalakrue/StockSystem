"""Section-21 verification for the 2026-10-10 pooled-exits improvement.

TEST-ONLY pytz shim (Asia/Rangoon -> Asia/Yangon, identical UTC+6:30) lives in
this module only. No app file is modified for the sandbox.

Covers the command's section 21:
  * causal prefix invariance (single-trade and portfolio level)
  * deterministic synthetic paths: BUY/SELL, JPY pip conversion, TP-only,
    SL-only, both-hit ambiguity, stop-gap slippage, 48h cap, previous-bar
    bias/danger exits, Friday barrier-before-close, missing-path censoring
  * real-trade reconciliation vs the authoritative __9 replay engine
    (core.replay_fixed_20261009) on sampled trades
  * same TP/SL config across all runtime paths; cache invalidation
  * ranking ties; 4-per-check capacity; held-symbol exclusion
  * S1-S240 mapping (all 240 rows exported, incl. disabled + 27 rebuilt rows)
  * ledger <-> comparison reconciliation; drawdown recompute
  * clean-launch smoke (imports OK, page compiles, configs valid)
"""
import json
import os
import sys

import pytest

# --- test-only pytz shim (module scope; app files untouched) ----------------
import pytz as _pytz
_orig_tz = _pytz.timezone


def _tz(name):
    if name == "Asia/Rangoon":
        name = "Asia/Yangon"
    return _orig_tz(name)


_pytz.timezone = _tz

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)
WORK = "/home/hatch/workspace/fx_improve/work"
DELIV = os.path.join(WORK, "deliverables")
DATA = "/home/hatch/workspace/fx/cvnew/cvnew/raw_ohlc_all_symbols_H1_4_years.csv"

import numpy as np
import pandas as pd

from core import exit_engine_20261010 as E
from core.monthly_runtime import ENGINE_VERSION as MONTHLY_ENGINE_VERSION


# ------------------------------------------------------------- helpers ------
def synth_tape(n, *, start="2024-01-02 06:00", pip=0.0001, seed=7, drift=0.0):
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, 0.0008, n)
    C = 1.1000 * np.exp(np.cumsum(rets))
    O = np.r_[C[0], C[:-1]]
    H = np.maximum(O, C) + np.abs(rng.normal(0, 0.0003, n))
    L = np.minimum(O, C) - np.abs(rng.normal(0, 0.0003, n))
    times = pd.date_range(start, periods=n, freq="h", tz="UTC")
    return dict(times=times, lookup={t: i for i, t in enumerate(times)},
                prices=np.c_[O, H, L, C], pip=pip,
                friday=np.zeros(n, bool), exit_known=np.ones(n, bool),
                exit_bias=np.zeros(n), exit_atr=np.full(n, 0.0012),
                exit_range=H - L, exit_body=C - O, bias=np.zeros(n),
                atr=np.full(n, 0.0012), availability=times)


def synth_signal(tape, i_entry, *, symbol="EURUSD", direction="BUY",
                 eq="EURUSD-01-X", scol="S1", danger=False):
    entry_at = tape["times"][i_entry]
    return {"Datetime": entry_at,
            "check_at": entry_at - pd.Timedelta(minutes=30),
            "Symbol": symbol, "Direction": direction,
            "Equation ID": eq, "Active S Column": scol,
            "Danger Enabled": danger,
            "signal_bar_open": entry_at - pd.Timedelta(hours=2),
            "Suggested TP Pips": 30.0, "Suggested SL Pips": 50.0}


def fixed_exits(tp=30.0, sl=50.0):
    return {"tp_pips": tp, "sl_pips": sl, "basis": "FIXED_PIPS",
            "atr_pips": np.nan, "atr_bar_time": None, "gate_rr": 0.5}


# ------------------------------------------------------------- entry gate ---
class TestEntryGate:
    def test_fixed_pairs_pass(self):
        assert E.entry_gate(30, 50)[0]      # EURJPY/EURNZD: 27/53 = 0.509
        assert E.entry_gate(50, 20)[0]      # USDJPY
        assert E.resolve_pooled_exits("EURJPY", np.nan, None)["tp_pips"] == 30.0
        assert E.resolve_pooled_exits("USDJPY", np.nan, None)["sl_pips"] == 20.0

    def test_boundary_passes(self):
        ok, rr, reason = E.entry_gate(4.5, 3.0)   # (4.5-3)/(3+3) = 0.25/… no
        # exact boundary: (TP-3) = 0.5*(SL+3) -> TP = 0.5*SL + 4.5
        ok, rr, reason = E.entry_gate(0.5 * 10 + 4.5, 10.0)
        assert ok and reason == "PASS" and abs(rr - 0.5) < 1e-12

    def test_reject_pair_not_in_scenario(self):
        r = E.resolve_pooled_exits("AUDUSD", np.nan, None)
        assert r == {"rejected": "REJECT_PAIR_NOT_IN_SCENARIO"}

    def test_gbpy_atr_clips(self):
        r = E.resolve_pooled_exits("GBPJPY", 200.0, None)   # 3*200=600 -> 500
        assert r["tp_pips"] == 500.0 and r["sl_pips"] == 100.0
        r = E.resolve_pooled_exits("GBPJPY", 1.0, None)     # 3,2 -> clip 10
        assert r["tp_pips"] == 10.0 and r["sl_pips"] == 10.0
        r = E.resolve_pooled_exits("GBPJPY", 12.0, None)    # 36 / 24, no clip
        assert r["tp_pips"] == 36.0 and r["sl_pips"] == 24.0
        assert r["basis"] == "ATR14_MULTIPLIER"

    def test_gbpy_gate_property(self):
        # With the doc's clips, the 3-pip gate passes for every ATR on a grid:
        # tiny ATR clips to 10/10 -> (10-3)/(10+3) = 0.538 >= 0.5, and the
        # ratio only grows with ATR. Documented here as a property, not a bug.
        for a in (0.5, 1.0, 2.25, 12.0, 45.0, 60.0, 200.0):
            r = E.resolve_pooled_exits("GBPJPY", a, None)
            assert "rejected" not in r, (a, r)
        # The gate itself still rejects bad risk/reward (unit check):
        ok, rr, reason = E.entry_gate(5.0, 100.0)
        assert not ok and reason == "REJECT_REWARD_RISK"

    def test_atr_rejections(self):
        assert E.resolve_pooled_exits("GBPJPY", np.nan, None) == {"rejected": "REJECT_ATR_MISSING"}
        assert E.resolve_pooled_exits("GBPJPY", None, None) == {"rejected": "REJECT_ATR_MISSING"}
        assert E.resolve_pooled_exits("GBPJPY", 0.0, None) == {"rejected": "REJECT_ATR_NONPOSITIVE"}
        assert E.resolve_pooled_exits("GBPJPY", -2.0, None) == {"rejected": "REJECT_ATR_NONPOSITIVE"}

    def test_invalid_inputs(self):
        ok, rr, reason = E.entry_gate(np.nan, 50.0)
        assert not ok and reason == "REJECT_INVALID_TP_SL"
        ok, rr, reason = E.entry_gate(30.0, 0.0)
        assert not ok and reason == "REJECT_INVALID_TP_SL"


# ------------------------------------------------------------- synthetic ----
class TestSyntheticPaths:
    def _quiet(self, n=12):
        O = np.linspace(1.1000, 1.1005, n)
        H = O + 0.0004
        L = O - 0.0004
        C = O + 0.0001
        t = synth_tape(n)
        t["prices"] = np.c_[O, H, L, C]
        t["exit_range"] = H - L
        t["exit_body"] = C - O
        return t

    def test_tp_only_buy(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        H[4] = 1.1045  # touches TP 1.1035 (entry 1.1005 + 30p)
        t["prices"] = np.c_[O, H, L, C]
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "TP"
        assert tr["gross_pips"] == pytest.approx(30.0)
        assert tr["net_pips"] == pytest.approx(29.0)          # cost deducted once
        assert tr["net_pips_sl_first"] == tr["net_pips_tp_first"] == pytest.approx(29.0)
        assert not tr["ambiguous"] and tr["outcome_state"] == "CLOSED_KNOWN"
        assert tr["initial_stop_R"] == pytest.approx(29.0 / 50.0)
        assert tr["cost_inclusive_R"] == pytest.approx(29.0 / 51.0)

    def test_sl_only_sell(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        H[5] = 1.1060  # SELL stop = 1.1005+50p = 1.1055
        t["prices"] = np.c_[O, H, L, C]
        sig = synth_signal(t, 1, direction="SELL")
        tr = E.replay_trade_engine(sig, t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "SL"
        assert tr["net_pips"] == pytest.approx(-51.0)
        assert tr["entry_side"] == "SELL"

    def test_jpy_pip_conversion(self):
        t = synth_tape(8, pip=0.01)
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        O[:] = 150.0
        H[:] = 150.05
        L[:] = 149.95
        C[:] = 150.01
        H[3] = 150.70  # TP = 150.10 + 50p*0.01 = 150.60
        t["prices"] = np.c_[O, H, L, C]
        sig = synth_signal(t, 1, symbol="USDJPY")
        ex = {"tp_pips": 50.0, "sl_pips": 20.0, "basis": "FIXED_PIPS",
              "atr_pips": np.nan, "atr_bar_time": None, "gate_rr": 2.0}
        tr = E.replay_trade_engine(sig, t, exits=ex, priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "TP"
        assert tr["tp_price"] == pytest.approx(150.50)   # 150.00 + 50*0.01
        assert tr["sl_price"] == pytest.approx(149.80)   # 150.00 - 20*0.01
        assert tr["net_pips"] == pytest.approx(49.0)

    def test_both_hit_ambiguity(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        H[4] = 1.1045
        L[4] = 1.0950  # same bar touches TP (1.1035) and SL (1.0955)
        t["prices"] = np.c_[O, H, L, C]
        tr_s = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                     priority="SL_FIRST", cost_pips=1.0)
        tr_t = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                     priority="TP_FIRST", cost_pips=1.0)
        assert tr_s["ambiguous"] and tr_t["ambiguous"]
        assert tr_s["exit_reason"] == "SL" and tr_t["exit_reason"] == "TP"
        assert tr_s["net_pips_sl_first"] == pytest.approx(-51.0)
        assert tr_s["net_pips_tp_first"] == pytest.approx(29.0)
        assert tr_s["net_pips"] == pytest.approx(-51.0)   # run priority wins
        assert tr_t["net_pips"] == pytest.approx(29.0)

    def test_stop_gap_slippage(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        O[3] = 1.0940  # adverse gap through the stop
        t["prices"] = np.c_[O, H, L, C]
        entry_px = O[1]
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "SL"
        assert tr["exit_price"] == pytest.approx(1.0940)  # observed open, never fabricated
        assert tr["stop_gap"]
        assert tr["net_pips"] == pytest.approx((1.0940 - entry_px) / 0.0001 - 1.0)

    def test_favourable_gap_capped_at_target(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        O[3] = 1.1060  # gaps over the target
        t["prices"] = np.c_[O, H, L, C]
        entry_px = O[1]
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "TP"
        assert tr["exit_price"] == pytest.approx(entry_px + 30 * 0.0001)  # capped at target
        assert not tr["stop_gap"]

    def test_hold_cap_48h(self):
        t = self._quiet(60)
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "HOLD_CAP"
        assert tr["hold_hours"] == pytest.approx(48.0)

    def test_bias_flip_previous_bar(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        t["prices"] = np.c_[O, H, L, C]
        t["exit_bias"][4] = -1.0  # completed-bar bias flips against BUY
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "BIAS_FLIP"
        assert tr["exit_at"] == t["times"][4]

    def test_danger_exit(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        O[5] = 1.1005
        H[5] = 1.1030
        L[5] = 1.0975
        C[5] = 1.0980  # range .0055 > 3*atr(.0036); body -.0025 < -.0006
        t["prices"] = np.c_[O, H, L, C]
        t["exit_range"] = H - L
        t["exit_body"] = C - O
        sig = synth_signal(t, 1, danger=True)
        tr = E.replay_trade_engine(sig, t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "DANGER"

    def test_friday_barrier_before_close(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        t["friday"][6] = True
        L[6] = 1.0950  # SL touched inside the Friday bar
        t["prices"] = np.c_[O, H, L, C]
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "SL"          # barrier wins over Friday close
        assert tr["exit_price"] == pytest.approx(O[1] - 50 * 0.0001)

    def test_friday_close_no_touch(self):
        t = self._quiet()
        O, H, L, C = (t["prices"][:, k].copy() for k in range(4))
        t["friday"][6] = True
        t["prices"] = np.c_[O, H, L, C]
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["exit_reason"] == "FRIDAY_CLOSE"
        assert tr["exit_at"] == t["times"][6] + pd.Timedelta(hours=1)
        assert tr["exit_price"] == pytest.approx(C[6])

    def test_missing_path_censored_never_zero(self):
        t = self._quiet(2)  # tape ends right after the entry bar
        tr = E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                   priority="SL_FIRST", cost_pips=1.0)
        assert tr["outcome_state"] == "UNRESOLVED_UNKNOWN"
        assert tr["censored"]
        assert np.isnan(tr["net_pips"]) and np.isnan(tr["net_pips_sl_first"])
        assert np.isnan(tr["gross_pips"])

    def test_bad_priority_raises(self):
        t = self._quiet()
        with pytest.raises(ValueError):
            E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                  priority="BOGUS")

    def test_bad_cost_raises(self):
        t = self._quiet()
        with pytest.raises(ValueError):
            E.replay_trade_engine(synth_signal(t, 1), t, exits=fixed_exits(),
                                  cost_pips=2.5)


# ------------------------------------------------------------- causality ---
class TestCausalPrefixInvariance:
    def _raw(self, n_days=30, seed=11):
        rng = np.random.default_rng(seed)
        out = []
        for sym, base in (("EURUSD", 1.10), ("GBPJPY", 190.0)):
            n = n_days * 24
            rets = rng.normal(0, 0.0006, n)
            C = base * np.exp(np.cumsum(rets))
            O = np.r_[C[0], C[:-1]]
            H = np.maximum(O, C) + 0.0002 * base / 1.1
            L = np.minimum(O, C) - 0.0002 * base / 1.1
            times = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
            out.append(pd.DataFrame({"Datetime": times, "Symbol": sym,
                                     "Open": O, "High": H, "Low": L, "Close": C}))
        return pd.concat(out, ignore_index=True)

    def _signals(self, raw, checks):
        rows = []
        for i, (ck, sym) in enumerate(checks):
            rows.append({
                "Datetime": ck + pd.Timedelta(minutes=30), "check_at": ck,
                "Symbol": sym, "Direction": "BUY",
                "Equation ID": f"{sym}-01-X", "Active S Column": "S1",
                "Strategy Hit Count": 1,
                "Strategy Engine": MONTHLY_ENGINE_VERSION,
                "Danger Enabled": False, "Improved Rank": 100.0 - i,
                "signal_bar_open": ck - pd.Timedelta(hours=2),
                "Suggested TP Pips": 30.0, "Suggested SL Pips": 50.0,
                "ranking_score": 1.0,
            })
        return pd.DataFrame(rows)

    def test_single_trade_future_bars_irrelevant(self):
        t = synth_tape(40)
        sig = synth_signal(t, 1)
        a = E.replay_trade_engine(sig, t, exits=fixed_exits(), priority="SL_FIRST")
        # extend the tape with 160 unrelated future bars (different seed)
        t2 = synth_tape(200, seed=99)
        t2["prices"][:40] = t["prices"]
        t2["friday"][:40] = t["friday"]
        b = E.replay_trade_engine(sig, t2, exits=fixed_exits(), priority="SL_FIRST")
        assert a["exit_reason"] == b["exit_reason"]
        assert a["exit_at"] == b["exit_at"]
        assert (np.isnan(a["net_pips"]) and np.isnan(b["net_pips"])) or \
            a["net_pips"] == pytest.approx(b["net_pips"])

    def test_portfolio_prefix_invariance(self):
        from core.monthly_runtime import raw_frame
        raw_full = raw_frame(self._raw(30))
        raw_trunc = raw_full.loc[raw_full["Datetime"] < pd.Timestamp("2024-01-21")].copy()
        checks = [(pd.Timestamp("2024-01-05 06:30", tz="UTC"), "EURUSD"),
                  (pd.Timestamp("2024-01-05 07:30", tz="UTC"), "GBPJPY"),
                  (pd.Timestamp("2024-01-06 10:30", tz="UTC"), "EURUSD"),
                  (pd.Timestamp("2024-01-10 12:30", tz="UTC"), "GBPJPY")]
        sig = self._signals(raw_full, checks)
        r_full = E.run_portfolio(raw_full, signals=sig, scenario=E.SCENARIO_POOLED,
                                 cost_pips=1.0, priority="SL_FIRST")
        r_tr = E.run_portfolio(raw_trunc, signals=sig, scenario=E.SCENARIO_POOLED,
                               cost_pips=1.0, priority="SL_FIRST")
        cut = pd.Timestamp("2024-01-21", tz="UTC")
        d_full = r_full["checks"].loc[pd.to_datetime(r_full["checks"]["check_at"], utc=True) < cut]
        d_tr = r_tr["checks"]
        pd.testing.assert_frame_equal(
            d_full.reset_index(drop=True).astype(str),
            d_tr.reset_index(drop=True).astype(str))
        t_full = r_full["trades"]
        t_tr = r_tr["trades"]
        assert len(t_full) == len(t_tr)
        for c in ("Symbol", "exit_reason", "outcome_state"):
            assert (t_full[c].astype(str) == t_tr[c].astype(str)).all()
        assert np.allclose(t_full["net_pips_sl_first"].fillna(0),
                           t_tr["net_pips_sl_first"].fillna(0))


# ------------------------------------------------------------- config -------
class TestConfigConsistency:
    def test_config_hash_stable(self):
        assert E.config_hash() == E.config_hash()
        assert len(E.config_hash()) == 64

    def test_cache_invalidation(self):
        base = dict(scenario=E.SCENARIO_POOLED, cost_pips=1.0,
                    priority="SL_FIRST", data_sha256="abc",
                    entry_start="2022-10-05", entry_end="2026-10-05")
        k = E.cache_key(**base)
        E.assert_cache_fresh(k, **base)
        for kw in ({"cost_pips": 3.0}, {"priority": "TP_FIRST"},
                   {"data_sha256": "abd"}, {"scenario": E.SCENARIO_BASELINE},
                   {"entry_end": "2026-10-04"}):
            with pytest.raises(E.StaleCacheError):
                E.assert_cache_fresh(k, **{**base, **kw})

    def test_ledger_carries_config_hash(self):
        p = os.path.join(DELIV, "trade_ledger_pooled_exits_research_cost1pip_20261010.csv")
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        l = pd.read_csv(p, usecols=["config_hash"])
        assert (l["config_hash"] == E.config_hash()).all()


# ------------------------------------------------------------- admission ----
class TestAdmission:
    def _raw(self):
        rng = np.random.default_rng(5)
        n = 24 * 10
        C = 1.10 * np.exp(np.cumsum(rng.normal(0, 0.0006, n)))
        O = np.r_[C[0], C[:-1]]
        times = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        return pd.DataFrame({"Datetime": times, "Symbol": "EURUSD", "Open": O,
                             "High": np.maximum(O, C) + 0.0002,
                             "Low": np.minimum(O, C) - 0.0002, "Close": C})

    def _sigs(self, rows):
        out = []
        for i, (ck, sym, rank) in enumerate(rows):
            out.append({"Datetime": ck + pd.Timedelta(minutes=30), "check_at": ck,
                        "Symbol": sym, "Direction": "BUY",
                        "Equation ID": f"{sym}-01-X", "Active S Column": "S1",
                        "Strategy Hit Count": 1,
                        "Strategy Engine": MONTHLY_ENGINE_VERSION,
                        "Danger Enabled": False, "Improved Rank": rank,
                        "signal_bar_open": ck - pd.Timedelta(hours=2),
                        "Suggested TP Pips": 30.0, "Suggested SL Pips": 50.0})
        return pd.DataFrame(out)

    def test_ranking_ties_deterministic(self):
        from core.monthly_runtime import raw_frame
        base = self._raw()
        g2 = base.copy()
        g2["Symbol"] = "EURNZD"
        raw = raw_frame(pd.concat([base, g2], ignore_index=True))
        ck = pd.Timestamp("2024-01-03 06:30", tz="UTC")
        # same rank, different symbols -> Symbol ascending wins deterministically
        both = self._sigs([(ck, "EURUSD", 50.0), (ck, "EURNZD", 50.0)])
        r = E.run_portfolio(raw, signals=both, scenario=E.SCENARIO_BASELINE,
                            cost_pips=1.0)
        r2 = E.run_portfolio(raw, signals=both.iloc[::-1].reset_index(drop=True),
                             scenario=E.SCENARIO_BASELINE, cost_pips=1.0)
        assert r["checks"]["selected"].tolist() == r2["checks"]["selected"].tolist()
        assert r["checks"]["selected"].tolist() != []

    def test_four_per_check_capacity(self):
        from core.monthly_runtime import raw_frame
        base = self._raw()
        raws = []
        syms = ["EURJPY", "EURNZD", "USDJPY", "GBPJPY", "EURUSD"]
        for s in syms:
            g = base.copy()
            g["Symbol"] = s
            raws.append(g)
        raw = raw_frame(pd.concat(raws, ignore_index=True))
        ck = pd.Timestamp("2024-01-03 06:30", tz="UTC")
        # EURUSD ranked first so its rejection is recorded before capacity fills
        sig = self._sigs([(ck, "EURUSD", 101.0)] +
                         [(ck, s, 100.0 - i) for i, s in
                          enumerate(["EURJPY", "EURNZD", "USDJPY", "GBPJPY"])])
        r = E.run_portfolio(raw, signals=sig, scenario=E.SCENARIO_POOLED, cost_pips=1.0)
        chk = r["checks"].loc[pd.to_datetime(r["checks"]["check_at"], utc=True) == ck].iloc[0]
        sel = [s for s in chk["selected"].split(",") if s]
        assert len(sel) == 4
        assert set(sel) == {"EURJPY", "EURNZD", "USDJPY", "GBPJPY"}
        # EURUSD rejected (pair not in scenario) -> reason recorded
        assert "REJECT_PAIR_NOT_IN_SCENARIO" in chk["exit_rejections"]

    def test_held_symbol_exclusion(self):
        from core.monthly_runtime import raw_frame
        raw = raw_frame(self._raw())
        ck1 = pd.Timestamp("2024-01-03 06:30", tz="UTC")
        ck2 = pd.Timestamp("2024-01-03 07:30", tz="UTC")
        sig = self._sigs([(ck1, "EURUSD", 90.0), (ck2, "EURUSD", 90.0)])
        r = E.run_portfolio(raw, signals=sig, scenario=E.SCENARIO_BASELINE,
                            cost_pips=1.0)
        # first check admits EURUSD (quiet market: no barrier touch -> held 48h)
        c1 = r["checks"].loc[pd.to_datetime(r["checks"]["check_at"], utc=True) == ck1].iloc[0]
        c2 = r["checks"].loc[pd.to_datetime(r["checks"]["check_at"], utc=True) == ck2].iloc[0]
        first = c1["selected"]
        if "EURUSD" in first.split(","):
            assert "EURUSD" not in c2["selected"].split(",")
            assert c2["reason"] in ("TOP_FOUR_HELD", "ENTRY", "NO_TRIGGER",
                                    "MAX_20_HOLDINGS")


# ------------------------------------------------------------- reconciliation
LEDGERS_1P = {
    "baseline": os.path.join(DELIV, "trade_ledger_baseline_current_exits_cost1pip_20261010.csv"),
    "pooled": os.path.join(DELIV, "trade_ledger_pooled_exits_research_cost1pip_20261010.csv"),
}


class TestRealTradeReconciliation:
    """Sampled real trades vs the authoritative __9 engine (frozen).

    The only deliberate behavioural difference is the section-5 eval order:
    this engine evaluates intrabar BARRIERS before the FRIDAY_CLOSE; the __9
    engine evaluated Friday close first. Differing sampled trades must be
    Friday-involved only.
    """

    def _sample(self, scenario, n=60, seed=4242):
        p = LEDGERS_1P[scenario]
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        l = pd.read_csv(p)
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(l), size=min(n, len(l)), replace=False)
        return l.iloc[idx]

    @pytest.mark.parametrize("scenario", ["baseline", "pooled"])
    def test_sampled_trades_match_authoritative_engine(self, scenario):
        from core import replay_fixed_20261009 as F9
        from core.monthly_runtime import raw_frame
        from core.monthly_backtest import make_tapes
        sample = self._sample(scenario)
        raw = pd.read_csv(DATA, usecols=["Datetime", "Symbol", "Open", "High", "Low", "Close"])
        syms = sample["Symbol"].unique().tolist()
        raw = raw.loc[raw["Symbol"].isin(syms)].copy()
        raw["Datetime"] = pd.to_datetime(raw["Datetime"], utc=True)
        tapes = make_tapes(raw_frame(raw))
        scen = E.SCENARIO_BASELINE if scenario == "baseline" else E.SCENARIO_POOLED
        identical, friday_diverge, other = 0, 0, []
        for _, row in sample.iterrows():
            tape = tapes[row["Symbol"]]
            sig = {"Datetime": pd.to_datetime(row["entry_at"], utc=True),
                   "check_at": pd.to_datetime(row["check_at"], utc=True),
                   "Symbol": row["Symbol"],
                   "Direction": row["entry_side"],
                   "Equation ID": row["Equation ID"],
                   "Active S Column": row["Active S Column"],
                   "Danger Enabled": bool(row["danger"])}
            ref = F9.replay_trade_fixed(
                sig, tape, tp_pips=float(row["tp_pips"]), sl_pips=float(row["sl_pips"]),
                hold_hours=48, danger_enabled=bool(row["danger"]),
                priority="SL_FIRST", cost_scenario="legacy_1pip",
                exit_mode="reconciliation")
            mine_exit = pd.to_datetime(row["exit_at"], utc=True)
            ref_exit = pd.to_datetime(ref["exit_at"], utc=True)
            same = (ref["exit_reason"] == row["exit_reason"]
                    and ref_exit == mine_exit
                    and abs(ref["exit_price"] - row["exit_price"]) < 1e-9
                    and abs(ref["gross_pips"] - row["gross_pips_sl_first"]) < 1e-9
                    and abs(ref["net_pips"] - row["net_pips_sl_first"]) < 1e-9)
            if same:
                identical += 1
            elif "FRIDAY" in str(ref["exit_reason"]) or "FRIDAY" in str(row["exit_reason"]):
                friday_diverge += 1  # documented eval-order difference
            else:
                other.append((row["trade_id"], ref["exit_reason"], row["exit_reason"]))
        assert not other, f"non-Friday divergences vs __9 engine: {other[:10]}"
        assert identical + friday_diverge == len(sample)
        print(f"\n[{scenario}] identical={identical} friday-order-diverge={friday_diverge} "
              f"of {len(sample)} sampled")


# ------------------------------------------------------------- mapping ------
class TestS240Mapping:
    def _status(self):
        p = os.path.join(DELIV, "strategy_status_240_20261010.csv")
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        return pd.read_csv(p)

    def test_all_240_exported(self):
        s = self._status()
        s_rows = s.loc[s["s_column"].str.startswith("S")]
        assert len(s_rows) == 240
        assert sorted(int(x[1:]) for x in s_rows["s_column"]) == list(range(1, 241))
        assert s_rows["symbol"].nunique() == 20
        assert sorted(s_rows["myanmar_month"].unique().tolist()) == list(range(1, 13))

    def test_disabled_rows_present(self):
        s = self._status()
        assert (s["s_column"].str.startswith("RB")).sum() == 27
        rb = s.loc[s["s_column"].str.startswith("RB")]
        assert (rb["status"] == "REJECTED").all()

    def test_statuses_valid_and_live_never_approved(self):
        s = self._status()
        allowed = {"REJECTED", "INSUFFICIENT_SAMPLE", "DEVELOPMENT_CANDIDATE",
                   "PAPER_PENDING", "FRESH_VALIDATED"}
        assert set(s["status"].unique()) <= allowed
        assert not s["live_approved"].any()
        assert not s["fresh_evaluation_passed"].any()
        flags = ["data_quality_passed", "causal_replay_passed",
                 "development_screen_passed", "fresh_evaluation_passed",
                 "execution_model_verified", "paper_forward_passed", "live_approved"]
        for f in flags:
            assert f in s.columns

    def test_pooled_gets_48_development_candidates(self):
        s = self._status()
        dev = s.loc[s["status"] == "DEVELOPMENT_CANDIDATE"]
        assert len(dev) == 48
        assert set(dev["symbol"].unique()) == {"EURJPY", "EURNZD", "GBPJPY", "USDJPY"}
        assert (dev["development_screen_passed"]).all()
        assert not dev["live_approved"].any()


# ------------------------------------------------------------- reconcile ----
class TestLedgerReconciliation:
    @pytest.mark.parametrize("scenario", ["baseline", "pooled"])
    @pytest.mark.parametrize("cost", [1.0, 3.0, 5.0])
    def test_comparison_reconciles_to_ledger(self, scenario, cost):
        scen = "baseline_current_exits" if scenario == "baseline" else "pooled_exits_research"
        p = os.path.join(DELIV, f"trade_ledger_{scen}_cost{cost:g}pip_20261010.csv")
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        l = pd.read_csv(p)
        comp = pd.read_csv(os.path.join(DELIV, "comparison_before_after_20261010.csv"))
        for window in ("full_4y", "reused_year"):
            lw = l
            if window == "reused_year":
                m = (l["entry_at"] >= "2025-10-05") & (l["entry_at"] < "2026-10-05")
                lw = l.loc[m]
            row = comp.loc[(comp["scenario"] == scen) & (comp["cost_pips"] == cost)
                           & (comp["window"] == window)].iloc[0]
            closed = lw.loc[~lw["censored"].fillna(False).astype(bool)]
            assert row["attempts"] == len(lw)
            assert row["closed_trades"] == len(closed)
            assert row["unknown_outcomes"] == int(lw["censored"].fillna(False).astype(bool).sum())
            assert row["net_pips_sl_first"] == pytest.approx(closed["net_pips_sl_first"].sum(), abs=0.05)
            assert row["net_pips_tp_first"] == pytest.approx(closed["net_pips_tp_first"].sum(), abs=0.05)
            assert row["ambiguous_trades"] == int(closed["ambiguous"].fillna(False).astype(bool).sum())

    def test_cost_derivation_exact(self):
        b1 = os.path.join(DELIV, "trade_ledger_baseline_current_exits_cost1pip_20261010.csv")
        b3 = os.path.join(DELIV, "trade_ledger_baseline_current_exits_cost3pip_20261010.csv")
        if not (os.path.exists(b1) and os.path.exists(b3)):
            pytest.skip("portfolio run not finished yet")
        l1 = pd.read_csv(b1)
        l3 = pd.read_csv(b3)
        for v in ("sl_first", "tp_first"):
            g = l1[f"gross_pips_{v}"].to_numpy()
            n = l3[f"net_pips_{v}"].to_numpy()
            ok = (np.isnan(g) & np.isnan(n)) | (np.abs(g - 3.0 - n) < 1e-9)
            assert ok.all()

    def test_drawdown_recompute(self):
        p = os.path.join(DELIV, "trade_ledger_pooled_exits_research_cost1pip_20261010.csv")
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        l = pd.read_csv(p)
        closed = l.loc[~l["censored"].fillna(False).astype(bool)].copy()
        closed = closed.sort_values("exit_at", kind="mergesort")
        agg = closed.groupby("exit_at", sort=True)["net_pips_sl_first"].sum()
        eq = agg.cumsum().to_numpy()
        peak = np.maximum.accumulate(np.r_[0.0, eq])[1:]
        dd = float(np.minimum.accumulate(eq - peak).min())
        comp = pd.read_csv(os.path.join(DELIV, "comparison_before_after_20261010.csv"))
        row = comp.loc[(comp["scenario"] == "pooled_exits_research")
                       & (comp["cost_pips"] == 1.0) & (comp["window"] == "full_4y")].iloc[0]
        assert row["realized_drawdown_pips"] == pytest.approx(dd, abs=0.01)

    def test_r_definitions_labelled(self):
        p = os.path.join(DELIV, "trade_ledger_pooled_exits_research_cost3pip_20261010.csv")
        if not os.path.exists(p):
            pytest.skip("portfolio run not finished yet")
        l = pd.read_csv(p)
        closed = l.loc[~l["censored"].fillna(False).astype(bool)]
        r = closed["initial_stop_R"].to_numpy()
        rc = closed["cost_inclusive_R"].to_numpy()
        n = closed["net_pips_sl_first"].to_numpy()
        sl = closed["sl_pips"].to_numpy()
        assert np.allclose(r, n / sl, equal_nan=True)
        assert np.allclose(rc, n / (sl + 3.0), equal_nan=True)
        assert not np.allclose(r, rc, equal_nan=True)  # the two definitions differ


# ------------------------------------------------------------- smoke --------
class TestSmoke:
    def test_new_modules_import(self):
        import core.exit_engine_20261010  # noqa: F401
        from core import exit_engine_20261010 as eng  # noqa: F401
        assert eng.ENGINE_VERSION_EXIT == "exit-engine-20261010-v1"

    def test_page_compiles(self):
        import py_compile
        py_compile.compile(os.path.join(APP, "pages", "pooled_research_20261010.py"),
                           doraise=True)

    def test_configs_valid(self):
        cfg = json.load(open(os.path.join(APP, "config", "research_improve_20261010.json")))
        assert cfg["scenarios"]["pooled_exits_research"]["live_enabled"] is False
        assert cfg["scenarios"]["pooled_exits_research"]["exits"]["GBPJPY"]["tp_mult"] == 3.0
        bundle = json.load(open(os.path.join(APP, "data", "pooled_scenario_20261010.json")))
        assert bundle["live_enabled"] is False
        assert len(bundle["s_mapping"]) == 240
        assert len(bundle["rebuilt_family_disabled"]) == 27
        assert bundle["config_hash"] == E.config_hash()
