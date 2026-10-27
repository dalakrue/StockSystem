"""Legacy API names routed exclusively to the 240 frozen monthly equations."""
from core.monthly_runtime import MAPPING, live_table, latest_check, decision_text
from core.monthly_strategy_columns import STRATEGY_COLUMNS
STRATEGY_NAMES={m['column']:m['symbol']+'-'+str(m['month']).zfill(2)+' '+m['equation_id'] for m in MAPPING}


def evaluate_pullback_strategies(df,higher_bias=None,middle_bias=None,timeframe='H1',*,symbol=None,check_time=None,quotes=None):
    result={c:dict(entry_condition=False,signal='NO ENTRY',reason='No matching monthly trigger',score=0,eligible=False) for c in STRATEGY_COLUMNS}
    if df is None or df.empty or str(timeframe).upper() not in ('H1','1H'):return result
    symbol=symbol or df.attrs.get('symbol') or (str(df.Symbol.iloc[0]) if 'Symbol' in df else None)
    if not symbol:return result
    table=live_table({symbol:df},check_time or latest_check(),quotes)
    matches=table.loc[table.Symbol.eq(symbol)]
    if matches.empty:return result
    row=matches.iloc[0]
    c=row['Active S Column']
    if c and int(row[c]):
        result[c]=dict(entry_condition=True,signal=row.Direction,reason=row['Equation ID'],score=row.ranking_score,eligible=False,
             strategy_column=c,equation_id=row['Equation ID'],tp_pips=row['Suggested TP Pips'],sl_pips=row['Suggested SL Pips'],
             tp_price=row['TP Price'],sl_price=row['SL Price'],max_hold_hours=row['Max Hold Hours'],danger=row['Danger Enabled'])
    return result


def strategy_decision(results):
    active=[(c,r) for c,r in results.items() if c in STRATEGY_COLUMNS and r.get('entry_condition') and r.get('signal') in ('BUY','SELL')]
    if len(active)>1:raise ValueError('A symbol can have only one active monthly equation')
    if not active:return 'None'
    c,r=active[0]
    return decision_text(r['signal'],c,r.get('equation_id',''),r.get('tp_price'),r.get('sl_price'))


def middle_bias_exit(position_side,current_middle_bias,position_age_hours=None):
    from core.hourly_four_symbol_selector_20260928 import middle_bias_exit_decision
    return middle_bias_exit_decision(position_side,current_middle_bias,position_age_hours=position_age_hours)


def ranked_pullback_scores(df,higher_bias,middle_bias=None):
    return {s:v['score'] for s,v in evaluate_pullback_strategies(df,higher_bias,middle_bias).items()}


def run_pullback_models(df,higher_bias,middle_bias=None,symbol='UNKNOWN'):
    return strategy_decision(evaluate_pullback_strategies(df,higher_bias,middle_bias,symbol=symbol))
