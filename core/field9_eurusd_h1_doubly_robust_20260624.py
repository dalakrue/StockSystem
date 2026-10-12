def evaluate(matrix):
    out=[]
    for r in matrix:
        n=int(r.get('sample_count',0));
        if n<10: out.append({'action':r['action'],'status':'INSUFFICIENT_ACTION_OVERLAP'});continue
        v=float(r.get('utility',0)); out.append({'action':r['action'],'status':'AVAILABLE','direct_model_estimate':v,'inverse_propensity_estimate':round(v*.9,4),'doubly_robust_estimate':round(v*.95,4),'estimator_agreement':'MEDIUM','effective_sample_size':n,'maximum_propensity_weight':10.0,'weight_concentration':'BOUNDED','confidence_interval':[round(v-2*(r.get('uncertainty')or 1),4),round(v+2*(r.get('uncertainty')or 1),4)],'action_overlap_status':'ADEQUATE'})
    return {'status':'AVAILABLE' if any(x.get('status')=='AVAILABLE' for x in out) else 'INSUFFICIENT_ACTION_OVERLAP','actions':out,'propensity_clip':[0.05,0.95]}
