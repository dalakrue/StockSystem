"""Versioned additive contract for Field 8 alpha-beta-delta shadow evidence."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
HORIZONS=(1,3,6)
ABD_STATES={'UP_EDGE_STRENGTHENING','UP_EDGE_WEAKENING','DOWN_EDGE_STRENGTHENING','DOWN_EDGE_WEAKENING','ZERO_CROSS_UP','ZERO_CROSS_DOWN','HIGH_BETA_FRAGILITY','STRUCTURAL_BREAK_WARNING','INSUFFICIENT_EVIDENCE'}
MCS_STATUSES={'INSUFFICIENT_EVIDENCE','NOT_COMPARABLE','MCS_INCLUDED','MCS_EXCLUDED','PENDING_REVALIDATION'}
REQUIRED_IDENTITY=('run_id','generation_id','source_snapshot_hash','symbol','timeframe','forecast_origin_time','target_time','calculation_version','maturity_status')
@dataclass(frozen=True)
class PublicationIdentity:
    run_id:str; generation_id:str; source_snapshot_hash:str; symbol:str; timeframe:str; forecast_origin_time:str; target_time:str; calculation_version:str; maturity_status:str

def validate_probability(v:Any)->bool:
    try:return 0.0<=float(v)<=1.0
    except Exception:return False
