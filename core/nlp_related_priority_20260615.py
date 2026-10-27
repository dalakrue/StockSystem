"""Ten-day real-news ranking for the existing Research NLP workspace.

KNN/Greedy values are deterministic display-ranking evidence only.  They never
replace or reverse the protected Full Metric direction and no placeholder news
is generated to satisfy a row target.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd
import streamlit as st

from core.news_event_store_20260618 import deduplicate_articles, load_recent_articles, persist_articles

MAX_CACHED_ROWS = 2000
MARKET_WORDS = {
    "eur", "euro", "usd", "dollar", "ecb", "fed", "fomc", "inflation", "cpi", "ppi",
    "rates", "rate", "jobs", "payroll", "nfp", "gdp", "pmi", "powell", "lagarde",
    "yield", "yields", "tariff", "trade", "geopolitical", "risk", "currency", "forex",
}
BUY_WORDS = {"dovish", "cut", "cuts", "weak", "weaker", "decline", "falls", "euro", "ecb", "rebound", "support"}
SELL_WORDS = {"hawkish", "hike", "hikes", "strong", "stronger", "surge", "rises", "dollar", "fed", "pressure", "risk-off"}
PROTECT_WORDS = {"war", "conflict", "shock", "surprise", "emergency", "crisis", "tariff", "sanction", "volatile", "uncertainty"}


def _extract_news_rows(obj: Any, depth: int = 0) -> List[Dict[str, Any]]:
    if obj is None or depth > 5:
        return []
    if isinstance(obj, pd.DataFrame):
        return [dict(row) for row in obj.head(MAX_CACHED_ROWS).to_dict("records")]
    if isinstance(obj, list):
        return [dict(x) for x in obj[:MAX_CACHED_ROWS] if isinstance(x, Mapping)]
    if isinstance(obj, Mapping):
        rows: list[dict[str, Any]] = []
        if obj.get("headline") or obj.get("title") or obj.get("Title") or obj.get("Headline"):
            rows.append(dict(obj))
        for key in ("news_table", "table", "news", "rows", "articles", "event_response", "news_nlp", "nlp", "result", "data", "items"):
            if key in obj:
                rows.extend(_extract_news_rows(obj.get(key), depth + 1))
        return rows[:MAX_CACHED_ROWS]
    return []


def _timestamp(row: Mapping[str, Any]) -> pd.Timestamp:
    value = None
    for key in ("publication_time", "publishedDate", "published", "datetime", "timestamp", "Time", "Published", "Date"):
        if row.get(key) not in (None, ""):
            value = row.get(key); break
    try:
        if isinstance(value, (int, float)):
            unit = "ms" if abs(float(value)) > 10_000_000_000 else "s"
            ts = pd.to_datetime(value, unit=unit, utc=True, errors="coerce")
        else:
            ts = pd.to_datetime(value, utc=True, errors="coerce")
        return pd.Timestamp(ts) if not pd.isna(ts) else pd.NaT
    except Exception:
        return pd.NaT


def _row_text(row: Mapping[str, Any]) -> str:
    return " ".join(str(row.get(key) or "") for key in ("headline", "title", "Title", "summary", "description", "topic_name", "event_type"))


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z][a-z0-9-]{1,}", str(text).lower()))


def _float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def _canonical_direction() -> str:
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(st.session_state)
        final = canonical.get("final_decision") or {}
        value = str(final.get("directional_market_view") or canonical.get("full_metric_direction") or "WAIT").upper()
        return value if value in {"BUY", "SELL"} else "WAIT"
    except Exception:
        return "WAIT"


def collect_existing_news_rows(extra: Any = None, *, window_days: int = 10) -> List[Dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rows.extend(load_recent_articles(days=window_days, limit=MAX_CACHED_ROWS))
    rows.extend(_extract_news_rows(extra))
    for key in (
        "nlp_market_intelligence_result", "finnhub_news_cache", "nlp_related_news_priority_table_20260615",
        "dv_news_nlp_pack_20260612", "news_nlp_knn_greedy_pack_20260612", "research_pack_20260612",
        "final_synced_research_merge_pack_20260612", "final_merged_intelligence_pack_20260612",
        "related_news_rows", "news_rows", "nlp_ranked_news_df", "news_nlp_ranked_df",
        "news_nlp_table", "nlp_news_df", "latest_news_df",
    ):
        rows.extend(_extract_news_rows(st.session_state.get(key)))
    deduped = deduplicate_articles(rows)
    now = pd.Timestamp.now(tz="UTC")
    cutoff = now - pd.Timedelta(days=max(1, int(window_days)))
    valid = [row for row in deduped if (ts := _timestamp(row)) is not pd.NaT and pd.notna(ts) and cutoff <= ts <= now + pd.Timedelta(minutes=5)]
    valid.sort(key=lambda row: _timestamp(row).value, reverse=True)
    if valid:
        try:
            persist_articles(valid)
        except Exception:
            pass
    return valid[:MAX_CACHED_ROWS]


def _topic(row: Mapping[str, Any], tokens: set[str]) -> str:
    existing = str(row.get("topic_name") or row.get("event_type") or row.get("Topic") or "").strip()
    if existing:
        return existing
    if tokens & {"ecb", "fed", "fomc", "lagarde", "powell", "rates", "rate"}: return "CENTRAL BANK / RATES"
    if tokens & {"cpi", "ppi", "inflation"}: return "INFLATION"
    if tokens & {"nfp", "jobs", "payroll", "unemployment"}: return "LABOUR"
    if tokens & {"war", "sanction", "geopolitical", "tariff"}: return "GEOPOLITICAL / TRADE"
    return "MACRO / FX"


def _existing_or_unavailable(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        value = row.get(name)
        if value not in (None, "", "nan"):
            return value
    return "Unavailable"


def _score(row: Dict[str, Any], query: str, canonical_direction: str) -> Dict[str, Any]:
    text = _row_text(row)
    tokens = _tokens(text)
    query_tokens = _tokens(query)
    title = str(row.get("headline") or row.get("title") or row.get("Title") or "-")[:240]
    source = str(row.get("source") or row.get("Source") or "Unknown")[:100]
    published = _timestamp(row)
    now = pd.Timestamp.now(tz="UTC")
    age_hours = max(0.0, (now - published).total_seconds() / 3600.0) if pd.notna(published) else None

    relevance = _float(row.get("eurusd_pair_relevance"), -1)
    if relevance < 0:
        relevance = 100.0 * len(tokens & query_tokens) / max(1, len(query_tokens)) if query_tokens else 55.0 + min(35.0, len(tokens & MARKET_WORDS) * 6.0)
    importance = _float(row.get("importance_score", row.get("event_importance", row.get("Impact Score /100"))), 0)
    market_impact = max(importance, min(100.0, len(tokens & MARKET_WORDS) * 10.0 + abs(_float(row.get("eur_relevance_score")) - _float(row.get("usd_relevance_score"))) * 0.35))
    protect = min(100.0, len(tokens & PROTECT_WORDS) * 15.0 + (22.0 if "CONFLICT" in str(row.get("nlp_conflict_level", row.get("NLP Conflict", ""))).upper() else 0.0))
    freshness = 45.0 if age_hours is None else max(10.0, 100.0 - min(90.0, age_hours / max(1.0, 24.0 * 10.0) * 90.0))
    reliability = _float(row.get("nlp_reliability_score", row.get("source_reliability", row.get("Reliability %"))), 55.0)

    direction = str(row.get("nlp_direction") or row.get("news_direction") or row.get("Direction") or "").upper()
    if direction not in {"BUY", "SELL", "WAIT", "HOLD", "PROTECT"}:
        buy_pressure = len(tokens & BUY_WORDS) + max(0.0, _float(row.get("eur_relevance_score")) / 25.0)
        sell_pressure = len(tokens & SELL_WORDS) + max(0.0, _float(row.get("usd_relevance_score")) / 25.0)
        direction = "BUY" if buy_pressure > sell_pressure + 0.7 else "SELL" if sell_pressure > buy_pressure + 0.7 else "WAIT"
    directional_for_compare = direction if direction in {"BUY", "SELL"} else "WAIT"

    ideal = [100.0, 100.0, 85.0, 100.0, 90.0]
    vector = [relevance, market_impact, protect, freshness, reliability]
    distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(vector, ideal)))
    knn = max(0.0, 100.0 - distance / math.sqrt(5 * 100.0**2) * 100.0)
    greedy = relevance * 0.25 + market_impact * 0.30 + protect * 0.20 + freshness * 0.10 + reliability * 0.15
    final = knn * 0.52 + greedy * 0.48

    relationship = "NEUTRAL / WAIT"
    if canonical_direction in {"BUY", "SELL"} and directional_for_compare in {"BUY", "SELL"}:
        relationship = "SUPPORTS FULL METRIC" if canonical_direction == directional_for_compare else "CONFLICTS — PROTECT / WAIT"
    elif canonical_direction == "WAIT":
        relationship = "FULL METRIC WAIT — NEWS CANNOT CREATE TRADE"
    action = "PROTECT" if protect >= 70 or "CONFLICTS" in relationship else "WAIT" if direction == "WAIT" else direction
    impact_strength = "HIGH" if market_impact >= 70 else "MEDIUM" if market_impact >= 45 else "LOW"
    risk_level = "HIGH" if protect >= 70 else "MEDIUM" if protect >= 45 else "LOW"
    symbols = row.get("related_symbols") or row.get("symbols") or row.get("entities") or ["EURUSD"]
    if isinstance(symbols, str): symbols_text = symbols
    elif isinstance(symbols, Iterable): symbols_text = ", ".join(map(str, symbols))
    else: symbols_text = "EURUSD"
    sentiment = str(row.get("sentiment_label") or row.get("sentiment") or "NEUTRAL").upper()
    expected_1h = _existing_or_unavailable(row, "reaction_expectation_1h", "expected_1h_impact", "future_return_1h", "return_1h")
    expected_3h = _existing_or_unavailable(row, "reaction_expectation_3h", "expected_3h_impact", "future_return_3h", "return_3h")
    historical_sample = _existing_or_unavailable(row, "historical_sample_size", "sample_size")
    historical_accuracy = _existing_or_unavailable(row, "historical_accuracy", "historical_directional_accuracy")
    cache_freshness = "Unknown" if age_hours is None else (f"{age_hours/24:.1f} days old" if age_hours >= 24 else f"{age_hours:.1f} hours old")
    duplicate_identity = str(row.get("duplicate_identity") or row.get("article_id") or "")[:32]
    return {
        "Final Rank": 0,
        "Publication Time": published.strftime("%Y-%m-%d %H:%M UTC") if pd.notna(published) else "Invalid",
        "Source": source,
        "Headline": title,
        "Related Symbols": symbols_text or "EURUSD",
        "EURUSD Relevance": round(relevance, 2),
        "Topic": _topic(row, tokens),
        "Sentiment": sentiment,
        "Directional Impact": direction,
        "Impact Strength": impact_strength,
        "Risk Level": risk_level,
        "KNN Score": round(knn, 2),
        "Greedy Score": round(greedy, 2),
        "Final Score": round(final, 2),
        "Protection Action": action,
        "Expected 1H Impact": expected_1h,
        "Expected 3H Impact": expected_3h,
        "Historical Sample Size": historical_sample,
        "Historical Accuracy": historical_accuracy,
        "Duplicate Identity": duplicate_identity,
        "Cache Freshness": cache_freshness,
        "Relationship to Full Metric": relationship,
        "Final Confirmation Status": "CONFIRM" if relationship == "SUPPORTS FULL METRIC" else "CONFLICT / WAIT" if "CONFLICTS" in relationship else "NEUTRAL",
    }


@st.cache_data(ttl=300, show_spinner=False, max_entries=12)
def _cached_table(rows_json: str, query: str, top_n: int, canonical_direction: str) -> pd.DataFrame:
    try:
        rows = json.loads(rows_json)
    except Exception:
        rows = []
    scored = [_score(dict(row), query, canonical_direction) for row in rows if isinstance(row, Mapping)]
    if not scored:
        return pd.DataFrame(columns=[
            "Final Rank", "Publication Time", "Source", "Headline", "Related Symbols", "EURUSD Relevance",
            "Topic", "Sentiment", "Directional Impact", "Impact Strength", "Risk Level", "KNN Score",
            "Greedy Score", "Final Score", "Protection Action", "Expected 1H Impact", "Expected 3H Impact",
            "Historical Sample Size", "Historical Accuracy", "Duplicate Identity", "Cache Freshness",
            "Relationship to Full Metric", "Final Confirmation Status",
        ])
    frame = pd.DataFrame(scored).sort_values(
        ["Final Score", "KNN Score", "Greedy Score", "Publication Time"],
        ascending=[False, False, False, False], kind="stable",
    ).reset_index(drop=True)
    if int(top_n or 0) > 0:
        frame = frame.head(int(top_n)).copy()
    frame["Final Rank"] = range(1, len(frame) + 1)
    return frame


def render_related_news_priority_table(
    extra_rows: Any = None, *, query: str = "", top_n: int = 0,
    window_days: int = 10, title: str = "📰 Related News Priority — KNN + Greedy",
) -> pd.DataFrame:
    rows = collect_existing_news_rows(extra_rows, window_days=window_days)
    direction = _canonical_direction()
    frame = _cached_table(json.dumps(rows, ensure_ascii=False, default=str), str(query or ""), int(top_n or 0), direction)
    st.markdown(f"#### {title}")
    st.caption(
        f"Real, deduplicated articles from the latest {int(window_days)} days. Rank 1 is strongest. "
        "KNN/Greedy are supporting ranking evidence; Full Metric remains the direction authority."
    )
    if frame.empty:
        st.info(f"No valid real articles are stored in the latest {int(window_days)} days. No placeholder news was created.")
        return frame
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"{int(window_days)}-Day Real News", len(frame), "Target met" if len(frame) >= 10 else f"Only {len(frame)} genuine articles available")
    c2.metric("Rank 1 Impact", str(frame.iloc[0].get("Impact Strength", "-")))
    c3.metric("Canonical Direction", direction, "News cannot reverse it")
    c4.metric("Persisted", len(rows), "Survives reruns/tab switches")
    if len(frame) < 10:
        st.warning(f"Only {len(frame)} genuine, timestamp-valid, deduplicated articles are available in the ten-day window. The system reports the real count and does not fabricate rows.")
    st.dataframe(frame, use_container_width=True, hide_index=True, height=min(680, max(340, 36 * min(len(frame), 16) + 92)))
    st.session_state["nlp_related_news_priority_table_20260615"] = frame
    st.session_state["nlp_related_news_priority_window_days_20260617"] = int(window_days)
    return frame


__all__ = ["collect_existing_news_rows", "render_related_news_priority_table"]
