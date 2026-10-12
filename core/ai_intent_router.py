"""Deterministic narrow-intent router for read-only domain analysis."""
from __future__ import annotations
import re
from typing import Any

# Specific routes come first. Existing public intent names remain compatible.
INTENTS = {
    "market_time": ("broker time", "myanmar time", "latest candle", "completed h1", "current time", "what time", "time sync", "synchronization", "watermark", "fresh", "stale"),
    "regime_transition": ("regime transition", "transition probability", "transition trust", "next regime", "change point", "changepoint"),
    "alpha_delta": ("alpha delta", "regime alpha", "regime delta", "alpha", "delta"),
    "tp_sl_guidance": ("take profit", "stop loss", "tp/sl", "tp", "sl", "exit price", "price target"),
    "hold_guidance": ("should i hold", "keep holding", "hold safety", "hold score", "continue holding", "hold"),
    "exit_guidance": ("should i exit", "exit now", "close now", "close trade", "hold or exit", "take profit now"),
    "field7_research": ("field 7", "field7", "research layer", "research lab", "scientific edge", "promotion gate"),
    "field6_evidence": ("field 6", "field6", "decision evidence", "preparation field", "sentiment technical history"),
    "session_evidence": ("london session", "new york session", "ny session", "overlap session", "london/ny", "session evidence", "session"),
    "entry_guidance": ("should i buy", "should i sell", "buy now", "sell now", "enter now", "entry now", "open trade", "entry"),
    "forecast_validation": ("forecast validation", "forecast accuracy", "coverage calibration", "prediction outcome", "settled forecast", "model skill"),
    "price_forecast": ("predicted price", "future price", "price path", "power bi", "powerbi", "forecast", "projection", "band", "h+1", "h+6"),
    "execution_feasibility": ("execution cost", "transaction cost", "spread", "slippage", "feasibility", "cost to expected move"),
    "risk_position_sizing": ("position size", "lot size", "margin", "risk amount", "position", "lot", "sizing"),
    "priority_ranking": ("best hour", "priority", "rank", "knn", "greedy", "opportunity"),
    "regime_explanation": ("major regime", "regime", "trend state", "market regime"),
    "reliability_explanation": ("reliability", "confidence", "uncertainty", "calibration", "trust", "accuracy"),
    "similar_day": ("similar day", "historical match", "analogue", "pattern", "motif", "discord"),
    "agreement_analysis": ("sentiment technical agreement", "sentiment and technical", "agreement", "conflict between sentiment"),
    "sentiment_analysis": ("sentiment", "news direction", "research news"),
    "technical_analysis": ("technical analysis", "technical direction", "indicator", "rsi", "macd"),
    "data_quality": ("data quality", "missing data", "duplicate timestamp", "leakage", "future data"),
    "historical_comparison": ("last 25", "history", "historical", "compare", "previous"),
    "system_health": ("system health", "connector", "generation", "ready", "status", "error", "database", "cache"),
    "bias_analysis": ("directional bias", "market bias", "trading bias", "less risky bias", "bullish bias", "bearish bias", "regime bias", "bias"),
    "decision_explanation": ("current decision", "less risky", "decision", "buy", "sell", "wait", "why"),
}

SOURCE_MAP = {
    "market_time": ("identity", "validation", "connector", "history"),
    "regime_transition": ("regime", "reliability", "history", "similar_day"),
    "alpha_delta": ("regime", "history", "reliability"),
    "tp_sl_guidance": ("projection", "risk", "decision", "warnings"),
    "hold_guidance": ("decision", "risk", "scores", "reliability", "history", "warnings"),
    "exit_guidance": ("decision", "risk", "projection", "reliability", "scores", "warnings"),
    "field7_research": ("field7", "research", "validation", "history", "warnings"),
    "field6_evidence": ("field6", "history", "technical", "sentiment", "warnings"),
    "session_evidence": ("session", "history", "priority", "technical", "warnings"),
    "entry_guidance": ("decision", "scores", "regime", "reliability", "priority", "warnings"),
    "forecast_validation": ("projection", "validation", "history", "reliability"),
    "price_forecast": ("projection", "forecast", "reliability", "validation"),
    "execution_feasibility": ("risk", "execution", "projection", "validation"),
    "decision_explanation": ("decision", "scores", "regime", "reliability", "warnings"),
    "regime_explanation": ("regime", "reliability", "history", "similar_day"),
    "reliability_explanation": ("reliability", "uncertainty", "validation", "evidence"),
    "similar_day": ("similar_day", "history", "reliability"),
    "sentiment_analysis": ("sentiment", "evidence", "history"),
    "technical_analysis": ("technical", "scores", "priority", "history"),
    "agreement_analysis": ("sentiment", "technical", "decision", "warnings"),
    "data_quality": ("identity", "validation", "history", "warnings"),
    "historical_comparison": ("history", "decision", "regime", "evidence"),
    "priority_ranking": ("priority", "decision", "regime", "reliability"),
    "risk_position_sizing": ("risk", "decision", "scores", "warnings"),
    "system_health": ("identity", "validation", "connector", "evidence", "warnings"),
    "bias_analysis": ("decision", "regime", "priority", "projection", "technical", "reliability", "warnings"),
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+_/-]+", str(text or "").lower()))


def detect_intent(question: str) -> dict[str, Any]:
    q = str(question or "").strip().lower()
    tokens = _tokens(q)
    scored: list[tuple[int, int, str]] = []
    for order, (intent, phrases) in enumerate(INTENTS.items()):
        score = 0
        specificity = 0
        for phrase in phrases:
            phrase_l = phrase.lower()
            if " " in phrase_l or "/" in phrase_l or "+" in phrase_l:
                if phrase_l in q:
                    score += 6
                    specificity += len(phrase_l)
            elif phrase_l in tokens:
                score += 2
                specificity += len(phrase_l)
        scored.append((score, specificity - order, intent))
    score, _, intent = max(scored, default=(0, 0, "decision_explanation"))
    if score <= 0:
        intent = "decision_explanation"
    return {
        "intent": intent,
        "score": score,
        "required_sources": SOURCE_MAP[intent],
        "normalized_question": " ".join(q.split()),
    }


__all__ = ["detect_intent", "INTENTS", "SOURCE_MAP"]
