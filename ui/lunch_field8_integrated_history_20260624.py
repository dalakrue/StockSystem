"""Production-route adapter for nested Field 8 rendering."""
import streamlit as st
from core.canonical.snapshot import load_canonical_snapshot
from core.repositories.history_repository import HistoryRepository
from core.repositories.outcome_repository import OutcomeRepository
from core.repositories.research_repository import ResearchRepository
from core.repositories.run_repository import RunRepository
from lunch.context import LunchRenderContext
from lunch.field_08.contract import validate
from lunch.field_08.view_model import build_view_model
from lunch.field_08.renderer import render
def render_field8_integrated_history(state):
    snapshot=load_canonical_snapshot(state)
    if snapshot is None: st.info('Run Calculation + Open Lunch in Settings to publish Field 8 evidence.'); return
    context=LunchRenderContext(snapshot,RunRepository(state),HistoryRepository(state),OutcomeRepository(),ResearchRepository(),'field_08',str(state.get('lunch_search_query_20260621') or ''),bool(state.get('phone_mode',False)))
    errors=validate(context)
    if errors:
        for error in errors: st.warning(error)
        return
    render(build_view_model(context))
