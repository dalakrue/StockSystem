"""Local EUR/USD sentiment engine with currency-aware direction mapping."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import hashlib
import math
import re

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except Exception:  # pragma: no cover
    SentimentIntensityAnalyzer = None  # type: ignore

EUR_TERMS = {
    "eur", "euro", "eurozone", "ecb", "lagarde", "eurostat", "european central bank",
    "european inflation", "european growth", "european employment", "bund yield",
}
USD_TERMS = {
    "usd", "dollar", "federal reserve", "fed", "fomc", "powell", "cpi", "pce", "nfp",
    "nonfarm payroll", "unemployment", "jobless claims", "treasury yield", "ism", "gdp",
    "retail sales", "financial stress", "dxy",
}
PAIR_TERMS = {"eurusd", "eur usd", "euro dollar", "ecb versus fed", "rate differential", "yield spread"}
HAWKISH = {"hawkish", "rate hike", "higher for longer", "tightening", "inflation persistent", "raise rates"}
DOVISH = {"dovish", "rate cut", "easing", "lower rates", "disinflation", "pause tightening"}
POSITIVE = {"strong", "surge", "accelerate", "beat", "improve", "growth", "resilient", "hotter"}
NEGATIVE = {"weak", "decline", "miss", "contract", "recession", "slump", "cooling", "stress"}


def _contains(text: str, terms: set[str]) -> float:
    hits = sum(1 for term in terms if term in text)
    return min(100.0, hits * 25.0)


def _freshness(published_at: Any, half_life_hours: float = 36.0) -> float:
    try:
        parsed = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 3600)
        return 100.0 * math.exp(-math.log(2) * age / half_life_hours)
    except Exception:
        return 35.0


def _vader(text: str) -> float:
    if SentimentIntensityAnalyzer is None:
        pos = sum(term in text for term in POSITIVE)
        neg = sum(term in text for term in NEGATIVE)
        return max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg)))
    return float(SentimentIntensityAnalyzer().polarity_scores(text).get("compound", 0.0))


def _event_type(text: str) -> tuple[str, float]:
    categories = (
        ("CENTRAL_BANK", {"ecb", "fomc", "federal reserve", "rate hike", "rate cut"}, 100),
        ("INFLATION", {"cpi", "pce", "inflation"}, 95),
        ("LABOR", {"nfp", "payroll", "unemployment", "jobless claims"}, 90),
        ("GROWTH", {"gdp", "ism", "retail sales", "growth", "recession"}, 75),
        ("YIELDS", {"treasury yield", "bund yield", "yield spread", "rate differential"}, 85),
        ("POLITICAL_RISK", {"election", "sanction", "war", "political risk"}, 70),
    )
    for category, terms, importance in categories:
        if any(term in text for term in terms):
            return category, float(importance)
    return "OTHER", 35.0


def score_article(item: Mapping[str, Any]) -> dict[str, Any]:
    title = str(item.get("title") or item.get("headline") or "")
    description = str(item.get("description") or item.get("summary") or "")
    text = " ".join(re.sub(r"\s+", " ", f"{title} {description}".lower()).split())
    eur_rel = max(float(item.get("eur_relevance") or 0), _contains(text, EUR_TERMS))
    usd_rel = max(float(item.get("usd_relevance") or 0), _contains(text, USD_TERMS))
    pair_rel = max(float(item.get("eurusd_relevance") or 0), _contains(text, PAIR_TERMS), min(100.0, 0.65 * eur_rel + 0.65 * usd_rel))
    lexical = _vader(text)
    hawkish = sum(term in text for term in HAWKISH)
    dovish = sum(term in text for term in DOVISH)
    policy_tone = max(-1.0, min(1.0, (hawkish - dovish) / max(1, hawkish + dovish)))
    eur_score = 0.0
    usd_score = 0.0
    if eur_rel:
        eur_score = 100.0 * (0.55 * lexical + 0.45 * policy_tone)
    if usd_rel:
        usd_score = 100.0 * (0.55 * lexical + 0.45 * policy_tone)
    # Currency-aware conversion: positive EUR helps EURUSD; positive USD hurts it.
    pair_direction = (eur_score * eur_rel / 100.0) - (usd_score * usd_rel / 100.0)
    pair_direction = max(-100.0, min(100.0, pair_direction))
    event_type, importance = _event_type(text)
    freshness = _freshness(item.get("published_at"))
    source_quality = float(item.get("source_quality") or 55.0)
    relevance = max(pair_rel, eur_rel, usd_rel)
    reliability = max(0.0, min(100.0, 0.30 * source_quality + 0.25 * relevance + 0.25 * freshness + 0.20 * importance))
    uncertainty = max(0.0, min(100.0, 100.0 - reliability + 20.0 * (1.0 - abs(lexical))))
    return {
        **dict(item),
        "eur_relevance": eur_rel, "usd_relevance": usd_rel, "eurusd_relevance": pair_rel,
        "event_type": event_type, "event_importance": importance, "vader_result": lexical,
        "eur_sentiment_score": eur_score, "usd_sentiment_score": usd_score,
        "pair_direction_implication": pair_direction, "freshness_score": freshness,
        "uncertainty": uncertainty, "reliability": reliability,
    }


def aggregate(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    scored = [score_article(item) for item in items]
    relevant = [row for row in scored if max(row["eur_relevance"], row["usd_relevance"], row["eurusd_relevance"]) > 0]
    if not relevant:
        return {
            "eur_sentiment_score": None, "usd_sentiment_score": None,
            "eurusd_net_directional_score": None, "sentiment_strength": None,
            "sentiment_uncertainty": 100.0, "event_risk": None,
            "sentiment_reliability": 0.0, "article_count": 0,
            "status": "INSUFFICIENT", "articles": scored,
        }
    weights = [max(0.001, row["reliability"] * row["freshness_score"] * max(row["eurusd_relevance"], 20) / 1_000_000) for row in relevant]
    total = sum(weights)
    weighted = lambda key: sum(row[key] * weight for row, weight in zip(relevant, weights)) / total
    eur = weighted("eur_sentiment_score")
    usd = weighted("usd_sentiment_score")
    net = weighted("pair_direction_implication")
    disagreement = sum(abs(row["pair_direction_implication"] - net) * weight for row, weight in zip(relevant, weights)) / total
    contradiction = min(100.0, disagreement)
    reliability = max(0.0, min(100.0, weighted("reliability") - 0.35 * contradiction))
    return {
        "eur_sentiment_score": eur,
        "usd_sentiment_score": usd,
        "eurusd_net_directional_score": net,
        "sentiment_strength": abs(net),
        "sentiment_uncertainty": max(weighted("uncertainty"), contradiction),
        "event_risk": weighted("event_importance"),
        "sentiment_reliability": reliability,
        "contradiction_score": contradiction,
        "article_count": len(relevant),
        "status": "VALID",
        "articles": scored,
        "dataset_hash": hashlib.sha256("|".join(sorted(str(row.get("article_id") or row.get("title_hash") or "") for row in relevant)).encode()).hexdigest(),
    }


__all__ = ["score_article", "aggregate"]
