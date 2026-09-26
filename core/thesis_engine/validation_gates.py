from __future__ import annotations

def default_validation(model_names):
    return {n:{"white_reality_check":"NOT_RUN","spa":"NOT_RUN","giacomini_white":"NOT_RUN","mcs_member":True,"cscv":"NOT_RUN","pbo":0.0,"gate":1.0,"reason":"insufficient settled history; shadow-visible"} for n in model_names}
