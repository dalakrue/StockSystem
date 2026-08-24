from __future__ import annotations
from typing import Iterable

ENTITIES = {
    "EUR": ("eur", "euro", "eurozone", "ecb", "germany", "france"),
    "USD": ("usd", "united states", "federal reserve", "fed", "cpi", "pce", "nfp"),
    "MACRO": ("gdp", "pmi", "interest rate", "inflation", "employment", "geopolitical"),
}
POSITIVE = {"rise", "strong", "beat", "hawkish", "growth", "higher", "improve"}
NEGATIVE = {"fall", "weak", "miss", "dovish", "recession", "lower", "decline", "risk"}


def extract_entities(text: str) -> list[str]:
    lower = str(text).lower()
    return [entity for entity, aliases in ENTITIES.items() if any(alias in lower for alias in aliases)]

def lexicon_sentiment(text: str) -> float:
    tokens = set(str(text).lower().split())
    return float((len(tokens & POSITIVE) - len(tokens & NEGATIVE)) / max(1, len(tokens & POSITIVE) + len(tokens & NEGATIVE)))

def eurusd_relevance(text: str) -> float:
    lower = str(text).lower()
    hits = sum(alias in lower for aliases in ENTITIES.values() for alias in aliases)
    has_eur = any(alias in lower for alias in ENTITIES["EUR"])
    has_usd = any(alias in lower for alias in ENTITIES["USD"])
    return float(min(100.0, hits * 8.0 + (30.0 if has_eur and has_usd else 0.0)))
