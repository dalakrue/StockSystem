from __future__ import annotations
import math, time
from typing import Any, Mapping, Sequence

def unavailable(reason="INSUFFICIENT_DATA"):
    return {"status": reason, "available": False, "shadow_only": True, "production_influence_enabled": False}

def finite(values):
    out=[]
    for v in values or []:
        try:
            x=float(v)
            if math.isfinite(x): out.append(x)
        except Exception: pass
    return out

def clip(x,lo,hi): return max(lo,min(hi,x))

def evaluate(x,y):
 a=finite(x); b=finite(y); n=min(len(a),len(b)); a=a[-n:]; b=b[-n:]
 if n<30:return unavailable()
 concord=discord=0
 for i in range(n-1):
  for j in range(i+1,n):
   z=(a[i]-a[j])*(b[i]-b[j]); concord+=z>0; discord+=z<0
 tau=(concord-discord)/max(concord+discord,1); qa=sorted(a); qb=sorted(b); al=qa[int(.1*(n-1))]; bl=qb[int(.1*(n-1))]; au=qa[int(.9*(n-1))]; bu=qb[int(.9*(n-1))]; low=sum(x<=al and y<=bl for x,y in zip(a,b))/max(sum(x<=al for x in a),1); up=sum(x>=au and y>=bu for x,y in zip(a,b))/max(sum(x>=au for x in a),1)
 return {"status":"AVAILABLE_SHADOW","available":True,"conditional_kendalls_tau":tau,"upper_tail_dependence":up,"lower_tail_dependence":low,"asymmetry_spread":up-low,"copula_family":"CLAYTON" if low>up+.05 else "GUMBEL" if up>low+.05 else "GAUSSIAN","parameter_stability":clip(1-abs(up-low),0,1),"cross_market_confirmation":"CONFIRMED" if abs(tau)>.2 else "WEAK","dependency_break_warning":abs(tau)<.05,"sample_count":n,"shadow_only":True,"production_influence_enabled":False}
