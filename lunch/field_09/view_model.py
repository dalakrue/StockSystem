def build_view_model(context):
    state=context.history_repository.state
    payload=state.get('field9_eurusd_h1_decision_impact') or {}
    additive=state.get('field9_counterfactual_policy_20260625') or {}
    return {'context':context,'payload':payload,'summary':payload.get('current_summary',{}),'path':payload.get('impact_path',[]),'matrix':payload.get('counterfactual_action_matrix',[]),'history':payload.get('history',[]),'identity':payload.get('identity',{}),'readiness':payload.get('readiness',{}),'research_grade_v17':state.get('research_grade_system_v17_20260624') or {},'counterfactual_policy_20260625':additive}
