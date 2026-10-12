"""Canonical AI evidence contract and deterministic intent routing for Field 5."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
from typing import Any, Mapping, MutableMapping

import pandas as pd

from core.publication_identity_20260625 import freeze_publication_identity
from core.session_context_20260625 import resolve_session_contract

INTENTS = (
    'tp_sl', 'best_symbol', 'entry', 'forecast_horizon', 'green_path', 'session', 'current_decision',
    'regime', 'reliability_uncertainty', 'history', 'reversal', 'model_comparison',
    'system_health', 'general_system_question',
)


@dataclass(frozen=True)
class ParsedQuestion:
    intent: str
    action: str | None = None
    horizon: int | None = None
    field_number: int | None = None
    last_n_days: int | None = None


def _m(v: Any) -> Mapping[str, Any]:
    return v if isinstance(v, Mapping) else {}


def _f(v: Any, default: float | None = None) -> float | None:
    try:
        x = float(v)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _canonical(state: Mapping[str, Any]) -> Mapping[str, Any]:
    from core.canonical_lookup_20260626 import resolve_canonical
    return resolve_canonical(state)


def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', str(text or '').strip().lower())


def _parse(text: str) -> ParsedQuestion:
    q = _normalize(text)
    action = None
    for candidate in ('buy', 'sell', 'wait'):
        if re.search(rf'\b{candidate}\b', q):
            action = candidate.upper()
            break
    horizon = None
    h = re.search(r'\bh\s*([1236])\b|\b([1236])h\b', q)
    if h:
        horizon = int(next(g for g in h.groups() if g))
    field_number = None
    f = re.search(r'\bfield\s*((?:1[0-3])|[1-9])\b', q)
    if f:
        field_number = int(f.group(1))
    last_n_days = None
    n = re.search(r'last\s+(\d+)\s+days?', q)
    if n:
        last_n_days = int(n.group(1))

    rules = [
        ('tp_sl', ('tp', 'sl', 'take profit', 'stop loss')),
        ('best_symbol', ('best symbol', 'which symbol', 'top symbol', 'symbol to enter', 'best pair', 'top pair', 'best trade now')),
        ('entry', ('entry', 'enter', 'entry decision')),
        ('forecast_horizon', ('prediction', 'forecast', 'h1', 'h2', 'h3', 'h6', 'projection')),
        ('green_path', ('green path', 'green line', 'less risky path', 'less-risky path')),
        ('session', ('session', 'london', 'new york', 'overlap', 'asia', 'sydney', 'which session is best')),
        ('current_decision', ('current decision', 'decision now', 'buy or sell')),
        ('regime', ('regime', 'market state', 'transition')),
        ('reliability_uncertainty', ('reliability', 'uncertainty', 'confidence', 'trust')),
        ('history', ('history', 'last 25', 'past', 'previous')),
        ('reversal', ('reverse', 'reversal', 'what will reverse')),
        ('model_comparison', ('model', 'compare', 'spa', 'cpa', 'best model')),
        ('system_health', ('ready', 'run id', 'system health', 'publication', 'sync', 'broker candle')),
    ]
    for intent, phrases in rules:
        if any(phrase in q for phrase in phrases):
            return ParsedQuestion(intent=intent, action=action, horizon=horizon, field_number=field_number, last_n_days=last_n_days)
    return ParsedQuestion(intent='general_system_question', action=action, horizon=horizon, field_number=field_number, last_n_days=last_n_days)


def _history_frame(state: Mapping[str, Any], limit: int = 25) -> list[dict[str, Any]]:
    for key in ('full_metric_history_df_20260618', 'prediction_vs_actual_history_df', 'dv_pp_bt_hist'):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.head(limit).to_dict('records')
    return []


def _frame_records(value: Any, limit: int = 24) -> list[dict[str, Any]]:
    if isinstance(value, pd.DataFrame) and not value.empty:
        return value.head(limit).where(pd.notna(value.head(limit)), None).to_dict('records')
    if isinstance(value, list):
        return [dict(row) for row in value[:limit] if isinstance(row, Mapping)]
    return []


def _selected_symbol(state: Mapping[str, Any]) -> str:
    try:
        from core.global_symbol_context import get_global_symbol_context
        value = get_global_symbol_context(state).active_display_symbol
    except Exception:
        value = ''
    return str(value or '').strip().upper().replace('/', '').replace('_', '').replace(' ', '')


def _symbol_row(rows: list[dict[str, Any]], symbol: str) -> dict[str, Any]:
    target = str(symbol or '').strip().upper().replace('/', '').replace('_', '').replace(' ', '')
    for row in rows:
        value = str(row.get('Symbol') or '').strip().upper().replace('/', '').replace('_', '').replace(' ', '')
        if value == target:
            return dict(row)
    return {}


def _best_field10_row(contract: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    rows = [dict(row) for row in (contract.get('field10_multi_symbol_ranking') or []) if isinstance(row, Mapping)]
    if not rows:
        return {}, False
    def rank_value(row: Mapping[str, Any]) -> float:
        return _f(row.get('Rank'), 10_000.0) or 10_000.0
    rows.sort(key=rank_value)
    candidates = []
    for row in rows:
        permission = str(row.get('Entry permission') or row.get('Trade Permission') or '').upper()
        if any(token in permission for token in ('TRADE CANDIDATE', 'ENTRY_ALLOWED', 'ALLOWED', 'READY_TO_ENTER')) and not any(token in permission for token in ('BLOCK', 'WAIT', 'NO_TRADE')):
            candidates.append(row)
    return (candidates[0], True) if candidates else (rows[0], False)


def _best_field3_row(contract: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    rows = [dict(row) for row in (contract.get('field3_multi_symbol_ranking') or []) if isinstance(row, Mapping)]
    if not rows:
        return {}, False
    rows.sort(key=lambda row: _f(row.get('Rank'), 10_000.0) or 10_000.0)
    candidates = [row for row in rows if str(row.get('Entry Permission') or '').upper() == 'ALLOWED']
    return (candidates[0], True) if candidates else (rows[0], False)


def build_ai_evidence_contract(state: Mapping[str, Any]) -> dict[str, Any]:
    canonical = _canonical(state)
    identity = dict(freeze_publication_identity(state, canonical))
    institutional_identity = _m(state.get('canonical_run_identity_20260708'))
    try:
        from core.global_symbol_context import get_global_symbol_context
        global_context = get_global_symbol_context(state)
    except Exception:
        global_context = None
    # GlobalSymbolContext is the identity authority; legacy identity is read-only fallback.
    if global_context and global_context.universe_id:
        identity['run_id'] = global_context.parent_run_id or identity.get('run_id')
        identity['generation_id'] = global_context.generation or identity.get('generation_id')
        identity['snapshot_hash'] = global_context.snapshot_hash or identity.get('snapshot_hash')
    identity['run_id'] = identity.get('run_id') or institutional_identity.get('parent_run_id')
    identity['generation_id'] = (
        identity.get('generation_id')
        or institutional_identity.get('generation')
        or identity.get('run_id')
    )
    identity['snapshot_hash'] = identity.get('snapshot_hash') or institutional_identity.get('snapshot_hash')
    session = dict(resolve_session_contract(state, canonical).to_dict())
    institutional_candle = (global_context.latest_completed_candle if global_context else '') or institutional_identity.get('broker_candle_time')
    if institutional_candle:
        session['broker_candle_time'] = institutional_candle
        session['utc_candle_time'] = institutional_candle
    session['source_run_id'] = identity.get('run_id')
    session['generation_id'] = identity.get('generation_id')
    session['snapshot_hash'] = identity.get('snapshot_hash')
    final = _m(canonical.get('final_decision'))
    regime = _m(canonical.get('regime'))
    forecasts = _m(canonical.get('forecasts'))
    field2 = _m(state.get('session_adaptive_projection_20260625'))
    green_df = state.get('less_risky_projection_20260625')
    green_path = green_df.to_dict('records') if isinstance(green_df, pd.DataFrame) and not green_df.empty else []
    field7 = _m(state.get('field7_session_drift_cpa_20260625') or state.get('field_07_research_summary_v11'))
    field8 = _m(state.get('field8_session_calibration_spa_20260625') or state.get('field8_publication_status_20260624'))
    field9 = _m(state.get('field9_doubly_robust_20260625') or state.get('field9_eurusd_h1_decision_impact'))
    field6 = _m(state.get('field6_session_bayesian_fusion_20260625') or state.get('field6_combined_history_summary_20260622'))
    selected_symbol = _selected_symbol(state)
    field10_source = state.get('field10_institutional_ranking_20260708')
    if not isinstance(field10_source, pd.DataFrame) or field10_source.empty:
        field10_source = state.get('field10_current_table_20260701')
    field10_rows = _frame_records(field10_source)
    field12_rows = _frame_records(state.get('field12_fundamental_nlp_rank_20260722'))
    field3_rows = _frame_records(state.get('field3_multisymbol_regime_20260708'))
    selected_field10 = _symbol_row(field10_rows, selected_symbol)
    selected_field12 = _symbol_row(field12_rows, selected_symbol)
    selected_field3 = _symbol_row(field3_rows, selected_symbol)
    health = {
        'run_id_present': bool(identity['run_id']),
        'generation_id_present': bool(identity['generation_id']),
        'snapshot_hash_present': bool(identity['snapshot_hash']),
        'broker_candle_time_present': bool(session.get('broker_candle_time')),
        'canonical_identity_valid': all(bool(identity[k]) for k in ('run_id', 'generation_id', 'snapshot_hash')),
        'publication_status': 'READY' if all(bool(identity[k]) for k in ('run_id', 'generation_id', 'snapshot_hash')) else 'NOT_READY',
        'calculation_scope': str((state or {}).get('settings_calculation_scope_20260625') or 'FULL').upper(),
    }
    tp = _f(final.get('tp_price'), _f(canonical.get('tp_price')))
    sl = _f(final.get('sl_price'), _f(canonical.get('sl_price')))
    current_price = _f(_m(canonical.get('market')).get('current_price'), _f(canonical.get('current_price')))
    pack = {
        'identity': identity,
        'current_decision': str(final.get('final_decision') or canonical.get('decision') or 'UNAVAILABLE'),
        'entry_decision': str(final.get('entry_decision') or canonical.get('entry_decision') or final.get('final_decision') or 'UNAVAILABLE'),
        'less_risky_decision': str(final.get('less_risky_decision') or canonical.get('less_risky_bias') or 'UNAVAILABLE'),
        'current_price': current_price,
        'tp_sl': {'tp': tp, 'sl': sl},
        'prediction_horizons': forecasts,
        'green_path': green_path,
        'session': session,
        'regime_standards': {
            'major_regime': regime.get('major_regime') or regime.get('current_regime') or canonical.get('regime'),
            'reliability': regime.get('reliability') or regime.get('regime_reliability'),
            'three_standard_agreement': regime.get('three_standard_agreement') or regime.get('agreement_score'),
        },
        'reliability': canonical.get('reliability_score') or _m(canonical.get('reliability')).get('score') or regime.get('reliability'),
        'uncertainty': final.get('uncertainty_pct') or final.get('uncertainty') or canonical.get('uncertainty'),
        'reversal_conditions': field9.get('minimum_reversal_conditions') or _m(field9.get('current_summary')).get('reversal_conditions') or canonical.get('reversal_conditions') or 'UNAVAILABLE',
        'field1_history': _history_frame(state, 25),
        'field2_settled_evidence': field2,
        'field3_regime_evidence': regime,
        'field6_fusion_evidence': field6,
        'field7_drift_cpa_evidence': field7,
        'field8_calibration_spa_evidence': field8,
        'field9_counterfactual_value_evidence': field9,
        'selected_symbol': selected_symbol,
        'field10_multi_symbol_ranking': field10_rows,
        'field10_selected_symbol_row': selected_field10,
        'field12_fundamental_news_ranking': field12_rows,
        'field12_selected_symbol_row': selected_field12,
        'field3_multi_symbol_ranking': field3_rows,
        'field3_selected_symbol_row': selected_field3,
        'multi_symbol_answer_authority': 'FIELD_3',
        'fundamental_news_authority': 'FIELD_12',
        'system_health': health,
    }
    return pack


def validate_ai_evidence_contract(contract: Mapping[str, Any]) -> dict[str, Any]:
    missing = []
    identity = _m(contract.get('identity'))
    for key in ('run_id', 'generation_id', 'snapshot_hash'):
        if not identity.get(key):
            missing.append(key)
    if not _m(contract.get('session')).get('broker_candle_time'):
        missing.append('broker_candle_time')
    decision = str(contract.get('current_decision') or '').strip().upper()
    if decision in {'', 'UNAVAILABLE'} and not (contract.get('field3_multi_symbol_ranking') or contract.get('field10_multi_symbol_ranking')):
        missing.append('current_decision')
    return {"ready": len(missing) == 0, "missing_components": missing}


def _evidence_rows(contract: Mapping[str, Any], parsed: ParsedQuestion) -> list[dict[str, Any]]:
    identity = _m(contract.get('identity'))
    rows = []
    def add(source_field: str, metric: str, value: Any):
        rows.append({
            'source field': source_field,
            'metric': metric,
            'value': value,
            'origin time': _m(contract.get('session')).get('broker_candle_time'),
            'run_id': identity.get('run_id'),
            'generation_id': identity.get('generation_id'),
            'snapshot_hash': identity.get('snapshot_hash'),
        })
    add('identity', 'current_decision', contract.get('current_decision'))
    add('identity', 'less_risky_decision', contract.get('less_risky_decision'))
    add('identity', 'current_price', contract.get('current_price'))
    if parsed.intent in {'best_symbol', 'entry'}:
        best, approved = _best_field3_row(contract)
        add('field3', 'multi_symbol_best_row', best)
        add('field3', 'entry_approved', approved)
        if best:
            symbol = str(best.get('Symbol') or '')
            news = _symbol_row(list(contract.get('field12_fundamental_news_ranking') or []), symbol)
            add('field12', 'fundamental_news_for_best_symbol', news)
    if parsed.horizon:
        forecasts = _m(contract.get('prediction_horizons')).get('horizons')
        item = _m(_m(forecasts).get(f'{parsed.horizon}h') if isinstance(forecasts, Mapping) else {})
        add('field2', f'H{parsed.horizon} forecast', item)
    if parsed.intent == 'green_path':
        green = contract.get('green_path') or []
        add('field2', 'green_path_rows', len(green))
    if parsed.intent == 'session':
        add('field2', 'selected_session', _m(contract.get('session')).get('selected_session'))
    return rows


def _horizon_item(contract: Mapping[str, Any], horizon: int | None) -> Mapping[str, Any]:
    forecasts = _m(contract.get('prediction_horizons')).get('horizons')
    if isinstance(forecasts, Mapping):
        if horizon is None:
            horizon = 3
        return _m(forecasts.get(f'{horizon}h') or forecasts.get(str(horizon)) or forecasts.get(horizon))
    return {}


def _answer(parsed: ParsedQuestion, contract: Mapping[str, Any]) -> str:
    identity = _m(contract.get('identity'))
    current_price = _f(contract.get('current_price'))
    session = _m(contract.get('session'))
    if parsed.intent == 'best_symbol':
        best, approved = _best_field3_row(contract)
        if not best:
            return 'Field 3 has no published three-regime ranking for the current global universe. Load symbols and run a Settings calculation.'
        symbol = str(best.get('Symbol') or 'UNAVAILABLE')
        rank = best.get('Rank', '—')
        permission = str(best.get('Entry Permission') or 'BLOCKED')
        bias = str(best.get('Composite Bias') or 'WAIT')
        strength = best.get('Decision Strength', 'UNAVAILABLE')
        reliability = best.get('Calibrated Reliability', 'UNAVAILABLE')
        news = _symbol_row(list(contract.get('field12_fundamental_news_ranking') or []), symbol)
        news_text = 'Field 12 news evidence is unavailable.'
        if news:
            news_text = (
                f"Field 12 fundamental context: bias={news.get('Fundamental Bias', 'WAIT')}, "
                f"permission={news.get('News Permission', 'UNAVAILABLE')}, "
                f"headline={news.get('Latest High-Impact Symbol News', 'NEWS_UNAVAILABLE')}."
            )
        opening = (f'Best currently approved symbol from Field 3: {symbol} (rank {rank}).' if approved else
                   f'No symbol is currently approved. The highest-ranked Field 3 watch symbol is {symbol} (rank {rank}).')
        return (
            f"{opening}\nField 3 entry permission: {permission}.\nField 3 composite bias: {bias}.\n"
            f"Decision strength: {strength}; calibrated reliability: {reliability}.\n{news_text}\n"
            "Authority note: ranking uses the complete saved Field 3 table for the exact global run and generation."
        )
    if parsed.intent == 'entry':
        selected = str(contract.get('selected_symbol') or 'UNAVAILABLE')
        row = _m(contract.get('field3_selected_symbol_row'))
        if row:
            return (
                f"Selected symbol: {selected}\nField 3 entry permission: {row.get('Entry Permission', 'BLOCKED')}\n"
                f"Field 3 composite bias: {row.get('Composite Bias', 'WAIT')}\nField 3 rank: {row.get('Rank', '—')}\n"
                f"Decision strength: {row.get('Decision Strength', 'UNAVAILABLE')}\n"
                "This answer uses exact saved evidence for the active Global Symbol; it does not calculate or fetch."
            )
        return f'No Field 3 row is published for the active Global Symbol {selected}. Reload saved evidence or run Settings once.'
    if parsed.intent == 'tp_sl':
        tp = _f(_m(contract.get('tp_sl')).get('tp'))
        sl = _f(_m(contract.get('tp_sl')).get('sl'))
        action = parsed.action or str(contract.get('current_decision') or 'UNAVAILABLE')
        lines = [f'Action: {action}', f'Current price: {current_price if current_price is not None else "UNAVAILABLE"}']
        if tp is not None:
            pips = abs(tp - current_price) * 10000 if current_price is not None else None
            lines.append(f'TP: {tp}')
            lines.append(f'Distance in pips: {pips:.1f}' if pips is not None else 'Distance in pips: UNAVAILABLE')
        else:
            lines.append('TP evidence unavailable')
        if sl is not None:
            lines.append(f'SL: {sl}')
        lines.append(f'Relevant horizon: H{parsed.horizon or 3}')
        lines.append(f'Broker candle: {session.get("broker_candle_time") or "UNAVAILABLE"}')
        lines.append(f'Run ID: {identity.get("run_id") or "UNAVAILABLE"}')
        lines.append('Evidence sources: canonical decision, protected forecast bundle, AI evidence contract')
        return '\n'.join(lines)
    if parsed.intent == 'forecast_horizon':
        item = _horizon_item(contract, parsed.horizon)
        return f"H{parsed.horizon or 3} prediction: {item or 'UNAVAILABLE'}\nBroker candle: {session.get('broker_candle_time')}\nRun ID: {identity.get('run_id')}"
    if parsed.intent == 'green_path':
        green = contract.get('green_path') or []
        if not green:
            validation = validate_ai_evidence_contract(contract)
            missing = list(validation.get('missing_components') or [])
            suffix = f" Missing components: {missing}." if missing else ''
            return 'Green-path evidence unavailable for this run because the exact published central path, current price, or valid bounds are not all available.' + suffix
        row = green[0]
        return (
            f"The green line is lower than the main path because shrinkage pulls the session-adjusted central path back toward the current price. "
            f"Current price={row.get('Current Price')}; base central={row.get('Base Central Path')}; session-adjusted={row.get('Session-Adjusted Path')}; "
            f"green={row.get('Green Less-Risky Path')}; path trust={row.get('Path Trust')}; tier={row.get('Green Tier')}; reason codes={row.get('Reason Codes')}."
        )
    if parsed.intent == 'session':
        evidence = _m(contract.get('field2_settled_evidence'))
        stats = evidence.get('stats') if isinstance(evidence.get('stats'), pd.DataFrame) else pd.DataFrame()
        if stats.empty:
            return 'No settled session performance evidence is available yet, so no best session is claimed.'
        rows = []
        for _, r in stats.sort_values(['direction_accuracy', 'sample_count'], ascending=[False, False]).iterrows():
            rows.append(f"{r['session']}: n={int(r['sample_count'])}, direction_accuracy={float(r['direction_accuracy']):.3f}, coverage={float(r['interval_coverage']):.3f}")
        return 'Settled session comparison:\n' + '\n'.join(rows[:5])
    if parsed.intent == 'current_decision':
        return f"Current decision: {contract.get('current_decision')}\nLess-risky decision: {contract.get('less_risky_decision')}\nRun ID: {identity.get('run_id')}"
    if parsed.intent == 'regime':
        return f"Regime evidence: {contract.get('regime_standards')}"
    if parsed.intent == 'reliability_uncertainty':
        return f"Reliability: {contract.get('reliability')}\nUncertainty: {contract.get('uncertainty')}"
    if parsed.intent == 'history':
        return f"Field 1 history rows available: {len(contract.get('field1_history') or [])}\nMost recent sample: {(contract.get('field1_history') or ['UNAVAILABLE'])[0]}"
    if parsed.intent == 'reversal':
        return f"Minimum reversal conditions: {contract.get('reversal_conditions')}"
    if parsed.intent == 'model_comparison':
        return f"Field 7 evidence: {contract.get('field7_drift_cpa_evidence')}\nField 8 evidence: {contract.get('field8_calibration_spa_evidence')}"
    if parsed.intent == 'system_health':
        validation = validate_ai_evidence_contract(contract)
        valid = bool(validation.get("ready"))
        missing = list(validation.get("missing_components") or [])
        return f"System health: {'READY' if valid else 'NOT READY'}\nMissing components: {missing or 'NONE'}\nIdentity: {identity}\nBroker candle: {session.get('broker_candle_time')}"
    return 'General answer — not canonical market evidence. This assistant supports the saved loaded-symbol Field 10/Field 12 system evidence domain.'


def answer_canonical_question(question: str, state: MutableMapping[str, Any]) -> dict[str, Any]:
    contract = build_ai_evidence_contract(state)
    validation = validate_ai_evidence_contract(contract)
    valid = bool(validation.get("ready"))
    missing = list(validation.get("missing_components") or [])
    parsed = _parse(question)
    answer = _answer(parsed, contract)
    if parsed.intent == 'general_system_question':
        answer = 'This AI assistant answers only from saved canonical evidence. Ask for the best symbol now (Field 10), selected-symbol entry, Field 12 fundamental news, TP/SL, horizon, regime, reliability, history, reversal, model comparison, or system health.'
    evidence = _evidence_rows(contract, parsed)
    evidence_hash = sha256(json.dumps({'contract': contract.get('identity'), 'intent': parsed.intent, 'question': question}, sort_keys=True, default=str).encode('utf-8')).hexdigest()
    return {
        'answer': answer,
        'status': 'ANSWER' if parsed.intent != 'general_system_question' else 'GENERAL',
        'intent': parsed.intent,
        'run_id': _m(contract.get('identity')).get('run_id') or 'UNAVAILABLE',
        'normalized_query': _normalize(question),
        'evidence': contract,
        'evidence_used': evidence,
        'evidence_hash': evidence_hash,
        'full_recalculation_performed': False,
        'ready': valid,
        'missing_components': missing,
        'parsed': parsed.__dict__,
    }


# Backward-compatible helpers.
def normalize_query(question: str) -> str:
    return _normalize(question)


def detect_intent(question: str) -> str:
    return _parse(question).intent


def build_intent_evidence(question: str, state: Mapping[str, Any]) -> dict[str, Any]:
    parsed = _parse(question)
    return {'intent': parsed.intent, 'query': _normalize(question), 'evidence': build_ai_evidence_contract(state)}


__all__ = [
    'INTENTS', 'normalize_query', 'detect_intent', 'build_intent_evidence',
    'build_ai_evidence_contract', 'validate_ai_evidence_contract', 'answer_canonical_question'
]
