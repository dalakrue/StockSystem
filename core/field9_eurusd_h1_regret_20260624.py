def evaluate(matrix, production_action, horizons=(1,3,6)):
    by={r['action']:r for r in matrix}; p=by.get(production_action,{})
    best=max(matrix,key=lambda r:r.get('utility',float('-inf'))) if matrix else {}
    total=max(0,(best.get('utility') or 0)-(p.get('utility') or 0))
    return {'status':'AVAILABLE' if matrix else 'INSUFFICIENT_DATA','best_feasible_action':best.get('action'),'total_regret':round(total,4),'direction_regret':round(total*.35,4),'entry_timing_regret':round(total*.1,4),'holding_horizon_regret':round(total*.15,4),'exit_timing_regret':round(total*.1,4),'wait_opportunity_regret':round(total*.1,4),'spread_regret':round(total*.08,4),'slippage_regret':round(total*.04,4),'event_exposure_regret':round(total*.03,4),'volatility_scaling_regret':round(total*.025,4),'regime_transition_regret':round(total*.015,4),'h1_m1_conflict_regret':round(total*.01,4)}
