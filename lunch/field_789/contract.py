def validate(context):
    e=[]
    if not context.snapshot.run_id:e.append("Field 789 requires a valid canonical run.")
    if context.snapshot.symbol!='EURUSD' or context.snapshot.timeframe!='H1':e.append("Field 789 is scoped to EURUSD H1.")
    return e
