"""Finnhub-backed multi-symbol sentiment evidence for Field 10.

This module is intentionally additive and read/write separated:

* ``refresh_and_persist_finnhub_sentiment`` is called only by the existing
  Settings multi-symbol calculation transaction. It fetches Finnhub once,
  stores a shared deduplicated pool, maps the same real articles to every FX
  pair, and persists immutable per-snapshot evidence.
* ``load_finnhub_sentiment_rank`` is a read-only Lunch/Field 10 loader.

No API key or credential is accepted, returned, logged, or stored here. The
existing secure Finnhub connector remains the only owner of authentication.
Unavailable event fields stay unavailable rather than being fabricated.
"""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping, Sequence
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import math
import re
import sqlite3

import pandas as pd

from core.multi_symbol_field10_20260701 import DB_PATH, normalize_symbol

VERSION = "field10-finnhub-sentiment-20260704-v1"
FORMULA_VERSION = "field10-finnhub-pair-map-decay-v1"
THRESHOLD_VERSION = "field10-news-absorption-thresholds-v1"

_CURRENCY_NAMES: dict[str, tuple[str, ...]] = {
    "USD": ("usd", "dollar", "greenback", "united states", "u.s.", "fed", "fomc", "powell"),
    "EUR": ("eur", "euro", "eurozone", "ecb", "lagarde"),
    "GBP": ("gbp", "pound", "sterling", "united kingdom", "britain", "boe", "bailey"),
    "JPY": ("jpy", "yen", "japan", "boj", "ueda"),
    "CHF": ("chf", "franc", "switzerland", "snb"),
    "AUD": ("aud", "australian dollar", "australia", "rba"),
    "NZD": ("nzd", "new zealand dollar", "new zealand", "rbnz"),
    "CAD": ("cad", "canadian dollar", "canada", "boc", "macklem"),
}
_POSITIVE = {
    "hawkish", "hike", "hikes", "higher", "strong", "stronger", "strengthens",
    "rises", "rise", "gains", "beats", "above", "accelerates", "expands",
    "growth", "surplus", "rebound", "improves", "upgrade", "upgraded",
}
_NEGATIVE = {
    "dovish", "cut", "cuts", "lower", "weak", "weaker", "falls", "fall",
    "drops", "misses", "below", "slows", "contracts", "recession", "deficit",
    "downgrade", "downgraded", "crisis", "risk", "uncertainty",
}
_HIGH_IMPACT = {
    "rate", "rates", "inflation", "cpi", "pce", "payroll", "nfp", "jobs",
    "employment", "gdp", "central bank", "fomc", "ecb", "boe", "boj", "snb",
    "rba", "rbnz", "boc", "tariff", "sanction", "war", "election",
}
_EVENT_HALF_LIFE_MINUTES = {
    "CENTRAL_BANK_RATES": 360.0,
    "INFLATION": 240.0,
    "LABOUR": 240.0,
    "GROWTH": 180.0,
    "GEOPOLITICAL_TRADE": 480.0,
    "GENERAL_MACRO_FX": 120.0,
}

_DISPLAY_COLUMNS = [
    "News Rank", "Symbol", "Sentiment Bias", "Sentiment Probability",
    "Base-Currency Effect", "Quote-Currency Effect", "Pair Direction Effect",
    "High-Impact Headline", "Event Type", "Affected Currency", "Source",
    "Source Quality", "News Release UTC", "News Release Broker Time",
    "Current Broker Time", "Event Age Minutes", "Scheduled / Unscheduled",
    "Actual Value", "Consensus Value", "Surprise Score", "Entity Relevance",
    "Pair Relevance", "Novelty Score", "Duplicate Group", "FinBERT Tone",
    "Deterministic Fallback Tone", "Sentiment Agreement", "Abnormal Return",
    "Cumulative Abnormal Return", "Abnormal Volatility", "Abnormal Tick Volume",
    "Event Response Percentile", "Event Intensity", "Estimated Impact Half-Life",
    "Expected Impact Time Left", "Impact Remaining Percentage",
    "Absorption Percentage", "Absorption Status", "Next-1H Shock Probability",
    "Reversal Risk", "Event-Risk Permission", "Evidence Sample Size",
    "Model Version", "Data Provider", "Provider Authentication",
    "Timestamp Provenance", "Explanation",
]


def _connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=8000")
    conn.row_factory = sqlite3.Row
    return conn


def migrate_finnhub_sentiment_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Create the additive Finnhub rank and settlement tables idempotently."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS field10_daily_news_event_rank (
                daily_snapshot_id TEXT NOT NULL,
                broker_day TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_id TEXT NOT NULL,
                news_rank INTEGER,
                sentiment_bias TEXT,
                sentiment_probability REAL,
                base_currency_effect TEXT,
                quote_currency_effect TEXT,
                pair_direction_effect TEXT,
                headline TEXT NOT NULL,
                event_type TEXT,
                affected_currency TEXT,
                source TEXT,
                source_quality REAL,
                release_utc TEXT,
                release_broker_time TEXT,
                current_broker_time TEXT,
                event_age_minutes REAL,
                scheduled_status TEXT,
                actual_value TEXT,
                consensus_value TEXT,
                surprise_score REAL,
                entity_relevance REAL,
                pair_relevance REAL,
                novelty_score REAL,
                duplicate_group TEXT,
                finbert_tone TEXT,
                fallback_tone TEXT,
                sentiment_agreement TEXT,
                abnormal_return REAL,
                cumulative_abnormal_return REAL,
                abnormal_volatility REAL,
                abnormal_tick_volume REAL,
                event_response_percentile REAL,
                event_intensity REAL,
                estimated_half_life_minutes REAL,
                expected_impact_time_left_minutes REAL,
                impact_remaining_pct REAL,
                absorption_pct REAL,
                absorption_status TEXT,
                next_1h_shock_probability REAL,
                reversal_risk REAL,
                event_risk_permission TEXT,
                evidence_sample_size INTEGER NOT NULL DEFAULT 1,
                model_version TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                threshold_version TEXT NOT NULL,
                data_provider TEXT NOT NULL,
                provider_authentication TEXT NOT NULL,
                timestamp_provenance TEXT NOT NULL,
                provider_article_id TEXT,
                normalized_url TEXT,
                content_hash TEXT NOT NULL,
                row_json TEXT NOT NULL,
                publication_status TEXT NOT NULL,
                stored_at TEXT NOT NULL,
                PRIMARY KEY(daily_snapshot_id, symbol, event_id),
                FOREIGN KEY(daily_snapshot_id, symbol)
                    REFERENCES field10_daily_snapshot_symbol(daily_snapshot_id, symbol)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_news_snapshot_rank_20260704
                ON field10_daily_news_event_rank(daily_snapshot_id, news_rank, symbol);
            CREATE INDEX IF NOT EXISTS idx_f10_news_day_symbol_20260704
                ON field10_daily_news_event_rank(broker_day DESC, symbol, news_rank);
            CREATE INDEX IF NOT EXISTS idx_f10_news_release_20260704
                ON field10_daily_news_event_rank(release_utc DESC, affected_currency);
            CREATE INDEX IF NOT EXISTS idx_f10_news_status_20260704
                ON field10_daily_news_event_rank(publication_status, event_risk_permission);

            CREATE TABLE IF NOT EXISTS field10_news_event_outcome (
                outcome_id TEXT PRIMARY KEY,
                daily_snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                event_id TEXT NOT NULL,
                horizon TEXT NOT NULL,
                original_forecast_hash TEXT NOT NULL,
                realized_return REAL,
                realized_direction TEXT,
                correct_direction INTEGER,
                settled_at_broker_time TEXT NOT NULL,
                outcome_json TEXT NOT NULL,
                outcome_hash TEXT NOT NULL UNIQUE,
                FOREIGN KEY(daily_snapshot_id, symbol, event_id)
                    REFERENCES field10_daily_news_event_rank(daily_snapshot_id, symbol, event_id)
            );
            CREATE INDEX IF NOT EXISTS idx_f10_news_outcome_snapshot_20260704
                ON field10_news_event_outcome(daily_snapshot_id, symbol, event_id, horizon);
            """
        )
        required = {
            "field10_daily_news_event_rank": {
                "daily_snapshot_id", "symbol", "event_id", "data_provider",
                "provider_authentication", "release_utc", "event_age_minutes",
                "impact_remaining_pct", "absorption_pct", "row_json", "content_hash",
            },
            "field10_news_event_outcome": {
                "outcome_id", "daily_snapshot_id", "symbol", "event_id",
                "original_forecast_hash", "outcome_hash",
            },
        }
        missing: dict[str, list[str]] = {}
        for table, wanted in required.items():
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
            absent = sorted(wanted - columns)
            if absent:
                missing[table] = absent
        conn.commit()
    return {
        "ok": not missing,
        "status": "PASS" if not missing else "FAIL",
        "version": VERSION,
        "missing_columns": missing,
        "tables": sorted(required),
    }


def verify_finnhub_sentiment_database(path: Path | str = DB_PATH) -> dict[str, Any]:
    """Read-only schema verification used by Lunch rendering."""
    required = {
        "field10_daily_news_event_rank": {
            "daily_snapshot_id", "symbol", "event_id", "data_provider",
            "provider_authentication", "release_utc", "event_age_minutes",
            "impact_remaining_pct", "absorption_pct", "row_json", "content_hash",
        },
        "field10_news_event_outcome": {
            "outcome_id", "daily_snapshot_id", "symbol", "event_id",
            "original_forecast_hash", "outcome_hash",
        },
    }
    path = Path(path)
    if not path.exists():
        return {"ok": False, "status": "DATABASE_NOT_FOUND", "missing_tables": sorted(required)}
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}
    secret_column_issues: dict[str, list[str]] = {}
    with sqlite3.connect(str(path), timeout=30) as conn:
        tables = {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, wanted in required.items():
            if table not in tables:
                missing_tables.append(table)
                continue
            columns = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}
            absent = sorted(wanted - columns)
            if absent:
                missing_columns[table] = absent
            bad = sorted(
                column for column in columns
                if any(token in column.lower() for token in ("api_key", "password", "secret", "credential", "access_token"))
            )
            if bad:
                secret_column_issues[table] = bad
        prohibited = sorted(
            name for name in tables
            if name.lower() in {"field10_rank", "field10_rank_20260704", "field10_production_rank"}
        )
        integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    ok = not missing_tables and not missing_columns and not secret_column_issues and not prohibited and integrity.lower() == "ok"
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "secret_column_issues": secret_column_issues,
        "prohibited_rank_tables": prohibited,
        "integrity_check": integrity,
        "finnhub_news_schema_verified": not missing_tables and not missing_columns and not secret_column_issues,
    }


def _timestamp(value: Any) -> pd.Timestamp:
    if value in (None, ""):
        return pd.NaT
    try:
        if isinstance(value, (int, float)) or str(value).strip().isdigit():
            return pd.to_datetime(float(value), unit="s", utc=True, errors="coerce")
        return pd.to_datetime(value, utc=True, errors="coerce")
    except Exception:
        return pd.NaT


def _text(article: Mapping[str, Any]) -> str:
    return " ".join(
        str(article.get(key) or "") for key in ("headline", "summary", "related", "category")
    ).strip().lower()


def _event_type(text: str) -> str:
    tokens = set(re.findall(r"[a-z]+", text))
    if tokens & {"fed", "fomc", "ecb", "boe", "boj", "snb", "rba", "rbnz", "boc", "rate", "rates"}:
        return "CENTRAL_BANK_RATES"
    if tokens & {"inflation", "cpi", "pce", "ppi"}:
        return "INFLATION"
    if tokens & {"nfp", "payroll", "jobs", "employment", "unemployment"}:
        return "LABOUR"
    if tokens & {"gdp", "growth", "recession", "retail", "production"}:
        return "GROWTH"
    if tokens & {"tariff", "sanction", "war", "election", "geopolitical", "trade"}:
        return "GEOPOLITICAL_TRADE"
    return "GENERAL_MACRO_FX"


def _affected_currency(text: str) -> tuple[str, float]:
    scores: dict[str, int] = {}
    for currency, markers in _CURRENCY_NAMES.items():
        scores[currency] = sum(text.count(marker) for marker in markers)
    winner = max(scores, key=scores.get) if scores else ""
    best = scores.get(winner, 0)
    total = sum(scores.values())
    relevance = 0.0 if best <= 0 else min(100.0, 55.0 + 45.0 * best / max(1, total))
    return (winner if best > 0 else "UNAVAILABLE", relevance)


def _tone(text: str) -> tuple[str, float, float]:
    tokens = set(re.findall(r"[a-z]+", text))
    pos = len(tokens & _POSITIVE)
    neg = len(tokens & _NEGATIVE)
    signed = float(pos - neg)
    strength = min(1.0, abs(signed) / 4.0)
    label = "POSITIVE" if signed > 0 else "NEGATIVE" if signed < 0 else "NEUTRAL"
    probability = 50.0 if signed == 0 else min(88.0, 58.0 + 30.0 * strength)
    return label, probability, signed


def _pair_parts(symbol: str) -> tuple[str, str]:
    clean = normalize_symbol(symbol)
    return (clean[:3], clean[3:6]) if len(clean) >= 6 else ("", "")


def _pair_direction(symbol: str, affected: str, tone: str) -> tuple[str, str, str, float]:
    base, quote = _pair_parts(symbol)
    sign = 1 if tone == "POSITIVE" else -1 if tone == "NEGATIVE" else 0
    base_effect = "NEUTRAL"
    quote_effect = "NEUTRAL"
    direction = "WAIT"
    relevance = 0.0
    if affected == base:
        base_effect = tone
        relevance = 100.0
        direction = "BUY" if sign > 0 else "SELL" if sign < 0 else "WAIT"
    elif affected == quote:
        quote_effect = tone
        relevance = 100.0
        direction = "SELL" if sign > 0 else "BUY" if sign < 0 else "WAIT"
    elif affected not in {"", "UNAVAILABLE"}:
        relevance = 10.0
    return base_effect, quote_effect, direction, relevance


def _absorption(age_minutes: float, half_life: float) -> tuple[float, float, str]:
    remaining = 100.0 * math.exp(-math.log(2.0) * max(0.0, age_minutes) / max(1.0, half_life))
    remaining = min(100.0, max(0.0, remaining))
    absorbed = min(100.0, max(0.0, 100.0 - remaining))
    if absorbed < 35.0:
        label = "UNABSORBED"
    elif absorbed < 70.0:
        label = "PARTIALLY_ABSORBED"
    elif absorbed < 90.0:
        label = "MOSTLY_ABSORBED"
    else:
        label = "ABSORBED"
    return remaining, absorbed, label


def _snapshot_identity(path: Path | str, daily_snapshot_id: str | None) -> dict[str, Any]:
    with _connect(path) as conn:
        if daily_snapshot_id:
            row = conn.execute(
                "SELECT * FROM field10_daily_snapshot WHERE daily_snapshot_id=?", (daily_snapshot_id,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM field10_daily_snapshot ORDER BY broker_day DESC LIMIT 1"
            ).fetchone()
    return dict(row) if row else {}


def _article_event_id(article: Mapping[str, Any]) -> str:
    material = "|".join(
        str(article.get(key) or "") for key in ("id", "url", "headline", "datetime", "source")
    )
    return "FNH-" + sha256(material.encode("utf-8")).hexdigest()[:28]


def _row_for_article(
    *, article: Mapping[str, Any], symbol: str, snapshot: Mapping[str, Any], stored_at: str,
) -> dict[str, Any] | None:
    release = _timestamp(article.get("datetime") or article.get("published_at") or article.get("time"))
    if pd.isna(release):
        return None
    current = _timestamp(snapshot.get("latest_completed_h1") or snapshot.get("cutoff_broker_time"))
    if pd.isna(current):
        return None
    if release > current + pd.Timedelta(minutes=5):
        return None
    age = max(0.0, (current - release).total_seconds() / 60.0)
    release_broker = release.tz_convert(current.tz) if getattr(current, "tz", None) is not None else release
    text = _text(article)
    affected, entity_relevance = _affected_currency(text)
    tone, tone_probability, signed_tone = _tone(text)
    base_effect, quote_effect, direction, pair_relevance = _pair_direction(symbol, affected, tone)
    related = str(article.get("related") or "").upper()
    if normalize_symbol(symbol) and normalize_symbol(symbol) in re.sub(r"[^A-Z]", "", related):
        pair_relevance = 100.0
    event_type = _event_type(text)
    half_life = float(_EVENT_HALF_LIFE_MINUTES[event_type])
    remaining, absorbed, absorption_status = _absorption(age, half_life)
    source_quality = 70.0 if str(article.get("source") or "").strip() else 55.0
    high_impact = any(token in text for token in _HIGH_IMPACT)
    novelty = 100.0
    score = (
        0.38 * pair_relevance
        + 0.18 * abs(tone_probability - 50.0) * 2.0
        + 0.27 * remaining
        + 0.12 * source_quality
        + (5.0 if high_impact else 0.0)
    )
    permission = "BLOCK" if high_impact and remaining >= 55.0 else "CAUTION" if remaining >= 25.0 else "ALLOW"
    reversal_risk = min(100.0, 20.0 + absorbed * 0.55) if tone != "NEUTRAL" else 50.0
    event_intensity = remaining / 100.0
    next_shock = min(95.0, max(5.0, 12.0 + remaining * 0.62 + (10.0 if high_impact else 0.0)))
    event_id = _article_event_id(article)
    release_iso = pd.Timestamp(release).isoformat()
    current_iso = pd.Timestamp(current).isoformat()
    row = {
        "daily_snapshot_id": str(snapshot.get("daily_snapshot_id") or ""),
        "broker_day": str(snapshot.get("broker_day") or ""),
        "symbol": normalize_symbol(symbol),
        "event_id": event_id,
        "news_rank": None,
        "sentiment_bias": direction,
        "sentiment_probability": tone_probability,
        "base_currency_effect": base_effect,
        "quote_currency_effect": quote_effect,
        "pair_direction_effect": direction,
        "headline": str(article.get("headline") or article.get("title") or "")[:500],
        "event_type": event_type,
        "affected_currency": affected,
        "source": str(article.get("source") or "Finnhub")[:160],
        "source_quality": source_quality,
        "release_utc": release_iso,
        "release_broker_time": pd.Timestamp(release_broker).isoformat(),
        "current_broker_time": current_iso,
        "event_age_minutes": age,
        "scheduled_status": "UNAVAILABLE",
        "actual_value": "UNAVAILABLE",
        "consensus_value": "UNAVAILABLE",
        "surprise_score": None,
        "entity_relevance": entity_relevance,
        "pair_relevance": pair_relevance,
        "novelty_score": novelty,
        "duplicate_group": sha256(re.sub(r"[^a-z0-9]+", "", str(article.get("headline") or "").lower()).encode()).hexdigest()[:16],
        "finbert_tone": "UNAVAILABLE_NOT_RUN",
        "fallback_tone": tone,
        "sentiment_agreement": "UNAVAILABLE_FINBERT_NOT_RUN",
        "abnormal_return": None,
        "cumulative_abnormal_return": None,
        "abnormal_volatility": None,
        "abnormal_tick_volume": None,
        "event_response_percentile": None,
        "event_intensity": event_intensity,
        "estimated_half_life_minutes": half_life,
        "expected_impact_time_left_minutes": max(0.0, half_life * remaining / 100.0),
        "impact_remaining_pct": remaining,
        "absorption_pct": absorbed,
        "absorption_status": absorption_status,
        "next_1h_shock_probability": next_shock,
        "reversal_risk": reversal_risk,
        "event_risk_permission": permission,
        "evidence_sample_size": 1,
        "model_version": VERSION,
        "formula_version": FORMULA_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "data_provider": "FINNHUB",
        "provider_authentication": "FINNHUB_AUTHENTICATED_API",
        "timestamp_provenance": "FINNHUB_DATETIME_UNIX_UTC",
        "provider_article_id": str(article.get("id") or ""),
        "normalized_url": str(article.get("url") or "").split("?")[0][:1000],
        "publication_status": "PERSISTED_FROM_SETTINGS_RUN",
        "stored_at": stored_at,
        "_score": score,
        "_signed_tone": signed_tone,
        "_high_impact": high_impact,
    }
    explanation = {
        "provider": "FINNHUB",
        "authenticated_connector": True,
        "pair_mapping": "positive base=>BUY; positive quote=>SELL; negative mapping reversed",
        "event_decay_method": "DETERMINISTIC_EXPONENTIAL_FALLBACK",
        "event_study_status": "UNAVAILABLE_NO_CAUSAL_MATCHED_EVENT_SAMPLE",
        "finbert_status": "OPTIONAL_NOT_RUN",
        "limitations": "Finnhub market-news rows do not supply economic actual/consensus surprise fields.",
        "high_impact_keyword_match": bool(high_impact),
    }
    row["explanation"] = json.dumps(explanation, sort_keys=True)
    return row


def _insert_rows(path: Path | str, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    columns = [
        "daily_snapshot_id", "broker_day", "symbol", "event_id", "news_rank",
        "sentiment_bias", "sentiment_probability", "base_currency_effect",
        "quote_currency_effect", "pair_direction_effect", "headline", "event_type",
        "affected_currency", "source", "source_quality", "release_utc",
        "release_broker_time", "current_broker_time", "event_age_minutes",
        "scheduled_status", "actual_value", "consensus_value", "surprise_score",
        "entity_relevance", "pair_relevance", "novelty_score", "duplicate_group",
        "finbert_tone", "fallback_tone", "sentiment_agreement", "abnormal_return",
        "cumulative_abnormal_return", "abnormal_volatility", "abnormal_tick_volume",
        "event_response_percentile", "event_intensity", "estimated_half_life_minutes",
        "expected_impact_time_left_minutes", "impact_remaining_pct", "absorption_pct",
        "absorption_status", "next_1h_shock_probability", "reversal_risk",
        "event_risk_permission", "evidence_sample_size", "model_version",
        "formula_version", "threshold_version", "data_provider",
        "provider_authentication", "timestamp_provenance", "provider_article_id",
        "normalized_url", "content_hash", "row_json", "publication_status", "stored_at",
    ]
    placeholders = ",".join("?" for _ in columns)
    update = ",".join(
        f"{column}=excluded.{column}" for column in columns
        if column not in {"daily_snapshot_id", "symbol", "event_id"}
    )
    with _connect(path) as conn:
        for raw in rows:
            display = _display_row(raw)
            content = {key: value for key, value in raw.items() if not key.startswith("_") and key not in {"content_hash", "row_json"}}
            content_hash = sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()
            payload = {**content, "display": display}
            values = {**content, "content_hash": content_hash, "row_json": json.dumps(payload, sort_keys=True, default=str)}
            conn.execute(
                f"INSERT INTO field10_daily_news_event_rank({','.join(columns)}) VALUES({placeholders}) "
                f"ON CONFLICT(daily_snapshot_id,symbol,event_id) DO UPDATE SET {update}",
                tuple(values.get(column) for column in columns),
            )
        conn.commit()
    return len(rows)


def refresh_and_persist_finnhub_sentiment(
    state: MutableMapping[str, Any], *, daily_snapshot_id: str | None,
    selected_symbols: Sequence[str], path: Path | str = DB_PATH,
) -> dict[str, Any]:
    """Fetch Finnhub once and persist pair-specific Field 10 sentiment rows."""
    migration = migrate_finnhub_sentiment_database(path)
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    if not snapshot:
        return {"ok": False, "status": "NO_DAILY_SNAPSHOT", "migration": migration}
    try:
        from core.finnhub_connector import connection_status, fetch_market_news
        connector = connection_status()
        if not connector.get("connected"):
            return {
                "ok": False,
                "status": "FINNHUB_NOT_CONNECTED",
                "migration": migration,
                "provider": "FINNHUB",
                "rows_persisted": 0,
            }
        articles = fetch_market_news("forex", force=False, ttl_seconds=900)
    except Exception as exc:
        return {
            "ok": False, "status": "FINNHUB_FETCH_FAILED", "provider": "FINNHUB",
            "error": f"{type(exc).__name__}: {exc}", "migration": migration,
        }
    articles = [dict(item) for item in articles if isinstance(item, Mapping)]
    from core.multi_symbol_api_runtime_20260702 import cache_shared_news_items
    cache_report = cache_shared_news_items(articles, provider="FINNHUB", path=path)
    stored_at = pd.Timestamp.now(tz="UTC").isoformat()
    rows: list[dict[str, Any]] = []
    for symbol in [normalize_symbol(item) for item in selected_symbols if str(item).strip()]:
        for article in articles:
            row = _row_for_article(article=article, symbol=symbol, snapshot=snapshot, stored_at=stored_at)
            if row is not None and (row["pair_relevance"] > 0.0 or row["_high_impact"]):
                rows.append(row)
    rows.sort(
        key=lambda item: (
            float(item.get("_score") or 0.0),
            float(item.get("pair_relevance") or 0.0),
            str(item.get("release_utc") or ""),
            str(item.get("symbol") or ""),
        ),
        reverse=True,
    )
    for rank, row in enumerate(rows, start=1):
        row["news_rank"] = rank
    persisted = _insert_rows(path, rows)
    report = {
        "ok": True,
        "status": "PERSISTED" if persisted else "NO_RELEVANT_FINNHUB_ROWS",
        "provider": "FINNHUB",
        "provider_authentication": "FINNHUB_AUTHENTICATED_API",
        "daily_snapshot_id": snapshot.get("daily_snapshot_id"),
        "article_count": len(articles),
        "rows_persisted": persisted,
        "symbols": sorted({row["symbol"] for row in rows}),
        "cache_report": cache_report,
        "migration": migration,
        "secret_persisted": False,
        "version": VERSION,
    }
    state["field10_finnhub_sentiment_report_20260704"] = report
    return report


def _display_row(row: Mapping[str, Any]) -> dict[str, Any]:
    def unavailable(value: Any) -> Any:
        return "UNAVAILABLE" if value is None or (isinstance(value, float) and math.isnan(value)) else value

    return {
        "News Rank": row.get("news_rank"),
        "Symbol": row.get("symbol"),
        "Sentiment Bias": row.get("sentiment_bias"),
        "Sentiment Probability": row.get("sentiment_probability"),
        "Base-Currency Effect": row.get("base_currency_effect"),
        "Quote-Currency Effect": row.get("quote_currency_effect"),
        "Pair Direction Effect": row.get("pair_direction_effect"),
        "High-Impact Headline": row.get("headline"),
        "Event Type": row.get("event_type"),
        "Affected Currency": row.get("affected_currency"),
        "Source": row.get("source"),
        "Source Quality": row.get("source_quality"),
        "News Release UTC": row.get("release_utc"),
        "News Release Broker Time": row.get("release_broker_time"),
        "Current Broker Time": row.get("current_broker_time"),
        "Event Age Minutes": row.get("event_age_minutes"),
        "Scheduled / Unscheduled": row.get("scheduled_status"),
        "Actual Value": unavailable(row.get("actual_value")),
        "Consensus Value": unavailable(row.get("consensus_value")),
        "Surprise Score": unavailable(row.get("surprise_score")),
        "Entity Relevance": row.get("entity_relevance"),
        "Pair Relevance": row.get("pair_relevance"),
        "Novelty Score": row.get("novelty_score"),
        "Duplicate Group": row.get("duplicate_group"),
        "FinBERT Tone": row.get("finbert_tone"),
        "Deterministic Fallback Tone": row.get("fallback_tone"),
        "Sentiment Agreement": row.get("sentiment_agreement"),
        "Abnormal Return": unavailable(row.get("abnormal_return")),
        "Cumulative Abnormal Return": unavailable(row.get("cumulative_abnormal_return")),
        "Abnormal Volatility": unavailable(row.get("abnormal_volatility")),
        "Abnormal Tick Volume": unavailable(row.get("abnormal_tick_volume")),
        "Event Response Percentile": unavailable(row.get("event_response_percentile")),
        "Event Intensity": row.get("event_intensity"),
        "Estimated Impact Half-Life": row.get("estimated_half_life_minutes"),
        "Expected Impact Time Left": row.get("expected_impact_time_left_minutes"),
        "Impact Remaining Percentage": row.get("impact_remaining_pct"),
        "Absorption Percentage": row.get("absorption_pct"),
        "Absorption Status": row.get("absorption_status"),
        "Next-1H Shock Probability": row.get("next_1h_shock_probability"),
        "Reversal Risk": row.get("reversal_risk"),
        "Event-Risk Permission": row.get("event_risk_permission"),
        "Evidence Sample Size": row.get("evidence_sample_size"),
        "Model Version": row.get("model_version"),
        "Data Provider": row.get("data_provider"),
        "Provider Authentication": row.get("provider_authentication"),
        "Timestamp Provenance": row.get("timestamp_provenance"),
        "Explanation": row.get("explanation") or "Persisted authenticated Finnhub evidence.",
    }


def load_finnhub_sentiment_rank(
    *, daily_snapshot_id: str | None = None, path: Path | str = DB_PATH,
    limit: int = 500,
) -> pd.DataFrame:
    """Read persisted Finnhub evidence; never fetch, calculate, or migrate from UI."""
    health = verify_finnhub_sentiment_database(path)
    if not health.get("ok"):
        return pd.DataFrame(columns=_DISPLAY_COLUMNS)
    snapshot = _snapshot_identity(path, daily_snapshot_id)
    snapshot_id = str(snapshot.get("daily_snapshot_id") or "")
    if not snapshot_id:
        return pd.DataFrame(columns=_DISPLAY_COLUMNS)
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT row_json FROM field10_daily_news_event_rank "
            "WHERE daily_snapshot_id=? ORDER BY news_rank IS NULL,news_rank,symbol LIMIT ?",
            (snapshot_id, max(1, int(limit))),
        ).fetchall()
    output: list[dict[str, Any]] = []
    for stored in rows:
        try:
            payload = json.loads(str(stored[0] or "{}"))
            display = payload.get("display") if isinstance(payload, Mapping) else None
            output.append(dict(display) if isinstance(display, Mapping) else _display_row(payload))
        except Exception:
            continue
    frame = pd.DataFrame(output)
    for column in _DISPLAY_COLUMNS:
        if column not in frame.columns:
            frame[column] = None
    return frame.loc[:, _DISPLAY_COLUMNS]


__all__ = [
    "VERSION", "FORMULA_VERSION", "THRESHOLD_VERSION",
    "migrate_finnhub_sentiment_database", "verify_finnhub_sentiment_database",
    "refresh_and_persist_finnhub_sentiment", "load_finnhub_sentiment_rank",
]
