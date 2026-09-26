def validate(context):
    s=context.snapshot; errors=[]
    if not s.run_id: errors.append('Field 8 requires a published canonical run.')
    if s.symbol!='EURUSD' or s.timeframe!='H1': errors.append('Field 8 is restricted to EURUSD H1.')
    return errors
