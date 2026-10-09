"""Settings-run Field 8 orchestration; never called from render paths."""
from core.canonical.snapshot import load_canonical_snapshot
from core.publication_identity_20260625 import freeze_publication_identity
from core.field8_integrated_history_engine_20260624 import build_bundle
from core.repositories.field8_repository import Field8Repository
def build_and_publish_field8(state,repository=None):
    snapshot=load_canonical_snapshot(state)
    if snapshot is None:return {'ok':False,'published':False,'reason':'NO_CANONICAL_SNAPSHOT'}
    # Build causal research only here (Settings run), never in a Lunch renderer.
    try:
        from core.causal_accuracy_upgrade_20260624 import build_shadow_extension
        from core.field8_integrated_history_engine_20260624 import _source_frame
        research = build_shadow_extension(_source_frame(state), as_of=snapshot.broker_candle_time, run_id=str(snapshot.run_id), predictions=dict(snapshot.predictions))
        state['causal_accuracy_shadow_20260624'] = research
    except Exception as exc:
        state['causal_accuracy_shadow_20260624'] = {'mode':'SHADOW_ONLY','status':'FAILED_SAFE','error':str(exc),'production_influence_enabled':False}
    identity=freeze_publication_identity(state, snapshot)
    bundle=build_bundle(snapshot,state,days=25); result=(repository or Field8Repository()).publish(bundle)
    state['field8_publication_identity_20260624']={'run_id':identity['run_id'] or bundle.run_id,'generation_id':identity['generation_id'] or bundle.generation_id,'snapshot_hash':identity['snapshot_hash'] or bundle.snapshot_hash,'database_path':result.get('database_path'),'publication_row_count':result.get('rows',0),'publication_timestamp':result.get('publication_timestamp'),'calculation_version':result.get('calculation_version')}; state['field8_publication_status_20260624']=result
    return result
