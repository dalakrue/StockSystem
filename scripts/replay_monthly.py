#!/usr/bin/env python3
"""Reproducible frozen H1 equation and portfolio exports; no training."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import argparse,json
import pandas as pd
from core.monthly_backtest import replay_portfolio,independent_diagnostics,bundle
from core.monthly_runtime import ROOT
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--candles',required=True,help='Raw all-symbol H1 CSV or Parquet; UTC bar-open Datetime')
parser.add_argument('--output',required=True)
parser.add_argument('--start');parser.add_argument('--end');parser.add_argument('--strict-only',action='store_true')
args=parser.parse_args()
raw=pd.read_parquet(args.candles) if Path(args.candles).suffix.lower()=='.parquet' else pd.read_csv(args.candles,low_memory=False)
result=replay_portfolio(raw,entry_start=args.start,entry_end=args.end,strict_only=args.strict_only)
diagnostic=independent_diagnostics(raw,signals=result['signals'],strict_only=args.strict_only)
out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
result['signals'].to_parquet(out/'all_rows_S1_S240.parquet',index=False)
result['signals'].to_csv(out/'all_rows_S1_S240.csv',index=False,chunksize=2000)
result['trades'].to_csv(out/'trade_log.csv',index=False)
result['checks'].to_csv(out/'check_decisions.csv',index=False)
diagnostic.to_csv(out/'independent_equation_diagnostics.csv',index=False)
(out/'portfolio_metrics.json').write_text(json.dumps(result['metrics'],indent=2,default=str,allow_nan=False))
(out/'monthly_replay.zip').write_bytes(bundle(result,diagnostic,include_signals=False))
for name in ('equation_column_map.json','equation_column_map.csv'):(out/name).write_bytes((ROOT/name).read_bytes())
print(json.dumps(result['metrics'],indent=2,default=str))
