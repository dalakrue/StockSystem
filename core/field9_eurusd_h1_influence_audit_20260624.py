def evaluate(history, impact):
    if len(history)<10:return {'status':'INSUFFICIENT_DATA','reason':'INSUFFICIENT_HISTORY'}
    scored=sorted(history,key=lambda r:float(r.get('net_utility',0)),reverse=True)
    conc=abs(float(scored[0].get('net_utility',0)))/max(.001,sum(abs(float(x.get('net_utility',0))) for x in scored))
    state='FRAGILE' if conc>.35 else 'MODERATELY_CONCENTRATED' if conc>.2 else 'STABLE'
    return {'status':state,'supportive_origins':scored[:5],'contradictory_origins':scored[-5:],'influence_concentration':round(conc,4),'impact_after_removing_top_observation':round(float(impact)*(1-conc),4),'impact_after_removing_top_three':round(float(impact)*(1-min(.8,conc*2)),4),'decision_stability_after_removal':state!='FRAGILE','fragility_state':state}
