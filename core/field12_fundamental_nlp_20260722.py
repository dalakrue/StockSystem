"""Field 12 fundamental-only multi-symbol news/NLP authority.

The builder is called only after a Settings calculation publishes its canonical
news evidence. Renderers read the saved table and never fetch news or recalculate
on tab open.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from datetime import datetime, timezone
from typing import Any
import math

import pandas as pd

TABLE_KEY = "field12_fundamental_nlp_rank_20260722"
META_KEY = "field12_fundamental_nlp_meta_20260722"
CSV_KEY = "field12_fundamental_nlp_csv_20260722"
VERSION = "field12-fundamental-news-nlp-v1"


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("/", "").replace("_", "").replace(" ", "")


def _num(value: Any, default: float | None = 0.0) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except Exception:
        return default


def _clip(value: Any, lo: float = 0.0, hi: float = 1.0) -> float:
    number = _num(value, lo)
    return float(max(lo, min(hi, number if number is not None else lo)))


def _sentiment_bias(value: Any) -> tuple[str, float]:
    text = str(value or "").strip().upper()
    positive = ("POSITIVE", "BULL", "BUY", "UP", "HAWKISH FOR", "STRONG")
    negative = ("NEGATIVE", "BEAR", "SELL", "DOWN", "DOVISH FOR", "WEAK")
    if any(token in text for token in positive):
        return "BUY", 1.0
    if any(token in text for token in negative):
        return "SELL", 1.0
    return "WAIT", 0.0


def _news_source_frame(state: Mapping[str, Any]) -> pd.DataFrame:
    for key in ("field10_news_nlp_evidence_20260708", "field10_institutional_ranking_20260708"):
        value = state.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty and "Symbol" in value.columns:
            return value.copy()
    return pd.DataFrame()


def build_field12_fundamental_rank(
    state: MutableMapping[str, Any],
    status: Mapping[str, Any] | None = None,
    *,
    reason: str = "settings_publication",
) -> dict[str, Any]:
    """Publish a deterministic rank using recent symbol-related news only."""
    try:
        from core.canonical_symbol_selection_20260709 import available_symbols
        symbols = available_symbols(state, limit=24)
    except Exception:
        symbols = []
    news = _news_source_frame(state)
    if not symbols and not news.empty:
        symbols = list(dict.fromkeys(_norm(v) for v in news["Symbol"].tolist() if _norm(v)))
    identity = state.get("canonical_run_identity_20260708")
    identity = identity if isinstance(identity, Mapping) else {}
    parent_run_id = str(
        (status or {}).get("parent_run_id")
        or (status or {}).get("run_id")
        or identity.get("parent_run_id")
        or state.get("settings_last_run_id_20260617")
        or ""
    )
    timeframe = str(identity.get("timeframe") or state.get("selected_timeframe") or state.get("timeframe") or "H4").upper()
    snapshot_hash = str(identity.get("snapshot_hash") or "")
    now = datetime.now(timezone.utc).isoformat()

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        match = news.loc[news["Symbol"].astype(str).map(_norm).eq(symbol)] if not news.empty else pd.DataFrame()
        item = match.iloc[0].to_dict() if not match.empty else {}
        title = str(item.get("Latest News Title") or "NEWS_UNAVAILABLE").strip()
        sentiment = str(item.get("News Sentiment") or "UNAVAILABLE").strip().upper()
        relevance = _clip(item.get("News Relevance Score"), 0.0, 1.0)
        absorption = _clip(item.get("News Absorption Score"), 0.0, 1.0)
        freshness_raw = _num(item.get("News Freshness Minutes"), None)
        freshness_score = 0.0 if freshness_raw is None else _clip(1.0 - freshness_raw / (72.0 * 60.0))
        conflict_text = str(item.get("News Conflict Flag") or "").strip().upper()
        conflict = conflict_text in {"TRUE", "YES", "1", "CONFLICT", "HIGH", "BLOCK"} or "CONFLICT" in conflict_text
        missing_reason = str(item.get("NLP Missing Reason") or "").strip()
        evidence_missing = (
            not item
            or not title
            or title.upper() in {"NEWS_UNAVAILABLE", "UNAVAILABLE", "NONE", "NAN"}
            or bool(missing_reason and missing_reason.upper() not in {"NONE", "OK", "AVAILABLE"})
        )
        bias, sentiment_strength = _sentiment_bias(sentiment)
        impact_score = relevance * (0.55 + 0.45 * freshness_score)
        score = 100.0 * (
            0.45 * relevance
            + 0.25 * freshness_score
            + 0.20 * absorption
            + 0.10 * sentiment_strength
        ) - (20.0 if conflict else 0.0)
        if evidence_missing:
            score = -1.0
            bias = "WAIT"
        if conflict:
            bias = "WAIT"
            permission = "PROTECT_NEWS_CONFLICT"
        elif evidence_missing:
            permission = "BLOCK_NO_RECENT_SYMBOL_NEWS"
        elif relevance >= 0.55 and freshness_score >= 0.25 and bias in {"BUY", "SELL"}:
            permission = "FUNDAMENTAL_NEWS_CANDIDATE"
        else:
            permission = "WAIT_NEWS_NOT_STRONG_ENOUGH"
        rows.append({
            "Symbol": symbol,
            "Timeframe": timeframe,
            "Fundamental Bias": bias,
            "News Permission": permission,
            "Fundamental News Score": round(score, 4),
            "High-Impact Score": round(impact_score, 4),
            "News Relevance Score": round(relevance, 4),
            "News Freshness Minutes": freshness_raw if freshness_raw is not None else "UNAVAILABLE",
            "News Freshness Score": round(freshness_score, 4),
            "News Absorption Score": round(absorption, 4),
            "News Sentiment": sentiment,
            "News Conflict Flag": bool(conflict),
            "Latest High-Impact Symbol News": title,
            "Currency / Symbol Match": item.get("News Currency/Symbol Match", "UNAVAILABLE"),
            "NLP Evidence Source": item.get("NLP Evidence Source", "UNAVAILABLE"),
            "NLP Missing Reason": missing_reason or ("NO_MATCHING_RECENT_NEWS" if evidence_missing else ""),
            "Evidence Status": "NEWS_UNAVAILABLE" if evidence_missing else "RECENT_SYMBOL_NEWS_READY",
            "Technical Influence": "NONE — NEWS/NLP ONLY",
            "Parent Run ID": parent_run_id,
            "Snapshot Hash": snapshot_hash,
            "Published At UTC": now,
        })

    table = pd.DataFrame(rows)
    if not table.empty:
        table["__available"] = table["Evidence Status"].eq("RECENT_SYMBOL_NEWS_READY")
        table = table.sort_values(
            ["__available", "Fundamental News Score", "High-Impact Score", "Symbol"],
            ascending=[False, False, False, True],
            kind="mergesort",
        ).reset_index(drop=True)
        table["Fundamental Rank"] = range(1, len(table) + 1)
        cols = ["Fundamental Rank"] + [c for c in table.columns if c not in {"Fundamental Rank", "__available"}]
        table = table[cols]

    meta = {
        "version": VERSION,
        "ok": not table.empty,
        "status": "READY" if not table.empty else "NO_LOADED_SYMBOL_NEWS",
        "symbols": symbols,
        "rows": int(len(table)),
        "timeframe": timeframe,
        "parent_run_id": parent_run_id,
        "snapshot_hash": snapshot_hash,
        "reason": reason,
        "technical_influence": False,
        "news_nlp_only": True,
        "calculated_during_settings": True,
        "opening_field12_triggers_calculation": False,
        "published_at": now,
    }
    state[TABLE_KEY] = table
    state[META_KEY] = meta
    try:
        state[CSV_KEY] = table.to_csv(index=False).encode("utf-8")
    except Exception:
        state[CSV_KEY] = b""
    return meta


__all__ = ["TABLE_KEY", "META_KEY", "CSV_KEY", "VERSION", "build_field12_fundamental_rank"]
