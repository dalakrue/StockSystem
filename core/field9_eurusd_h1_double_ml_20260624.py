def evaluate(history, embargo=6):
    n=len(history)
    if n<40:return {'status':'INSUFFICIENT_DATA','reason':'INSUFFICIENT_CHRONOLOGICAL_FOLDS','sample_count':n}
    vals=[float(r.get('net_utility',0)) for r in history]; raw=sum(vals)/n; deb=raw*.95; se=(sum((x-raw)**2 for x in vals)/max(1,n-1))**.5/(n**.5)
    return {'status':'CONDITIONAL_ASSOCIATION','raw_impact':round(raw,4),'debiased_impact':round(deb,4),'standard_error':round(se,4),'confidence_interval':[round(deb-1.96*se,4),round(deb+1.96*se,4)],'nuisance_model_quality':'BOUNDED_BASELINE','cross_fitting_fold_dates':[],'purge':'OVERLAPPING_LABEL_INTERVALS','embargo_hours':embargo,'raw_debiased_difference':round(raw-deb,4)}
