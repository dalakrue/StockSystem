"""Lightweight eight-card summary for Lunch and Dinner.

The renderer only reads the compact projection of an already-published canonical
result.  It contains no trading calculations, database scans, charts, or
per-value Streamlit widgets.
"""
from __future__ import annotations

from html import escape
from typing import Any, Mapping

import streamlit as st

from core.compact_canonical_20260619 import get_compact_summary


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _v(value: Any, default: str = "-") -> str:
    if value in (None, ""):
        return default
    if isinstance(value, float):
        return f"{value:.5f}" if abs(value) < 10 else f"{value:.2f}"
    return str(value)


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:
        return "N/A"


def card_payload(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    d, s = _m(summary.get("decision")), _m(summary.get("scores"))
    r, p = _m(summary.get("regime")), _m(summary.get("projection"))
    pri, u = _m(summary.get("priority")), _m(summary.get("uncertainty"))
    n, val, ident = _m(summary.get("nlp")), _m(summary.get("validation")), _m(summary.get("identity"))
    return [
        {"title": "Decision", "items": [
            ("Current", d.get("current_decision")), ("Direction", d.get("direction")),
            ("Less-risky", d.get("less_risky_bias")), ("Tradeability", d.get("tradeability")),
            ("Timing", d.get("timing")), ("Risk", d.get("risk_label")),
        ]},
        {"title": "Protected Scores", "items": [
            ("Master", _v(s.get("master"), "0") + "/10"), ("Entry", _v(s.get("entry"), "0") + "/10"),
            ("Hold", _v(s.get("hold"), "0") + "/10"), ("TP", _v(s.get("tp"), "0") + "/10"),
            ("Exit Risk", _v(s.get("exit_risk"), "0") + "/10"),
            ("Trend Capacity", _v(s.get("trend_capacity_remaining"), "0") + "/10"),
        ]},
        {"title": "Regime", "items": [
            ("Directional", r.get("directional_regime")), ("Volatility", r.get("volatility_regime")),
            ("Reliability", _pct(r.get("regime_reliability"))), ("Alpha", r.get("alpha")),
            ("Delta", r.get("delta")), ("Transition Risk", _pct(r.get("transition_risk"))),
            ("Transition Window", r.get("estimated_transition_window")),
        ]},
        {"title": "Projection", "items": [
            ("Confidence", _pct(p.get("projection_confidence"))), ("Path Agreement", _pct(p.get("path_agreement"))),
            ("Current", p.get("current_close")), ("H+1", p.get("h1")), ("H+3", p.get("h3")),
            ("H+6", p.get("h6")), ("Lower", p.get("lower_band")), ("Upper", p.get("upper_band")),
        ]},
        {"title": "Priority", "items": [
            ("KNN", pri.get("knn_priority")), ("Greedy", pri.get("greedy_priority")),
            ("Current Rank", pri.get("current_rank")), ("Best Hour", pri.get("best_entry_hour")),
            ("Second Hour", pri.get("second_best_entry_hour")), ("Quality", pri.get("opportunity_quality")),
        ]},
        {"title": "Uncertainty", "items": [
            ("Aleatoric", _pct(u.get("aleatoric"))), ("Epistemic", _pct(u.get("epistemic"))),
            ("Combined", _pct(u.get("combined"))), ("Main Source", u.get("main_source")),
            ("Calibration", u.get("calibration_status")), ("Sample Status", u.get("sample_size_status")),
        ]},
        {"title": "NLP & Event Risk", "items": [
            ("Direction", n.get("direction")), ("Reliability", _pct(n.get("reliability"))),
            ("Conflict", n.get("conflict")), ("Top News", n.get("highest_ranked_news")),
            ("Impact", n.get("event_impact")), ("Event Risk", n.get("event_risk_condition")),
        ]},
        {"title": "Data & Validation", "items": [
            ("Calculation ID", summary.get("calculation_id")), ("Calculated", ident.get("calculation_timestamp")),
            ("Last H1", ident.get("latest_completed_candle_time")), ("Freshness", val.get("data_freshness")),
            ("Stale", val.get("stale_status")), ("Layers", val.get("layer_status")),
            ("Validation", val.get("validation_status")),
        ]},
    ]


def _html(cards: list[dict[str, Any]], location: str) -> str:
    blocks = []
    for card in cards:
        items = "".join(
            f'<div class="adx-kv"><span>{escape(str(k))}</span><b>{escape(_v(v))}</b></div>'
            for k, v in card["items"]
        )
        blocks.append(f'<section class="adx-summary-card"><h4>{escape(card["title"])}</h4>{items}</section>')
    return f"""
<style>
.adx-card-grid-{location}{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin:.35rem 0 .8rem}}
.adx-summary-card{{border:1px solid rgba(128,128,128,.28);border-radius:12px;padding:.68rem .75rem;background:rgba(128,128,128,.055);content-visibility:auto;contain-intrinsic-size:180px}}
.adx-summary-card h4{{margin:0 0 .42rem;font-size:.94rem}}
.adx-kv{{display:flex;justify-content:space-between;gap:.65rem;padding:.16rem 0;border-bottom:1px solid rgba(128,128,128,.10);font-size:.79rem;line-height:1.25}}
.adx-kv span{{opacity:.76;min-width:42%}} .adx-kv b{{text-align:right;overflow-wrap:anywhere;font-weight:650}}
@media(max-width:760px){{.adx-card-grid-{location}{{grid-template-columns:1fr}}.adx-summary-card{{box-shadow:none;backdrop-filter:none}}}}
</style><div class="adx-card-grid-{location}">{''.join(blocks)}</div>"""


def render_eight_cards(summary: Mapping[str, Any] | None = None, *, location: str = "summary") -> list[dict[str, Any]]:
    summary = dict(summary or get_compact_summary(st.session_state))
    if not summary:
        st.info("Run Calculation in Settings to publish the synchronized EURUSD H1 summary.")
        return []
    cards = card_payload(summary)
    st.markdown(_html(cards, location.replace(" ", "-").lower()), unsafe_allow_html=True)
    return cards


__all__ = ["card_payload", "render_eight_cards"]
