"""Field 9 EURUSD H1 shadow-only data and utility contract."""
from __future__ import annotations
ACTIONS=("BUY","SELL","WAIT","HOLD","REDUCE","EXIT")
HORIZONS=(1,2,3,4,5,6)
REQUIRED_SETTLEMENT_HORIZONS=(1,3,6)
SCHEMA_VERSION="field9-eurusd-h1-1.0"
MODEL_VERSION="bounded-shadow-20260624"
SHADOW_FLAGS={"shadow_only":True,"production_influence_enabled":False,"production_decision_changed":False,"production_exit_changed":False,"protected_weights_changed":False}
UTILITY_COEFFICIENTS={"mae":0.25,"tail_breach":1.0,"high_confidence_wrong":0.75,"unsupported_evidence":0.5,"holding_time":0.05}
BOUNDS={"h1_rows":4000,"m1_rows":12000,"settled_outcomes":1500,"features":24,"models":12,"bootstrap_replications":64,"rashomon_models":12,"influence_rows":10,"history_rows":25,"cube_cells":216}
def unavailable(reason:str,status:str="UNAVAILABLE",**data):
    return {"status":status,"reason":reason,"data":data,"limitations":[reason],"performance":{}}
def settlement_state(row:dict)->str:
    states=[str(row.get(f"h{h}_status","PENDING")).upper()=="SETTLED" for h in REQUIRED_SETTLEMENT_HORIZONS]
    return "FULLY_SETTLED" if all(states) else "PARTIALLY_SETTLED" if any(states) else "UNSETTLED"
