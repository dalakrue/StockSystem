from __future__ import annotations
POLICY_VERSION="ARCEF-SV-POLICY-1"
def decide(direction_score, strength, uncertainty, entry_quality, cp_prob, thresholds=None):
    t={"buy":.24,"sell":-.24,"strong":.15,"max_uncertainty":.62,"entry":.55}; t.update(thresholds or {})
    if uncertainty>t["max_uncertainty"] or cp_prob>.65: return "WAIT"
    if direction_score>=t["buy"]:
        return "BUY" if entry_quality>=t["entry"] and strength>=t["strong"] else "WAIT PULLBACK"
    if direction_score<=t["sell"]:
        return "SELL" if entry_quality>=t["entry"] and strength<=-t["strong"] else "WAIT PULLBACK"
    return "HOLD" if abs(direction_score)>.08 else "WAIT"
