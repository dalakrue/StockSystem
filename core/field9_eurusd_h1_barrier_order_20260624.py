def evaluate(m1_complete, sample_count, tp_probability=None):
    if sample_count<10:return {'status':'INSUFFICIENT_DATA','reason':'INSUFFICIENT_MATURED_BARRIER_OUTCOMES'}
    if not m1_complete:return {'status':'INTRABAR_ORDER_AMBIGUOUS','reason':'COMPLETE_CAUSAL_M1_SEQUENCE_UNAVAILABLE'}
    p=.5 if tp_probability is None else float(tp_probability)
    return {'status':'AVAILABLE','tp_before_risk_probability':p,'risk_before_tp_probability':1-p,'neither_hit_probability':0.0,'median_time_to_tp':None,'median_time_to_adverse_barrier':None,'first_passage_advantage':round(2*p-1,4),'barrier_order_regret':round(max(0,.5-p),4),'sample_count':sample_count}
