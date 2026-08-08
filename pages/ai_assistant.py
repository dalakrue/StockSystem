"""Independent deterministic, canonical-grounded multi-symbol assistant."""
from __future__ import annotations

import hashlib
import pandas as pd
import streamlit as st

from core.ai_canonical_intents_v10 import answer_canonical_question, build_ai_evidence_contract, validate_ai_evidence_contract
from core.scalar_normalization_20260625 import metric_text

_EXCHANGE_KEY = 'independent_ai_last_exchange_20260625'
_LAST_HASH_KEY = 'independent_ai_last_question_hash_20260625'


def _nav(page: str) -> None:
    from core.navigation_authority_20260625 import navigate_to
    navigate_to(st.session_state, page, '')
    st.rerun()


def _clear_exchange() -> None:
    st.session_state[_EXCHANGE_KEY] = {}
    st.session_state.pop(_LAST_HASH_KEY, None)
    st.session_state['independent_ai_messages_20260624'] = []


def show(runtime_context=None):
    st.markdown('## 🤖 AI Assistant — Multi-Symbol Field 10 + Field 12 Grounding')
    try:
        from core.canonical_symbol_selection_20260709 import render_selector
        selected_symbol, _, _ = render_selector(
            st, st.session_state, surface='ai',
            title='AI Loaded-Symbol Selector — Synchronizes All Tabs',
            expanded=True,
        )
    except Exception as selector_exc:
        selected_symbol = str(st.session_state.get('canonical_display_symbol_20260709') or '')
        st.caption(f'AI symbol selector unavailable: {type(selector_exc).__name__}: {selector_exc}')
    contract = build_ai_evidence_contract(st.session_state)
    validation = validate_ai_evidence_contract(contract)
    ready = bool(validation.get("ready"))
    missing = list(validation.get("missing_components") or [])
    identity = contract.get('identity', {})
    session = contract.get('session', {})
    status = 'READY' if ready else 'NOT READY'

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric('Readiness', status)
    c2.metric('Run ID', metric_text(identity.get('run_id'))[:24])
    c3.metric('Generation ID', metric_text(identity.get('generation_id'))[:24])
    c4.metric('Snapshot Hash', metric_text(identity.get('snapshot_hash'))[:24])
    c5.metric('Broker candle', metric_text(session.get('broker_candle_time'))[:24])
    c6.metric('Selected symbol', metric_text(contract.get('selected_symbol') or selected_symbol)[:16])
    if not ready:
        st.warning('Missing components: ' + ', '.join(missing))
    st.caption(f"AI readiness is based only on the frozen canonical identity and broker candle contract for this run. Scope: {contract.get('system_health', {}).get('calculation_scope', 'FULL')}")

    from services.openrouter_backend_20260628 import configuration_status as openrouter_configuration_status
    openrouter_status = openrouter_configuration_status(st.session_state)
    api_cols = st.columns(4)
    api_cols[0].metric("OpenRouter", "CONNECTED" if openrouter_status.get("connected") else ("CONFIGURED" if openrouter_status.get("configured") else "NOT CONFIGURED"))
    api_cols[1].metric("AI Model", str(openrouter_status.get("model") or "openrouter/auto")[:28])
    api_cols[2].metric("Key Source", str(openrouter_status.get("source") or "Not configured"))
    api_cols[3].metric("Fallback", "LOCAL + AIRLLM")
    st.caption("OpenRouter is used first when configured. Every request is grounded in the frozen canonical contract and bounded published history; failures fall back locally without breaking the tab.")

    from ui.airllm_mobile_assistant_20260626 import render_airllm_mobile_panel
    airllm_status = render_airllm_mobile_panel(st.session_state)
    # One authoritative Open/Closed control. The panel stores the choice and the
    # submit path reads the same key, so the visible mode always matches execution.
    airllm_mode = bool(st.session_state.get('airllm_open_mode_20260627', False))
    backend = 'OpenRouter canonical assistant' if openrouter_status.get('configured') else ('AirLLM canonical assistant' if airllm_mode else 'Lightweight canonical assistant')
    st.caption('The independent AI tab owns both API and optional local-model backends. No assistant backend changes production calculations.')

    a, b, c = st.columns(3)
    if a.button('🍱 Open Lunch', use_container_width=True, key='ai_open_lunch'):
        _nav('Lunch')
    if b.button('⚙️ Open Settings', use_container_width=True, key='ai_open_settings'):
        _nav('Settings')
    if c.button('🧹 Clear', use_container_width=True, key='ai_clear_exchange'):
        _clear_exchange()
        st.rerun()

    with st.expander('Evidence Used', expanded=False):
        rows = [{
            'source field': 'identity',
            'metric': k,
            'value': v,
            'origin time': session.get('broker_candle_time'),
            'run_id': identity.get('run_id'),
            'generation_id': identity.get('generation_id'),
            'snapshot_hash': identity.get('snapshot_hash'),
        } for k, v in identity.items()]
        frame = pd.DataFrame(rows)
        st.dataframe(frame, use_container_width=True, hide_index=True)

    exchange = st.session_state.get(_EXCHANGE_KEY) or {}
    if exchange.get('question'):
        with st.chat_message('user'):
            st.markdown(exchange['question'])
    if exchange.get('answer'):
        with st.chat_message('assistant'):
            st.markdown(exchange['answer'])
            if exchange.get('backend_note'):
                st.caption(str(exchange.get('backend_note')))
            evidence_used = exchange.get('evidence_used') or []
            if evidence_used:
                with st.expander('Evidence Used', expanded=False):
                    st.dataframe(pd.DataFrame(evidence_used), use_container_width=True, hide_index=True)

    question = st.chat_input(
        'Ask: What is the best symbol to enter now? Or ask about Field 10 entry, Field 12 news, TP/SL, regime, reliability, history or system health',
        key='independent_ai_question_input_20260625',
    )
    if question:
        normalized = ' '.join(str(question).split()).strip()
        question_hash = hashlib.sha256((backend + '|' + str(contract.get('selected_symbol') or '') + '|' + normalized).encode('utf-8')).hexdigest()
        if question_hash != st.session_state.get(_LAST_HASH_KEY):
            result = answer_canonical_question(normalized, st.session_state)
            lightweight_answer = str(result.get('answer') or 'No grounded answer is available for this question.')
            answer = lightweight_answer
            backend_note = 'Lightweight grounded assistant'
            api_failed_note = ''
            if openrouter_status.get('configured'):
                try:
                    from services.openrouter_backend_20260628 import generate_grounded_answer as generate_openrouter_answer
                    api_result = generate_openrouter_answer(normalized, contract, st.session_state)
                except Exception as api_exc:
                    api_result = {'ok': False, 'status': 'FAILED', 'error': f'{type(api_exc).__name__}: {api_exc}'}
                if api_result.get('ok'):
                    answer = str(api_result.get('answer') or lightweight_answer)
                    backend_note = f"OpenRouter: {api_result.get('model')} · canonical + bounded history/NLP grounding"
                else:
                    api_failed_note = f"OpenRouter unavailable ({api_result.get('status')}): {api_result.get('error', '')}. "
            if answer == lightweight_answer and airllm_mode:
                model_id = str(st.session_state.get('airllm_model_id_20260627') or '').strip()
                if model_id:
                    from services.airllm_backend_20260626 import generate_grounded_answer
                    air_result = generate_grounded_answer(normalized, contract, runtime_enabled=True, runtime_model_id=model_id)
                    if air_result.get('ok'):
                        answer = str(air_result.get('answer') or lightweight_answer)
                        backend_note = api_failed_note + f"AirLLM fallback: {air_result.get('model_id')}"
                    else:
                        backend_note = api_failed_note + f"Optional AirLLM unavailable ({air_result.get('status')}). Enhanced canonical NLP/data-mining fallback used; no facts were invented."
                else:
                    backend_note = api_failed_note + 'Enhanced canonical intent + NLP evidence-retrieval + data-mining assistant used (no local model required).'
            elif answer == lightweight_answer:
                backend_note = api_failed_note + 'Deterministic canonical + NLP/data-mining fallback used.'
            st.session_state[_EXCHANGE_KEY] = {
                'question': normalized,
                'answer': answer,
                'backend_note': backend_note,
                'evidence_used': result.get('evidence_used') or [],
            }
            st.session_state[_LAST_HASH_KEY] = question_hash
            st.session_state['ai_evidence_contract_20260625'] = contract
        st.rerun()
