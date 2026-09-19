def evaluate(matrix, variance_lambda=.5):
    rows=[]
    for r in matrix:
        if r.get('support_status')=='INSUFFICIENT_ACTION_OVERLAP':
            rows.append({"action":r['action'],"status":"INSUFFICIENT_ACTION_OVERLAP"});continue
        loss=-(r.get('utility') or 0); var=(r.get('uncertainty') or 0)**2; penalty=variance_lambda*(var**.5)
        rows.append({"action":r['action'],"counterfactual_expected_loss":round(loss,4),"variance_penalty":round(penalty,4),"conservative_score":round(loss+penalty,4),"effective_sample_size":r.get('sample_count',0),"unsupported_action_warning":False})
    ranked=sorted([r for r in rows if 'conservative_score'in r],key=lambda x:x['conservative_score'])
    for i,r in enumerate(ranked,1):r['rank']=i
    return {"status":"AVAILABLE" if ranked else "INSUFFICIENT_ACTION_OVERLAP","actions":rows,"conservative_action_ranking":[r['action'] for r in ranked]}
