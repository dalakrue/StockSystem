from research.field9_eurusd_h1_orchestrator import run
def build_and_publish_field9(state):
    try:
        payload=run(state);state['field9_eurusd_h1_decision_impact']=payload
        return {'ok':True,'shadow_only':True,'run_id':payload.get('identity',{}).get('run_id'),'readiness':payload.get('readiness',{}).get('status')}
    except Exception as exc:
        payload={'status':'ERROR','reason':f'{type(exc).__name__}: {exc}','shadow_only':True,'production_influence_enabled':False,'production_decision_changed':False,'production_exit_changed':False,'protected_weights_changed':False}
        state['field9_eurusd_h1_decision_impact']=payload
        return {'ok':False,**payload}
