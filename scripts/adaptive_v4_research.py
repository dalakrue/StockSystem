"""Analyze closed-bar v4 outcomes from a Finder CSV (research, not validation).

python scripts/adaptive_v4_research.py --finder adaptive_v4_ten_symbol_diagnostics.csv --output research.json
"""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.adaptive_v4_research import analyze_trades,settle_closed_bars
from core.middle_regime_adaptive_v4 import VERSION

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finder',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args();data=pd.read_csv(args.finder,low_memory=False,keep_default_na=False)
    if 'Strategy Engine' not in data or not data['Strategy Engine'].eq(VERSION).all():
        parser.error('Finder must contain only current v4 rows')
    required={'Symbol','Datetime','Open Price','Highest Price','Lowest Price','Close Price','V4 Direction','Suggested TP Price','Suggested SL Price','Market Regime','Strategy Family'}
    if not required.issubset(data):parser.error('Missing columns: '+','.join(sorted(required-set(data))))
    results=[]
    for symbol,group in data.groupby('Symbol'):
        group=group.sort_values('Datetime').reset_index(drop=True)
        frame=group.rename(columns={'Datetime':'open_time','Open Price':'open','Highest Price':'high','Lowest Price':'low','Close Price':'close'})
        for col in ('open','high','low','close','Suggested TP Price','Suggested SL Price'):
            frame[col]=pd.to_numeric(frame[col],errors='coerce')
        audit=frame[['V4 Direction','Suggested TP Price','Suggested SL Price','Market Regime','Strategy Family']]
        outcomes=settle_closed_bars(frame,audit,str(symbol))
        if not outcomes.empty:results.append(outcomes)
    trades=pd.concat(results,ignore_index=True) if results else pd.DataFrame()
    report=analyze_trades(trades);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,default=str),encoding='utf-8')
    print(f'{VERSION}: research summary of {len(trades)} hypothetical trades -> {args.output}')
    print('RESEARCH ONLY: costs, spreads and forward validation are not included.')
if __name__=='__main__':main()
