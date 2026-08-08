"""Lightweight EURUSD news normalization, relevance, deduplication and summary.

This module is calculation-only.  It never changes the central trading regime
or BUY/SELL/WAIT decision; it produces additional NLP evidence for Research.
"""
from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True)
class NLPConfig:
    duplicate_threshold: float = 0.90
    related_threshold: float = 0.75
    buy_threshold: float = 18.0
    sell_threshold: float = -18.0
    minimum_pair_relevance: float = 20.0
    max_features: int = 12000
    ngram_min: int = 1
    ngram_max: int = 2
    general_decay_hours: float = 18.0
    macro_decay_hours: float = 36.0
    central_bank_decay_hours: float = 72.0
    commentary_decay_hours: float = 10.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


EUR_TERMS = {
    "eur": 24, "euro": 20, "ecb": 30, "european central bank": 34,
    "eurozone": 25, "germany": 13, "france": 10, "european commission": 16,
    "european inflation": 25, "european gdp": 22, "european pmi": 22,
    "lagarde": 24, "bund": 12,
}
USD_TERMS = {
    "usd": 24, "dollar": 18, "federal reserve": 32, "fed": 25, "fomc": 30,
    "powell": 25, "united states": 14, "u.s.": 14, "us treasury": 20,
    "treasury yields": 23, "cpi": 24, "pce": 24, "nfp": 28,
    "nonfarm payrolls": 30, "unemployment": 18, "gdp": 15,
    "retail sales": 20, "ism": 22, "interest rates": 18,
}
RISK_TERMS = {
    "banking crisis": 28, "geopolitical": 22, "conflict": 14, "war": 22,
    "oil": 12, "energy": 12, "risk appetite": 18, "safe haven": 22,
    "bonds": 10, "yield": 13, "credit risk": 18, "recession": 22,
    "crisis": 24, "shock": 20,
}
EVENT_KEYWORDS = {
    "CENTRAL_BANK": ("ecb", "fed", "fomc", "central bank", "powell", "lagarde", "rate decision", "interest rate"),
    "INFLATION": ("inflation", "cpi", "pce", "consumer price", "core prices"),
    "EMPLOYMENT": ("nfp", "nonfarm", "payroll", "unemployment", "jobs", "employment"),
    "GROWTH": ("gdp", "pmi", "retail sales", "ism", "growth", "recession"),
    "BANKING": ("banking", "credit risk", "liquidity", "bank failure", "stress test"),
    "GEOPOLITICAL": ("war", "conflict", "sanction", "geopolitical", "missile", "ceasefire"),
    "ENERGY": ("oil", "gas", "energy", "opec"),
    "RISK_SENTIMENT": ("risk appetite", "safe haven", "equities", "stocks", "bonds", "treasury yields"),
}
POSITIVE_TERMS = {
    "strong", "accelerate", "growth", "beat", "higher", "hawkish", "raise", "hike",
    "improve", "surge", "gain", "resilient", "expansion", "optimistic", "cooling inflation",
}
NEGATIVE_TERMS = {
    "weak", "slowdown", "miss", "lower", "dovish", "cut", "decline", "fall",
    "recession", "crisis", "risk", "contract", "unemployment rises", "hot inflation",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has", "have",
    "in", "is", "it", "its", "of", "on", "or", "that", "the", "to", "was", "were",
    "will", "with", "this", "after", "before", "about", "into", "over", "under",
}


def safe_text(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(text: Any) -> Dict[str, Any]:
    original = safe_text(text)
    display = unicodedata.normalize("NFKC", html.unescape(original))
    display = re.sub(r"<[^>]+>", " ", display)
    display = re.sub(r"https?://\S+|www\.\S+", " [URL] ", display, flags=re.I)
    display = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", " [EMAIL] ", display)
    display = re.sub(r"\s+", " ", display).strip()
    lower = display.lower()
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+|\n+", display) if x.strip()]
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]{1,}|\b(?:EUR|USD)\b", lower)
    clean_tokens = [simple_lemma(t) for t in tokens if t not in STOPWORDS and len(t) > 1]
    return {
        "original_text": original,
        "display_text": display,
        "model_text": " ".join(clean_tokens),
        "sentences": sentences,
        "tokens": tokens,
        "clean_tokens": clean_tokens,
    }


def simple_lemma(token: str) -> str:
    t = token.lower().strip("'\"")
    for suffix, replacement in (("ies", "y"), ("sses", "ss"), ("ing", ""), ("ed", ""), ("s", "")):
        if len(t) > len(suffix) + 3 and t.endswith(suffix):
            return t[: -len(suffix)] + replacement
    return t


def _term_score(text: str, mapping: Dict[str, int]) -> Tuple[float, List[str]]:
    found: List[str] = []
    score = 0.0
    for term, weight in mapping.items():
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, flags=re.I):
            found.append(term)
            score += weight
    return min(100.0, score), found


def detect_entities_and_relevance(text: str) -> Dict[str, Any]:
    lower = safe_text(text).lower()
    eur, eur_entities = _term_score(lower, EUR_TERMS)
    usd, usd_entities = _term_score(lower, USD_TERMS)
    risk, risk_entities = _term_score(lower, RISK_TERMS)
    entity_score = min(100.0, eur * 0.55 + usd * 0.55 + risk * 0.35)
    pair_score = min(100.0, max(eur, usd) * 0.55 + min(eur, usd) * 0.35 + risk * 0.20)
    if "eurusd" in lower or "eur/usd" in lower or "euro dollar" in lower:
        pair_score = max(pair_score, 92.0)
    currency_score = min(100.0, max(eur, usd) + min(eur, usd) * 0.25)
    return {
        "currency_relevance_score": round(currency_score, 2),
        "entity_relevance_score": round(entity_score, 2),
        "eur_relevance_score": round(eur, 2),
        "usd_relevance_score": round(usd, 2),
        "eurusd_pair_relevance": round(pair_score, 2),
        "entities": sorted(set(eur_entities + usd_entities + risk_entities)),
        "eur_entities": eur_entities,
        "usd_entities": usd_entities,
        "risk_entities": risk_entities,
    }


def classify_event_type(text: str) -> Tuple[str, float]:
    lower = safe_text(text).lower()
    scores: Dict[str, float] = {}
    for label, words in EVENT_KEYWORDS.items():
        scores[label] = sum(1.0 for w in words if w in lower)
    best = max(scores, key=scores.get) if scores else "OTHER"
    top = scores.get(best, 0.0)
    if top <= 0:
        return "OTHER", 35.0
    importance = min(100.0, 45.0 + top * 15.0)
    return best, importance


def lightweight_sentiment(text: str) -> Dict[str, Any]:
    lower = safe_text(text).lower()
    pos = sum(1 for x in POSITIVE_TERMS if x in lower)
    neg = sum(1 for x in NEGATIVE_TERMS if x in lower)
    total = max(1, pos + neg)
    raw = (pos - neg) / total
    label = "POSITIVE" if raw > 0.12 else "NEGATIVE" if raw < -0.12 else "NEUTRAL"
    confidence = min(0.92, 0.50 + abs(raw) * 0.42)
    positive = max(0.0, raw)
    negative = max(0.0, -raw)
    neutral = max(0.0, 1.0 - positive - negative)
    norm = max(1e-9, positive + negative + neutral)
    return {
        "sentiment_label": label,
        "sentiment_score": round(float(raw), 4),
        "sentiment_positive_probability": round(positive / norm, 4),
        "sentiment_negative_probability": round(negative / norm, 4),
        "sentiment_neutral_probability": round(neutral / norm, 4),
        "sentiment_confidence": round(confidence, 4),
        "sentiment_model": "lightweight-lexicon-fallback",
    }


def parse_timestamp(value: Any) -> pd.Timestamp:
    try:
        if isinstance(value, (int, float)) and float(value) > 100000:
            ts = pd.to_datetime(float(value), unit="s", utc=True)
        else:
            ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return pd.NaT
        return ts
    except Exception:
        return pd.NaT


def recency_weight(timestamp: Any, event_type: str, config: NLPConfig, now: Any = None) -> Tuple[float, float]:
    ts = parse_timestamp(timestamp)
    current = pd.Timestamp.now(tz="UTC") if now is None else parse_timestamp(now)
    if pd.isna(ts) or pd.isna(current):
        return 0.35, float("nan")
    age_hours = max(0.0, float((current - ts).total_seconds() / 3600.0))
    if event_type == "CENTRAL_BANK":
        decay = config.central_bank_decay_hours
    elif event_type in {"INFLATION", "EMPLOYMENT", "GROWTH"}:
        decay = config.macro_decay_hours
    elif event_type == "OTHER":
        decay = config.commentary_decay_hours
    else:
        decay = config.general_decay_hours
    return float(math.exp(-age_hours / max(1.0, decay))), age_hours


def stable_hash(text: str) -> str:
    return hashlib.sha256(safe_text(text).encode("utf-8", errors="ignore")).hexdigest()


def normalize_articles(articles: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for i, article in enumerate(articles or []):
        if not isinstance(article, dict):
            continue
        title = safe_text(article.get("headline") or article.get("title"))
        body = safe_text(article.get("summary") or article.get("text") or article.get("description"))
        combined = f"{title}. {body}".strip(". ")
        norm = normalize_text(combined)
        relevance = detect_entities_and_relevance(norm["display_text"])
        event_type, importance = classify_event_type(norm["display_text"])
        sentiment = lightweight_sentiment(norm["display_text"])
        ts = parse_timestamp(
            article.get("datetime") or article.get("timestamp") or article.get("time")
            or article.get("published_at") or article.get("publishedDate") or article.get("published_date")
        )
        rows.append({
            "row_id": i,
            "title": title,
            "source": safe_text(article.get("source") or "Unknown"),
            "url": safe_text(article.get("url")),
            "timestamp": ts,
            "original_text": combined,
            "display_text": norm["display_text"],
            "model_text": norm["model_text"],
            "sentences": norm["sentences"],
            "article_hash": stable_hash(norm["model_text"]),
            "title_hash": stable_hash(normalize_text(title)["model_text"]),
            "event_type": event_type,
            "event_importance": importance,
            **relevance,
            **sentiment,
        })
    return pd.DataFrame(rows)


def deduplicate_articles(df: pd.DataFrame, config: NLPConfig = NLPConfig()) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame() if not isinstance(df, pd.DataFrame) else df.copy()
    out = df.copy().reset_index(drop=True)
    out["duplicate_status"] = "NEW"
    out["duplicate_group_id"] = ""
    out["duplicate_count"] = 1
    out["similarity_to_previous"] = 0.0
    out["novelty_score"] = 100.0
    texts = out["model_text"].fillna("").astype(str).tolist()
    # Exact normalized hash first.
    groups: Dict[str, List[int]] = {}
    for i, h in enumerate(out["article_hash"].astype(str)):
        groups.setdefault(h, []).append(i)
    for h, idxs in groups.items():
        if len(idxs) > 1:
            newest = max(idxs, key=lambda j: out.loc[j, "timestamp"] if pd.notna(out.loc[j, "timestamp"]) else pd.Timestamp.min.tz_localize("UTC"))
            gid = h[:12]
            for j in idxs:
                out.loc[j, "duplicate_group_id"] = gid
                out.loc[j, "duplicate_count"] = len(idxs)
                if j != newest:
                    out.loc[j, "duplicate_status"] = "DUPLICATE"
                    out.loc[j, "similarity_to_previous"] = 1.0
                    out.loc[j, "novelty_score"] = 0.0
    # Compare newest-to-oldest so the newest source record is always kept.
    nonempty = [i for i, t in enumerate(texts) if t.strip()]
    nonempty.sort(
        key=lambda i: out.loc[i, "timestamp"] if pd.notna(out.loc[i, "timestamp"]) else pd.Timestamp.min.tz_localize("UTC"),
        reverse=True,
    )
    if len(nonempty) >= 2:
        try:
            vec = TfidfVectorizer(ngram_range=(config.ngram_min, config.ngram_max), max_features=config.max_features, min_df=1, sublinear_tf=True)
            matrix = vec.fit_transform([texts[i] for i in nonempty])
            sim = cosine_similarity(matrix)
            for local_i in range(len(nonempty)):
                i = nonempty[local_i]
                if out.loc[i, "duplicate_status"] == "DUPLICATE":
                    continue
                best_score = 0.0
                best_j = None
                for local_j in range(local_i):
                    j = nonempty[local_j]
                    score = float(sim[local_i, local_j])
                    if score > best_score:
                        best_score, best_j = score, j
                out.loc[i, "similarity_to_previous"] = round(best_score, 4)
                out.loc[i, "novelty_score"] = round(max(0.0, 100.0 * (1.0 - best_score)), 2)
                if best_j is not None and best_score >= config.duplicate_threshold:
                    out.loc[i, "duplicate_status"] = "DUPLICATE"
                    gid = out.loc[best_j, "duplicate_group_id"] or stable_hash(texts[best_j])[:12]
                    out.loc[i, "duplicate_group_id"] = gid
                elif best_j is not None and best_score >= config.related_threshold:
                    out.loc[i, "duplicate_status"] = "RELATED_UPDATE"
                    out.loc[i, "duplicate_group_id"] = out.loc[best_j, "duplicate_group_id"] or stable_hash(texts[best_j])[:12]
        except Exception:
            pass
    # Recompute group counts without multiplying impact.
    for gid, group in out[out["duplicate_group_id"].astype(bool)].groupby("duplicate_group_id"):
        out.loc[group.index, "duplicate_count"] = int(len(group))
    return out


def extractive_summary(text: str, *, max_sentences: int = 3) -> Dict[str, Any]:
    norm = normalize_text(text)
    sentences = norm["sentences"]
    if not sentences:
        return {"extractive_summary": "", "important_sentences": [], "summary_entities": [], "summary_event": "OTHER", "summary_market_effect": "WAIT"}
    relevance = detect_entities_and_relevance(norm["display_text"])
    event, _ = classify_event_type(norm["display_text"])
    try:
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=3000)
        matrix = vec.fit_transform(sentences)
        tfidf = np.asarray(matrix.sum(axis=1)).reshape(-1)
    except Exception:
        tfidf = np.ones(len(sentences))
    scored: List[Tuple[float, int, str]] = []
    seen: set[str] = set()
    for i, sentence in enumerate(sentences):
        key = normalize_text(sentence)["model_text"]
        repetition_penalty = 0.55 if key in seen else 1.0
        seen.add(key)
        ent = detect_entities_and_relevance(sentence)
        position = 1.0 if i == 0 else max(0.45, 0.85 - i * 0.05)
        keyword = 1.15 if classify_event_type(sentence)[0] != "OTHER" else 1.0
        score = float(tfidf[i]) * (1.0 + ent["eurusd_pair_relevance"] / 100.0) * position * keyword * repetition_penalty
        scored.append((score, i, sentence))
    chosen = sorted(sorted(scored, reverse=True)[: max(1, max_sentences)], key=lambda x: x[1])
    selected = [x[2] for x in chosen]
    sentiment = lightweight_sentiment(" ".join(selected))
    # Relative currency effect: positive EUR / negative USD supports EURUSD;
    # positive USD / negative EUR pressures EURUSD. Mixed evidence stays WAIT.
    balance = (float(relevance["eur_relevance_score"]) - float(relevance["usd_relevance_score"])) / 100.0
    relative_effect = float(sentiment["sentiment_score"]) * balance
    effect = "BUY" if relative_effect > 0.10 else "SELL" if relative_effect < -0.10 else "WAIT"
    return {
        "extractive_summary": " ".join(selected),
        "important_sentences": selected,
        "summary_entities": relevance["entities"],
        "summary_event": event,
        "summary_market_effect": effect,
    }


def map_market_direction(row: Dict[str, Any], config: NLPConfig = NLPConfig(), source_reliability: float = 70.0) -> Dict[str, Any]:
    sentiment = float(row.get("sentiment_score", 0.0) or 0.0)
    eur = float(row.get("eur_relevance_score", 0.0) or 0.0)
    usd = float(row.get("usd_relevance_score", 0.0) or 0.0)
    pair = float(row.get("eurusd_pair_relevance", 0.0) or 0.0)
    importance = float(row.get("event_importance", 35.0) or 35.0)
    novelty = float(row.get("novelty_score", 100.0) or 0.0) / 100.0
    recency, age_hours = recency_weight(row.get("timestamp"), str(row.get("event_type", "OTHER")), config)
    # Positive EUR is bullish EURUSD; positive USD is bearish EURUSD.
    currency_balance = (eur - usd) / 100.0
    if abs(currency_balance) < 0.08 and max(eur, usd) > 0:
        currency_balance = 0.12 if eur > usd else -0.12 if usd > eur else 0.0
    raw = sentiment * currency_balance
    score = raw * pair * (importance / 100.0) * recency * max(0.05, novelty) * (source_reliability / 100.0)
    score = float(max(-100.0, min(100.0, score)))
    if pair < config.minimum_pair_relevance or row.get("duplicate_status") == "DUPLICATE":
        direction = "WAIT"
    elif score >= config.buy_threshold:
        direction = "BUY"
    elif score <= config.sell_threshold:
        direction = "SELL"
    else:
        direction = "WAIT"
    buy = max(0.0, score)
    sell = max(0.0, -score)
    wait = max(0.0, 100.0 - min(100.0, abs(score) * 1.8))
    total = max(1.0, buy + sell + wait)
    return {
        "nlp_direction": direction,
        "nlp_direction_score": round(score, 2),
        "nlp_buy_pressure": round(100.0 * buy / total, 2),
        "nlp_sell_pressure": round(100.0 * sell / total, 2),
        "nlp_wait_pressure": round(100.0 * wait / total, 2),
        "nlp_event_importance": round(importance, 2),
        "nlp_pair_relevance": round(pair, 2),
        "nlp_recency_weight": round(recency, 4),
        "nlp_age_hours": round(age_hours, 2) if math.isfinite(age_hours) else None,
        "nlp_novelty": round(novelty * 100.0, 2),
        "nlp_source_reliability": round(source_reliability, 2),
    }


def build_article_intelligence(articles: Sequence[Dict[str, Any]], config: NLPConfig = NLPConfig()) -> pd.DataFrame:
    df = deduplicate_articles(normalize_articles(articles), config)
    if df.empty:
        return df
    mapped: List[Dict[str, Any]] = []
    for _, row in df.iterrows():
        data = row.to_dict()
        data.update(map_market_direction(data, config))
        data.update(extractive_summary(data.get("display_text", "")))
        mapped.append(data)
    out = pd.DataFrame(mapped)
    if "timestamp" in out.columns:
        out = out.sort_values("timestamp", ascending=False, na_position="last").reset_index(drop=True)
    return out
