"""Export ten-symbol H1 Finder diagnostics from CSV, or labeled synthetic smoke data.

python scripts/adaptive_v4_diagnostics.py --input candles.csv --output diagnostic.csv
Required columns: Symbol, Datetime, Open, High, Low, Close; optional higher_bias,middle_bias.
"""
from __future__ import annotations
import argparse,sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.super_quick_field3_20260722 import _build_middle_finder_history
from core.middle_regime_adaptive_v4 import VERSION

SYMBOLS=('EURUSD','USDJPY','GBPUSD','EURJPY','AUDUSD','USDCHF','EURCAD','AUDCHF','NZDCHF','USDCAD')
def synthetic():
    rng=np.random.default_rng(470);parts=[];n=360
    for k,symbol in enumerate(SYMBOLS):
        pip=.01 if symbol.endswith('JPY') else .0001
        close=(145 if pip==.01 else 1.1)+np.arange(n)*pip*(.16 if k%2 else -.16)+np.sin(np.arange(n)/7+k)*pip*6+rng.normal(0,pip*.4,n)
        op=np.r_[close[0]-pip,close[:-1]]
        parts.append(pd.DataFrame({'Symbol':symbol,'Datetime':pd.date_range('2025-01-01',periods=n,freq='h',tz='UTC'),
                        'Open':op,'High':np.maximum(op,close)+pip*.6,'Low':np.minimum(op,close)-pip*.6,'Close':close}))
    return pd.concat(parts,ignore_index=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--input',type=Path);ap.add_argument('--output',type=Path,default=Path('adaptive_v4_ten_symbol_diagnostics.csv'))
    args=ap.parse_args(); data=pd.read_csv(args.input) if args.input else synthetic()
    required={'Symbol','Datetime','Open','High','Low','Close'}
    if not required.issubset(data):ap.error('Missing columns: '+','.join(sorted(required-set(data))))
    symbols=list(dict.fromkeys(data.Symbol.astype(str).str.upper()))
    if len(symbols)!=10:ap.error('Exactly ten unique symbols required; got '+str(len(symbols)))
    frames={};now=pd.Timestamp.now(tz='UTC')
    for symbol,group in data.groupby('Symbol',sort=False):
        f=group.rename(columns={'Datetime':'open_time','Open':'open','High':'high','Low':'low','Close':'close'}).copy()
        f['open_time']=pd.to_datetime(f['open_time'],utc=True,errors='coerce')
        f=f.loc[f.open_time.notna() & (f.open_time+pd.Timedelta(hours=1)<=now)].sort_values('open_time').drop_duplicates('open_time')
        if f.empty:ap.error(symbol+' has no completed H1 candles')
        frames[str(symbol).upper()]=f
    finder=_build_middle_finder_history(frames,timeframe='H1')
    if set(finder.Symbol)!=set(symbols):ap.error('Finder omitted symbols: '+str(set(symbols)-set(finder.Symbol)))
    if not finder['Strategy Engine'].eq(VERSION).all():raise RuntimeError('Mixed engine versions')
    args.output.parent.mkdir(parents=True,exist_ok=True);finder.to_csv(args.output,index=False)
    print(f'{VERSION}: {len(finder)} completed Finder rows, {finder.Symbol.nunique()} symbols -> {args.output}')
    if not args.input:print('SYNTHETIC SMOKE DATA: no historical performance inference')
if __name__=='__main__':main()
