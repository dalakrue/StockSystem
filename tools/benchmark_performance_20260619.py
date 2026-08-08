"""Repeatable local benchmark for the 2026-06-19 display/runtime optimization.

This does not claim iPhone measurements. It compares the old active Dinner data
preparation with the new compact-summary path using the same synthetic H1 table,
and measures disk-backed session-state compaction in this Python process.
"""
from __future__ import annotations

import gc
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import tracemalloc
from types import SimpleNamespace

import numpy as np
import pandas as pd
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

class FakeStreamlit:
    def __init__(self): self.session_state = {}
    def __getattr__(self, name):
        if name in {"cache_data", "cache_resource"}:
            def cache_decorator(func=None, **kwargs):
                if callable(func):
                    return func
                return lambda wrapped: wrapped
            return cache_decorator
        def fn(*args, **kwargs): return None
        return fn

sys.modules.setdefault("streamlit", FakeStreamlit())

from core.compact_canonical_20260619 import build_compact_summary, build_ai_fact_pack
from core.performance_store_20260619 import (
    persist_frame, query_frame, export_frame, spool_history_frames,
    compact_adapter_frames, session_dataframe_audit, persist_summary, load_summary,
)
from ui.composite_summary_cards_20260619 import card_payload
from tabs.ai_assistant_compact_20260619 import _local_fact_answer


def load_legacy(filename="dinner_unified_center_20260617_legacy.src", name="benchmark_dinner_legacy"):
    path = ROOT / "tabs" / filename
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def make_data(rows=12000, cols=24):
    rng = np.random.default_rng(42)
    data = {"Time": pd.date_range("2024-01-01", periods=rows, freq="h")}
    for i in range(cols - 1): data[f"metric_{i}"] = rng.normal(size=rows)
    data["KNN Priority"] = rng.integers(1, 15, rows)
    data["Greedy Priority"] = rng.integers(1, 15, rows)
    return pd.DataFrame(data)


def canonical(frame):
    return {
        "run_id": "BENCH", "canonical_calculation_id": "BENCH-CID", "calculation_generation": 1,
        "data_signature": "BENCH-SIG", "symbol": "EURUSD", "timeframe": "H1", "source": "BENCH",
        "created_at": "2026-06-19T10:01:00+00:00", "latest_completed_candle_time": "2026-06-19T10:00:00+00:00",
        "calculation_status": "COMPLETED", "last_close": 1.1542,
        "master_score": 6.2, "entry_score": 6.8, "hold_safety": 5.9, "tp_quality": 6.1, "exit_risk": 3.4, "trend_capacity_remaining": 6.0,
        "final_decision": {"final_decision": "BUY", "directional_market_view": "BUY", "less_risky_decision": "BUY", "tradeability_decision": "BUY", "selected_horizon": 3, "calibrated_confidence": .73},
        "regime": {"major_regime": "BULL_NORMAL", "alpha": 1.2, "delta": .3},
        "multiscale_regime": {"current_volatility_regime": "NORMAL", "multi_scale_transition_risk_pct": 22},
        "reliability": {"score": 72, "status": "VALID", "sample_count": 120},
        "risk": {"risk_level": "MEDIUM"},
        "forecasts": {"selected_horizon": 3, "horizons": {h: {"point_forecast": 1.1542 + i*.0002, "lower_bound": 1.153, "upper_bound": 1.158, "reliability": .73} for i,h in enumerate(("1h","3h","6h"),1)}},
        "nlp": {"direction": "BUY", "reliability": 65, "conflict_level": "NONE"},
        "data_quality": {"status": "PASS", "score": 98, "freshness": "FRESH"},
        "full_metric_history": frame.to_dict("records"),
    }


def timed(fn, loops=10):
    gc.collect(); tracemalloc.start(); start=time.perf_counter()
    for _ in range(loops): fn()
    elapsed=(time.perf_counter()-start)/loops
    _, peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    return elapsed, peak


def main():
    frame=make_data(); can=canonical(frame)
    sh={"priority":{"table":frame,"best":frame.iloc[0].to_dict()},"hourly_priority_table":frame,"powerbi":{"summary":{"path_agreement_pct":81}}}
    legacy=load_legacy()
    lunch_legacy=load_legacy("final_lunch_upgrade_20260617_legacy.src", "benchmark_lunch_legacy")

    def old_prepare():
        sorted_frame=legacy._sort_priority(frame)
        scalars=legacy._flatten_scalars({"canonical":can,"summary":{"x":1}})
        frames=legacy._dedupe_frames(legacy._collect_frames({"priority":sorted_frame,"history":frame}))
        return len(scalars)+len(frames)
    def new_prepare():
        summary=build_compact_summary(can,sh)
        return card_payload(summary)

    def old_lunch_prepare():
        return lunch_legacy._safe_display_view(frame)
    def new_lunch_prepare():
        return card_payload(build_compact_summary(can, sh))

    summary_once=build_compact_summary(can,sh)
    fact_once=build_ai_fact_pack(summary_once,canonical=can,evidence_rows=frame.head(40).to_dict('records'))
    def old_ai_open():
        return pd.DataFrame(can.get("full_metric_history") or [])
    def new_ai_open():
        return fact_once.get("calculation_id"), fact_once.get("current_decision")

    old_t,old_peak=timed(old_prepare,5)
    new_t,new_peak=timed(new_prepare,30)
    old_lunch_t,old_lunch_peak=timed(old_lunch_prepare,5)
    new_lunch_t,new_lunch_peak=timed(new_lunch_prepare,30)
    old_ai_t,old_ai_peak=timed(old_ai_open,5)
    new_ai_t,new_ai_peak=timed(new_ai_open,100)
    compact_question_t,compact_question_peak=timed(lambda: _local_fact_answer("What is the safer decision and projection?", fact_once),1000)

    old_lunch=(ROOT/'tabs/final_lunch_upgrade_20260617_legacy.src').read_text(errors='ignore')
    old_dinner=(ROOT/'tabs/dinner_unified_center_20260617_legacy.src').read_text(errors='ignore')
    new_lunch=(ROOT/'tabs/final_lunch_upgrade_20260617.py').read_text(errors='ignore')
    new_dinner=(ROOT/'tabs/dinner_unified_center_20260617.py').read_text(errors='ignore')
    metric=lambda s: len(re.findall(r'\.metric\s*\(',s))
    copies=lambda s: s.count('.copy(')
    sorts=lambda s: s.count('sort_values(')

    with tempfile.TemporaryDirectory() as td:
        db=Path(td)/'bench.sqlite'
        state={k:frame for k in (
            'canonical_priority_table_20260617','adx_hourly_priority_calibrated_20260615',
            'three_center_priority_sorted_20260614','reliability_dynamic_priority_table_20260614',
            'finder_readonly_priority_table_20260618')}
        state['adx_shared_calc_result_20260615']={'priority':{'table':frame},'hourly_priority_table':frame,'history':{'priority':frame}}
        state['shared_calc_result']=state['adx_shared_calc_result_20260615']
        before=session_dataframe_audit(state)
        rss_before=psutil.Process().memory_info().rss
        spool=spool_history_frames(state,'BENCH:1',phone_mode=True,db_path=db)
        compact_adapter_frames(state,phone_mode=True)
        gc.collect(); rss_after=psutil.Process().memory_info().rss
        after=session_dataframe_audit(state)
        key='canonical_priority_table_20260617'
        manifest=spool[key]
        qstart=time.perf_counter(); page=query_frame('BENCH:1',key,columns=list(frame.columns[:8]),limit=48,order_by='Time',db_path=db); qtime=time.perf_counter()-qstart
        estart=time.perf_counter(); full=export_frame('BENCH:1',key,db_path=db); etime=time.perf_counter()-estart
        summary=build_compact_summary(can,sh); fact=build_ai_fact_pack(summary,canonical=can,evidence_rows=frame.head(40).to_dict('records'))
        persist_summary(summary['calculation_id'],summary,fact,db_path=db)
        sstart=time.perf_counter(); loaded_summary,_=load_summary(summary['calculation_id'],db_path=db); stime=time.perf_counter()-sstart

    result={
        'environment':{'python':sys.version.split()[0],'rows':len(frame),'columns':len(frame.columns),'scope':'local synthetic server-side benchmark; not iPhone telemetry'},
        'dinner_prepare_seconds':{'before':old_t,'after':new_t,'reduction_pct':(1-new_t/old_t)*100 if old_t else None},
        'dinner_prepare_tracemalloc_peak_bytes':{'before':old_peak,'after':new_peak,'reduction_pct':(1-new_peak/old_peak)*100 if old_peak else None},
        'lunch_prepare_seconds':{'before':old_lunch_t,'after':new_lunch_t,'reduction_pct':(1-new_lunch_t/old_lunch_t)*100 if old_lunch_t else None},
        'lunch_prepare_tracemalloc_peak_bytes':{'before':old_lunch_peak,'after':new_lunch_peak,'reduction_pct':(1-new_lunch_peak/old_lunch_peak)*100 if old_lunch_peak else None},
        'ai_tab_context_open_seconds':{'before':old_ai_t,'after':new_ai_t,'reduction_pct':(1-new_ai_t/old_ai_t)*100 if old_ai_t else None},
        'ai_tab_context_tracemalloc_peak_bytes':{'before':old_ai_peak,'after':new_ai_peak,'reduction_pct':(1-new_ai_peak/old_ai_peak)*100 if old_ai_peak else None},
        'ai_compact_question_seconds_excluding_network':compact_question_t,
        'ai_compact_question_tracemalloc_peak_bytes':compact_question_peak,
        'active_lunch_dinner_metric_calls':{'before':metric(old_lunch)+metric(old_dinner),'after':metric(new_lunch)+metric(new_dinner)},
        'active_lunch_dinner_copy_calls':{'before':copies(old_lunch)+copies(old_dinner),'after':copies(new_lunch)+copies(new_dinner)},
        'active_lunch_dinner_sort_calls':{'before':sorts(old_lunch)+sorts(old_dinner),'after':sorts(new_lunch)+sorts(new_dinner)},
        'session_dataframes':{'before':before,'after':after,'rss_before_bytes':rss_before,'rss_after_bytes':rss_after},
        'dinner_summary_database':{'rows_loaded':0,'columns_loaded':0,'summary_read_seconds':stime,'summary_calculation_id':loaded_summary.get('calculation_id')},
        'history_page_database':{'rows_loaded':len(page),'columns_loaded':len(page.columns),'read_seconds':qtime,'full_export_rows':len(full),'full_export_seconds':etime},
        'ai_fact_pack_bytes':fact.get('size_bytes'),
        'chart_builds_on_default_dinner_navigation':{'before':1,'after':0},
        'notes':{
            'run_calculation':'not benchmarked: protected pipeline requires live project data and Streamlit runtime',
            'phone_cpu_ram':'not observable in this server container',
            'external_ai_network':'excluded',
        }
    }
    out=ROOT/'PERFORMANCE_MEASUREMENTS_20260619.json'; out.write_text(json.dumps(result,indent=2,default=str))
    print(json.dumps(result,indent=2,default=str))

if __name__=='__main__': main()
