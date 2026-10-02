from core.publication_identity_20260625 import freeze_publication_identity
"""Read-only Field 8 view model using the exact Settings publication identity."""
from core.repositories.field8_repository import Field8Repository
from lunch.field_08.tables import prepare_table

def build_view_model(context):
    s=context.snapshot; state=context.history_repository.state; repo=Field8Repository()
    published_identity=state.get('field8_publication_identity_20260624') or {}
    current=freeze_publication_identity(state, s)
    exact={k:str(published_identity.get(k) or '') for k in ('run_id','generation_id','snapshot_hash')}
    errors=[]; df=None
    try:
        if all(exact.values()): df=repo.load(exact['run_id'],exact['generation_id'],exact['snapshot_hash'],days=25)
        else: df=repo.load('__MISSING__','__MISSING__','__MISSING__',days=25)
    except Exception as exc:
        import pandas as pd
        df=pd.DataFrame(); errors=[type(exc).__name__,str(exc)]
    meta=repo.publication_metadata(exact['run_id'],exact['generation_id'],exact['snapshot_hash']) if all(exact.values()) else None
    latest_same_run=repo.latest_for_run(current['run_id'])
    identity_match=all(exact.get(k)==current.get(k) for k in current) and all(exact.values())
    diagnostic={
      'current canonical run_id':current['run_id'],'current generation_id':current['generation_id'],'current snapshot_hash':current['snapshot_hash'] or 'UNAVAILABLE',
      'published run_id':exact['run_id'] or 'UNAVAILABLE','published generation_id':exact['generation_id'] or 'UNAVAILABLE','published snapshot_hash':exact['snapshot_hash'] or 'UNAVAILABLE',
      'repository database path':str(repo.path.resolve()),'publication status':'EXACT_MATCH' if identity_match and not df.empty else 'IDENTITY_MISMATCH' if latest_same_run else 'NOT_PUBLISHED',
      'publication row count':int((meta or {}).get('row_count') or 0),'source data row count':int((meta or {}).get('source_row_count') or 0),'required minimum row count':1,
      'last exception type':errors[0] if errors else 'NONE','last exception message':errors[1] if errors else 'NONE',
      'recommended corrective action':'Re-run Settings once to publish the exact canonical identity.' if not identity_match else ('Inspect source history and publication transaction.' if df.empty else 'NONE')}
    if latest_same_run and not identity_match:
        diagnostic['publication status']='SAME_RUN_IDENTITY_MISMATCH'; diagnostic['recommended corrective action']='A completed publication exists for this run, but generation/hash differ. Re-publish; stale rows were not mixed.'
    summaries={}
    if not df.empty:
        latest=df.iloc[0]
        for k in ('alpha_beta_delta_state','beta_instability','delta_alpha_h','delta_acceleration_h','path_reliability','regime_reliability','structural_break_state','rolling_coverage','dynamic_model_status','model_confidence_set_status','validation_status','research_integrated_trust_score','reason_codes'): summaries[k]=latest.get(k)
    return {'context':context,'table':prepare_table(df,context.search_query),'raw_table':df,'summaries':summaries,'identity':exact,'current_identity':current,'identity_match':identity_match,'published':identity_match and not df.empty,'diagnostic':diagnostic}
