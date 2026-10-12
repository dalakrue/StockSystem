"""Split raw OHLC ranges (2026-10-07): 2020-01-01 -> Latest and 2015-01-01 -> 2020-01-01.

Covers: new job kinds are recognized as raw-only, make_job produces the
explicit calendar bounds per range, legacy 10-year behavior is unchanged,
the two ranges can never dedupe against each other, and download
labels/filenames are range-aware.
"""
import pandas as pd

import core.resumable_build_20260928 as builds
from ui.build_artifact_controls_20261002 import raw_download_label


def test_new_kinds_are_raw_ohlc():
    assert builds.is_raw_ohlc_kind(builds.RAW_OHLC_KIND_2020_LATEST)
    assert builds.is_raw_ohlc_kind(builds.RAW_OHLC_KIND_2015_2020)
    # legacy kinds keep working
    assert builds.is_raw_ohlc_kind(builds.RAW_OHLC_KIND)
    assert builds.is_raw_ohlc_kind(builds.RAW_OHLC_KIND_LEGACY)
    assert not builds.is_raw_ohlc_kind(builds.KIND)


def test_range_kinds_are_distinct():
    kinds = {spec["kind"] for spec in builds.RAW_OHLC_RANGES_20261007.values()}
    assert kinds == {builds.RAW_OHLC_KIND_2020_LATEST, builds.RAW_OHLC_KIND_2015_2020}
    assert builds.RAW_OHLC_KIND not in kinds  # no dedup collision with legacy 10Y


def test_make_job_2020_latest_bounds():
    job = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2020_LATEST")
    assert job["kind"] == builds.RAW_OHLC_KIND_2020_LATEST
    assert job["raw_range"] == "2020_LATEST"
    assert job["range_label"] == "2020-01-01 → Latest"
    assert job["start_date"].startswith("2020-01-01")
    end = pd.Timestamp(job["end_date"], tz="UTC")
    now = pd.Timestamp.now(tz="UTC")
    assert (now - end).total_seconds() < 48 * 3600  # "latest" end rule
    assert len(job["symbols"]) == 20
    assert job["chunk_days"] == 180
    # ~5.75 years / 180d -> ~12 chunks per symbol
    assert job["symbols_progress"][job["symbols"][0]]["total_chunks"] >= 10


def test_make_job_2015_2020_bounds():
    job = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2015_2020")
    assert job["kind"] == builds.RAW_OHLC_KIND_2015_2020
    assert job["raw_range"] == "2015_2020"
    assert job["range_label"] == "2015-01-01 → 2020-01-01"
    assert job["start_date"].startswith("2015-01-01")
    assert job["end_date"].startswith("2020-01-01")
    assert len(job["symbols"]) == 20
    # 5 years / 180d -> ~10-11 chunks per symbol
    assert job["symbols_progress"][job["symbols"][0]]["total_chunks"] >= 9


def test_make_job_legacy_raw_only_unchanged():
    job = builds.make_job({}, symbols=[], timeframe="H1", raw_only=True)
    assert job["kind"] == builds.RAW_OHLC_KIND
    assert job["raw_range"] is None
    assert job["range_label"] is None
    assert job["start_date"] < "2020-01-01"  # still a trailing 10-year window


def test_ranges_never_dedupe_each_other():
    a = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2020_LATEST")
    b = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2015_2020")
    # queue_job dedup requires kind equality -> distinct kinds never collide
    assert a["kind"] != b["kind"]
    assert (a["start_date"], a["end_date"]) != (b["start_date"], b["end_date"])


def test_download_labels_range_aware():
    a = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2020_LATEST")
    b = builds.make_job({}, symbols=[], timeframe="H1", raw_range="2015_2020")
    label, filename = raw_download_label(a, False)
    assert "2020-01-01 → Latest" in label and filename == "raw_ohlc_all_symbols_H1_2020_latest.csv"
    label, filename = raw_download_label(a, True)
    assert "Partial" in label and filename == "raw_ohlc_all_symbols_H1_2020_latest_partial.csv"
    label, filename = raw_download_label(b, False)
    assert "2015-01-01 → 2020-01-01" in label and filename == "raw_ohlc_all_symbols_H1_2015_2020.csv"
    label, filename = raw_download_label(b, True)
    assert "Partial" in label and filename == "raw_ohlc_all_symbols_H1_2015_2020_partial.csv"


def test_download_labels_legacy_fallback():
    legacy = builds.make_job({}, symbols=[], timeframe="H1", raw_only=True)
    label, filename = raw_download_label(legacy, False)
    assert "10-Year" in label and filename == "raw_ohlc_all_symbols_H1_10_years.csv"
    label, filename = raw_download_label(legacy, True)
    assert "Partial 10-Year" in label and filename.endswith("_partial.csv")


def test_invalid_raw_range_falls_back_to_legacy():
    job = builds.make_job({}, symbols=[], timeframe="H1", raw_range="NOPE")
    assert job["kind"] == builds.RAW_OHLC_KIND
    assert job["raw_range"] is None
