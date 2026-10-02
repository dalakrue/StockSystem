from __future__ import annotations

def shrink(successes, n, global_rel=.5, min_samples=20, prior_strength=20):
    n=max(0,int(n)); empirical=float(successes)/n if n else global_rel
    return (empirical*n+global_rel*prior_strength)/(n+prior_strength), n>=min_samples

def matrix(global_rel=.5):
    dims=("regime","session","volatility_state","spread_state","news_impact_state","regime_age","time_horizon","data_quality_state")
    return [{"dimension":d,"bucket":"CURRENT","reliability":global_rel,"sample_count":0,"sparse_shrinkage":True} for d in dims]
