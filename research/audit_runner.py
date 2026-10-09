#!/usr/bin/env python3
"""Reproduce declared splits, full regeneration, ledgers and cost stress tables.

Usage: python research/audit_runner.py --csv first.csv --csv second.csv --output research_run
No provider credentials or network requests are made. No input means an explicit
blocked audit, never manufactured backtest results.
"""
from __future__ import annotations
import argparse,json,hashlib,sys,zipfile,platform
from pathlib import Path
from dataclasses import asdict,replace
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
from core.execution_policy_20261003 import get_policy,VERSION
from core.strategy_audit_20260924 import build_strategy_audit,STRATEGY_ALIASES,DISABLED_STRATEGY_IDS
from core.audited_portfolio_replay_20261003 import normalize_quotes,replay_portfolio,SCENARIOS

SPLITS={'TRAIN':('2024-10-03T00:00Z','2024-12-31T23:59:59Z'),
 'VALIDATION':('2025-01-01T00:00Z','2025-12-31T23:59:59Z'),
 'HELDOUT_PARAMETER_REPLAY':('2026-01-01T00:00Z','2026-10-03T23:59:59Z')}
# Thresholds fixed before viewing any new forward results.
GATES={'validation_net_gt':0,'validation_ev_gt':0,'forward_net_gt':0,'forward_ev_gt':0,'profit_factor_gt':1,
 'weekly_bootstrap_ev_lower_gt':0,'profitable_walk_forward_fraction_gt':.5,'max_hold_hours_le':24,
 'max_single_symbol_profit_fraction_le':.50,'max_single_quarter_profit_fraction_le':.50,
 'stress_ev_gt':0,'unresolved_execution_defects_eq':0,'max_account_drawdown_percent':10.0}


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def write_json(path,obj): path.write_text(json.dumps(obj,indent=2,default=str,allow_nan=False))

def json_safe(obj):
    if isinstance(obj,dict):return {k:json_safe(v) for k,v in obj.items()}
    if isinstance(obj,list):return [json_safe(x) for x in obj]
    if isinstance(obj,(float,np.floating)) and not np.isfinite(obj):return None
    if isinstance(obj,np.integer):return int(obj)
    return obj


def regenerate(raw,removed=(),relaxation=None,policy=None):
    from core.super_quick_field3_20260722 import _historical_fast_standard
    from core.field3_three_regime_engine import standard_windows
    from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection
    pieces=[];windows=standard_windows('H1')
    for sym,g in raw.groupby('Symbol',sort=True):
        g=g.sort_values('open_time',kind='mergesort').reset_index(drop=True)
        lower=_historical_fast_standard(g,window_bars=windows['LOWER'])
        middle=_historical_fast_standard(g,window_bars=windows['MIDDLE'])
        higher=_historical_fast_standard(g,window_bars=windows['HIGHER'])
        if len(middle)!=len(g):raise ValueError('Raw input has duplicate/invalid timestamps; resolve before regeneration')
        audit=build_strategy_audit(g,higher.Bias,middle.Bias,backtest_fast=True,removed_strategy_ids=removed,relaxation=relaxation,policy=policy)
        audit['Symbol']=sym;audit['Middle Regime Bias']=middle.Bias;audit['Lower Regime Bias']=lower.Bias;audit['Higher Standard Regime Bias']=higher.Bias
        audit['Datetime']=g.open_time
        pieces.append(audit)
    return attach_hourly_four_selection(pd.concat(pieces,ignore_index=True))


def calibration_comparison(raw,signals,out,policy):
    """Fit only matured pre-2025 labels; save offline diagnostics, never approve live."""
    from core.final_pair_forecast_20261003 import final_pair_labels
    from research.calibration import TemporalOutcomeModel,export_model_json
    from core.calibrated_target_model_20261003 import infer_model
    rows=[];labels=[]
    for sym,q in raw.groupby('Symbol',sort=True):
        q=q.sort_values('bar_open_time').reset_index(drop=True)
        s=signals.loc[signals.Symbol.eq(sym)].sort_values('bar_open_time').reset_index(drop=True)
        if len(q)!=len(s) or not q.bar_open_time.equals(s.bar_open_time):
            raise ValueError('Final-pair calibration timeline mismatch')
        q['bias']=s.entry_side;q['pip_size']=.01 if 'JPY' in sym else .0001
        side=np.where(s.entry_side.eq('BUY'),1.,np.where(s.entry_side.eq('SELL'),-1.,0.))
        lab=final_pair_labels(q,side,s.tp_price,s.sl_price,policy=policy,ambiguity='SL_FIRST',bias_exit=True)
        lab['label_complete'] &= s.unique_family_count.gt(0)
        rows.append(s);labels.append(lab)
    x=pd.concat(rows,ignore_index=True);y=pd.concat(labels,ignore_index=True)
    try:
        model=TemporalOutcomeModel().fit(x,y)
        spec=export_model_json(model,x,y,out/'offline_calibrated_model.json',policy)
        scores,bins=model.evaluate(x,y)
        scores.to_csv(out/'classifier_brier_scores.csv',index=False)
        bins.to_csv(out/'classifier_calibration_bins.csv',index=False)
        pred=model.predict(x)
        valid=y.label_complete & pd.to_datetime(x.signal_available_at,utc=True).ge(pd.Timestamp(model.training_end))
        comparison=x.loc[valid,['Symbol','signal_available_at','regime_family','unique_family_count','expected_net_pips','expected_net_pips_lower_bound']].copy()
        comparison['observed_outcome']=y.loc[valid,'outcome'];comparison['observed_net_pips']=y.loc[valid,'net_pips']
        for c in pred:comparison['classifier_p_'+c.lower()]=pred.loc[valid,c]
        pip=np.where(x.Symbol.str.contains('JPY'),.01,.0001)
        direction=np.where(x.entry_side.eq('BUY'),1.,-1.)
        close=np.concatenate([g.sort_values('bar_open_time').close.to_numpy() for _,g in raw.groupby('Symbol',sort=True)])
        forecasts=infer_model(spec,x,direction*(x.tp_price-close),direction*(close-x.sl_price),pip)
        comparison['classifier_expected_net_pips']=forecasts.loc[valid,'expected_net_pips']
        comparison['classifier_ev_lower_diagnostic']=forecasts.loc[valid,'expected_net_pips_lower_bound']
        comparison.to_csv(out/'classifier_vs_empirical_forecasts.csv',index=False)
        empirical=[]
        for c in ('TP','SL','BIAS','TIMEOUT'):
            p=x.loc[valid,'p_'+c.lower()] if 'p_'+c.lower() in x else pd.Series(dtype=float)
            actual=y.loc[valid,'outcome'].eq(c).astype(float)
            usable=p.notna()
            empirical.append({'outcome':c,'sample_count':int(usable.sum()),'brier_score':float(((p[usable]-actual[usable])**2).mean()) if usable.any() else None})
        pd.DataFrame(empirical).to_csv(out/'empirical_brier_scores.csv',index=False)
        status={'status':'OFFLINE_TRAINING_FIT_COMPLETE','training_end':model.training_end,'fit_samples':model.sample_count,
          'calibration_samples':model.calibration_count,'deployment_enabled':False,'classes':model.classes,
          'note':'2025/2026 evaluation only; 2026 may be contaminated. No acceptance manifest is generated.'}
    except ValueError as exc:
        status={'status':'INSUFFICIENT_CALIBRATION_EVIDENCE','reason':str(exc),'deployment_enabled':False}
    write_json(out/'calibration_status.json',status)
    return status


def weekly_bootstrap(ledger,iterations=1000,seed=73):
    if ledger.empty or ledger.net_pips.notna().sum()<20:return {'status':'INSUFFICIENT_TRADES','ev_lower':None,'net_interval':None}
    l=ledger.dropna(subset=['net_pips']).copy();l['week']=pd.to_datetime(l.exit_at,utc=True).dt.tz_localize(None).dt.to_period('W')
    blocks=l.groupby('week').agg(net=('net_pips','sum'),n=('net_pips','size'))
    if len(blocks)<8:return {'status':'INSUFFICIENT_WEEK_BLOCKS','ev_lower':None,'net_interval':None}
    rng=np.random.default_rng(seed);choices=rng.integers(0,len(blocks),(iterations,len(blocks)))
    v=blocks.net.to_numpy()[choices].sum(axis=1);n=blocks.n.to_numpy()[choices].sum(axis=1)
    return {'status':'COMPLETE','ev_lower':float(np.quantile(v/n,.025)),'ev_upper':float(np.quantile(v/n,.975)),
        'net_interval':np.quantile(v,[.025,.975]).tolist(),'negative_net_fraction':float((v<=0).mean()),'weeks':len(blocks),'iterations':iterations}


def attribution(ledger):
    if ledger.empty:return pd.DataFrame(columns=['Strategy','Attributed Net Pips','Associated Trades','Association EV'])
    records=[]
    for _,r in ledger.dropna(subset=['net_pips']).iterrows():
        ids=json.loads(r.active_strategy_ids)
        for s in ids:records.append({'Strategy':s,'fractional_net_pips':r.net_pips/max(1,len(ids)),'associated_net_pips':r.net_pips})
    if not records:return pd.DataFrame(columns=['Strategy','Attributed Net Pips','Associated Trades','Association EV'])
    return pd.DataFrame(records).groupby('Strategy').agg(**{'Attributed Net Pips':('fractional_net_pips','sum'),'Associated Trades':('associated_net_pips','size'),'Association EV':('associated_net_pips','mean')}).reset_index()


def replay_available_window(signals,raw,**kwargs):
    """Do not enumerate a whole year when the raw file has no quotes in it."""
    from core.audited_portfolio_replay_20261003 import metrics
    lo=pd.to_datetime(kwargs.get('entry_start'),utc=True);hi=pd.to_datetime(kwargs.get('entry_end'),utc=True)
    available=pd.to_datetime(raw.open_time,utc=True)
    if raw.empty or (lo is not None and available.max()<lo) or (hi is not None and available.min()>hi):
        empty=pd.DataFrame()
        return {'trades':empty,'hourly_equity':empty,'skips':pd.DataFrame([{'Symbol':'ALL','reason':'NO_RAW_QUOTES_IN_ENTRY_WINDOW'}]),'metrics':metrics(empty)}
    # Outside the supplied raw span there is no possible executable entry.
    # Internal quote gaps are still processed and censored by the core replay.
    if lo is not None:kwargs['entry_start']=max(lo,available.min())
    if hi is not None:kwargs['entry_end']=min(hi,available.max())
    return replay_portfolio(signals,raw,**kwargs)


def run_comparisons(raw,signals,out,p,removed_symbols=(),label='original',tp=77,sl=103,experiments=None):
    rows=[];ledgers={}
    for scenario in SCENARIOS:
        for split,(lo,hi) in SPLITS.items():
            result=replay_available_window(signals,raw,scenario=scenario,tp_pips=tp,sl_pips=sl,policy=p,entry_start=lo,entry_end=hi,removed_symbols=removed_symbols)
            tag=f'{label}_{SCENARIOS.index(scenario)+1}_{split}'
            result['trades'].to_csv(out/f'trades_{tag}.csv',index=False)
            result['skips'].to_csv(out/f'skips_{tag}.csv',index=False)
            result['hourly_equity'].to_csv(out/f'equity_{tag}.csv',index=False)
            rows.append({'variant':label,'scenario':scenario,'split':split,'TP':tp if not scenario.startswith('Dynamic') else 'DYNAMIC','SL':sl if scenario=='Fixed TP/SL' else 'DYNAMIC_OR_BIAS',**result['metrics']})
            ledgers[(scenario,split)]=result['trades']
            if experiments is not None:experiments.append({'experiment':tag,'type':'scheduled_portfolio_replay','policy':asdict(p)})
    return pd.DataFrame(rows),ledgers


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--csv',action='append',default=[]);ap.add_argument('--output',default='reports/research_run')
    ap.add_argument('--policy');ap.add_argument('--full-suite',action='store_true');ap.add_argument('--exhaustive-grid',action='store_true')
    ap.add_argument('--independent-trials',type=int);args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    policy=get_policy(json.loads(Path(args.policy).read_text()) if args.policy else None)
    freeze={'engine':VERSION,'python':platform.python_version(),'policy':asdict(policy),'acceptance_gates':GATES,
        'splits':SPLITS,'input_hashes':{str(Path(x).resolve()):sha(x) for x in args.csv},
        'code_hashes':{str(x.relative_to(ROOT)):sha(x) for x in sorted(ROOT.rglob('*.py')) if '__pycache__' not in str(x)}}
    write_json(out/'freeze_manifest.json',freeze)
    if not args.csv:
        blocked={'status':'BLOCKED_MISSING_RESEARCH_DATA','baseline_rows_claimed':283516,'baseline_symbols_claimed':20,'weekend_rows_claimed':38104,
            'training_winner_claimed':{'TP':77,'SL':103},'validation_integer_pairs_claimed':241081,'baseline_verified':False,
            'reason':'The attached app ZIP has no matching continuous two-year 20-symbol CSV. Broker executable bid/ask quotes and account inputs are also absent.',
            'live_configuration_qualifies':False,'portfolio_improvement_measured':False,'forecast_intervals':None,'experiments_run':0}
        write_json(out/'audit_status.json',blocked)
        pd.DataFrame([{'variant':v,'scenario':s,'split':split,'status':'BLOCKED_MISSING_DATA','Net Pip':None,'Max DD':None,'EV':None}
          for v in ('original','remove_symbols','remove_strategies','remove_symbols_and_strategies') for s in SCENARIOS for split in SPLITS]).to_csv(out/'scenario_comparison.csv',index=False)
        print(json.dumps(blocked));return
    source=pd.concat([pd.read_csv(x) for x in args.csv],ignore_index=True)
    raw=normalize_quotes(source)
    raw.to_parquet(out/'raw_quotes_frozen.parquet',index=False,compression='zstd')
    audit={'rows':len(raw),'symbols':int(raw.Symbol.nunique()),'start':str(raw.open_time.min()),'end':str(raw.open_time.max()),
        'weekend_utc_rows':int(raw.open_time.dt.dayofweek.ge(5).sum()),'non_executable_rows':int((~raw.market_executable).sum()),
        'broker_unverified_rows':int((~raw.broker_quote_verified).sum()),'duplicate_symbol_timestamps':int(raw.duplicated(['Symbol','open_time'],keep=False).sum()),
        'baseline_size_matches':len(raw)==283516 and raw.Symbol.nunique()==20}
    write_json(out/'input_audit.json',audit)
    if audit['duplicate_symbol_timestamps']:raise ValueError('Duplicate raw quotes require reconciliation; no arbitrary last-row fill')
    signals=regenerate(raw,policy=policy);signals.to_parquet(out/'derived_signals.parquet',index=False,compression='zstd')
    calibration=calibration_comparison(raw,signals,out,policy)
    signals[['Symbol','signal_available_at','unique_family_count','entry_origin','entry_eligible','research_entry_eligible','expected_net_pips','expected_net_pips_lower_bound','TP Filter Reasons']].to_csv(out/'signal_opportunity_rankings.csv',index=False)
    pd.DataFrame({'Alias':list(STRATEGY_ALIASES),'Owner':list(STRATEGY_ALIASES.values())}).to_csv(out/'strategy_aliases.csv',index=False)
    pd.DataFrame({'Strategy':[f'S{i}' for i in range(1,121)],'Hits':[int(signals[f'S{i} Entry Condition'].sum()) for i in range(1,121)]}).to_csv(out/'strategy_trigger_counts.csv',index=False)
    experiments=[];tables=[];tp,sl=77,103
    if args.exhaustive_grid:
        from research.fixed_grid import exhaustive_search
        for split in ('TRAIN','VALIDATION'):
            grid=exhaustive_search(signals,raw,policy,*SPLITS[split])
            grid.to_csv(out/f'integer_grid_{split}.csv',index=False)
            experiments.append({'experiment':'integer_grid_'+split,'trials':len(grid),'range':'10..500 inclusive'})
            if split=='TRAIN':tp,sl=(int(v) for v in grid.iloc[0][['TP','SL']])
    t,ledgers=run_comparisons(raw,signals,out,policy,tp=tp,sl=sl,experiments=experiments);tables.append(t)
    training=ledgers[('Fixed TP/SL','TRAIN')]
    symbols=training.dropna(subset=['net_pips']).groupby('Symbol').net_pips.sum().sort_values() if len(training) else pd.Series(dtype=float)
    symbols.rename('Net Pip').to_csv(out/'training_symbol_rankings.csv')
    ar=attribution(training).sort_values('Attributed Net Pips');ar.to_csv(out/'training_strategy_rankings.csv',index=False)
    worst_symbols=list(symbols.head(5).index[symbols.head(5)<0]);worst_strategies=list(ar.loc[ar['Attributed Net Pips']<0,'Strategy'].head(5))
    # Removals are training-selected; every selector and rescue mask regenerates.
    for label,rs,rt in [('remove_symbols',worst_symbols,[]),('remove_strategies',[],worst_strategies),('remove_symbols_and_strategies',worst_symbols,worst_strategies)]:
        changed=regenerate(raw,removed=rt,policy=policy) if rt else signals
        table,_=run_comparisons(raw,changed,out,policy,rs,label,tp,sl,experiments);tables.append(table)
    stresses=[];boots=[]
    for scenario in SCENARIOS:
        boots.append({'scenario':scenario,**weekly_bootstrap(ledgers[(scenario,'VALIDATION')])})
        for label,p2,amb in [('SL_FIRST',policy,'SL_FIRST'),('WIDER_COSTS',replace(policy,spread_pips=4,slippage_pips=1),'SL_FIRST')]:
            result=replay_available_window(signals,raw,scenario=scenario,tp_pips=tp,sl_pips=sl,policy=p2,entry_start=SPLITS['VALIDATION'][0],entry_end=SPLITS['VALIDATION'][1],ambiguity=amb)
            stresses.append({'scenario':scenario,'stress':label,**result['metrics']});experiments.append({'experiment':scenario+'_'+label})
    pd.DataFrame(stresses).to_csv(out/'cost_and_intrabar_stress.csv',index=False)
    write_json(out/'weekly_block_bootstrap.json',json_safe(boots))
    if args.full_suite:
        extra=[]
        for sym in sorted(raw.Symbol.unique()):
            result=replay_available_window(signals,raw,scenario='Fixed TP/SL',tp_pips=tp,sl_pips=sl,policy=policy,entry_start=SPLITS['VALIDATION'][0],entry_end=SPLITS['VALIDATION'][1],removed_symbols=[sym])
            extra.append({'test':'LEAVE_ONE_SYMBOL_OUT_REALLOCATION','removed':sym,**result['metrics']});experiments.append({'experiment':'LOSO_'+sym})
        # Individual/group ablation regenerates opportunities rather than deleting
        # associated P&L. These experiments are exploratory training only.
        active=[f'S{i}' for i in range(1,121) if f'S{i}' not in STRATEGY_ALIASES and f'S{i}' not in DISABLED_STRATEGY_IDS]
        removals=[[s] for s in active]+[[f'S{i}' for i in range(a,b+1)] for a,b in [(1,20),(21,50),(51,92),(93,110),(111,120)]]
        for ids in removals:
            changed=regenerate(raw,removed=ids,policy=policy)
            result=replay_available_window(changed,raw,scenario='Fixed TP/SL',tp_pips=tp,sl_pips=sl,policy=policy,entry_start=SPLITS['TRAIN'][0],entry_end=SPLITS['TRAIN'][1])
            extra.append({'test':'FULL_REGENERATION_ABLATION_TRAIN','removed':','.join(ids),**result['metrics']});experiments.append({'experiment':'ABLATE_'+','.join(ids)})
        for relax in (0.,.1,.2,.4):
            changed=regenerate(raw,relaxation=relax,policy=replace(policy,relaxation=relax))
            result=replay_available_window(changed,raw,scenario='Fixed TP/SL',tp_pips=tp,sl_pips=sl,policy=replace(policy,relaxation=relax),entry_start=SPLITS['TRAIN'][0],entry_end=SPLITS['TRAIN'][1])
            extra.append({'test':'RELAXATION_TRAIN_ONLY','removed':relax,**result['metrics']});experiments.append({'experiment':'RELAX_'+str(relax)})
        pd.DataFrame(extra).to_csv(out/'ablations_and_reallocation.csv',index=False)
    folds=[]
    for month in pd.date_range('2025-01-01','2025-12-01',freq='MS',tz='UTC'):
        # Fixed training choice evaluated month-by-month with a 24h boundary purge.
        result=replay_available_window(signals,raw,scenario='Fixed TP/SL',tp_pips=tp,sl_pips=sl,policy=policy,entry_start=month+pd.Timedelta(hours=24),entry_end=month+pd.offsets.MonthEnd()+pd.Timedelta(hours=23))
        folds.append({'month':str(month),'purge_hours':24,**result['metrics']})
    pd.DataFrame(folds).to_csv(out/'purged_monthly_validation.csv',index=False)
    sensitivity=[]
    for t2 in sorted(set(max(10,min(500,tp+d)) for d in (-5,0,5))):
        for s2 in sorted(set(max(10,min(500,sl+d)) for d in (-5,0,5))):
            result=replay_available_window(signals,raw,scenario='Fixed TP/SL',tp_pips=t2,sl_pips=s2,policy=policy,entry_start=SPLITS['VALIDATION'][0],entry_end=SPLITS['VALIDATION'][1])
            sensitivity.append({'TP':t2,'SL':s2,**result['metrics']});experiments.append({'experiment':f'SENSITIVITY_{t2}_{s2}'})
    pd.DataFrame(sensitivity).to_csv(out/'target_sensitivity.csv',index=False)
    for scenario in SCENARIOS:
        l=ledgers[(scenario,'VALIDATION')]
        if l.empty:continue
        l.groupby(['regime_family','volatility_bucket']).net_pips.agg(['count','sum','mean']).to_csv(out/f'regime_{SCENARIOS.index(scenario)}.csv')
        l.groupby('Symbol').net_pips.agg(['count','sum','mean']).to_csv(out/f'symbol_{SCENARIOS.index(scenario)}.csv')
        l.loc[l.exit_reason=='SL'].groupby('Symbol').stop_then_rebound.agg(['count','mean']).to_csv(out/f'rebound_{SCENARIOS.index(scenario)}.csv')
        attribution(l).to_csv(out/f'strategy_{SCENARIOS.index(scenario)}.csv',index=False)
    pd.concat(tables,ignore_index=True).to_csv(out/'scenario_comparison.csv',index=False)
    status={'status':'RESEARCH_REPLAY_COMPLETE_NOT_LIVE_ACCEPTED','live_configuration_qualifies':False,'untouched_forward_verified':False,
        'baseline_winner_verified':False,'claimed_validation_unprofitable_verified':False,
        'reason':'2026 is a parameter replay, not proven untouched. Broker bid/ask, independent forward history and account risk evidence are required.',
        'calibrated_classifier':calibration,
        'DSR_PBO':'NOT_RUN: independent trial estimate and valid independent return matrix required',
        'independent_trial_estimate':args.independent_trials,'experiments_run':len(experiments),
        'true_walk_forward_refitting':'NOT_RUN: available pre-2025 training is too short; monthly results are purged fixed-parameter validation',
        'money_profit_percent_drawdown':'NOT_REPORTED: account currency/equity/lots/conversion quotes/broker pip values missing',
        'lower_timeframe_bid_ask_reconstruction':'NOT_RUN: no executable lower-timeframe evidence',
        'controlled_export_replay_vs_full_regeneration':'NOT_RUN unless original candidate policy supplied; legacy module retained for audit'}
    write_json(out/'audit_status.json',json_safe(status));write_json(out/'experiment_log.json',experiments)
    print(json.dumps(status))

if __name__=='__main__':main()
