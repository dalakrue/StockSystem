def evaluate(history):
    out=[]
    for t in (.50,.55,.60,.65,.70,.75,.80):
        rows=[r for r in history if float(r.get('confidence',0))>=t]; n=len(rows)
        wrong=sum(not bool(r.get('direction_correct',False)) for r in rows)
        out.append({"threshold":t,"coverage":round(n/max(1,len(history)),4),"wrong_decision_risk":round(wrong/max(1,n),4) if n else None,"adverse_barrier_risk":None,"high_confidence_error_risk":round(wrong/max(1,n),4) if n else None,"average_net_utility":round(sum(float(r.get('net_utility',0)) for r in rows)/n,4) if n else None,"sample_count":n})
    return {"status":"SHADOW_ACTIONABLE" if len(history)>=50 else "INSUFFICIENT_DATA","curve":out}
