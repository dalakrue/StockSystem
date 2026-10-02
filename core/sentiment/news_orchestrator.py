"""Free-first news collection and local NLP orchestration.

Provider order: GDELT -> Finnhub -> Alpha Vantage -> local repository. The module
is called only by the Settings-owned calculation orchestrator; renderers never
perform network requests.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import logging
import re
import sqlite3

import requests

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
from core.sentiment.eurusd_sentiment_engine import aggregate, score_article
from core.sentiment.news_repository import NewsRepository, normalized_text, text_hash

LOGGER = logging.getLogger(__name__)
NEWS_PROVIDER_PRIORITY = ("GDELT", "FINNHUB", "ALPHA_VANTAGE", "LOCAL_NEWS_CACHE")
QUERY = (
    '(EUR OR euro OR Eurozone OR ECB OR Lagarde OR Eurostat OR "European inflation" OR '
    'USD OR dollar OR "Federal Reserve" OR FOMC OR CPI OR PCE OR NFP OR payrolls OR '
    '"Treasury yields" OR DXY OR EURUSD OR "EUR/USD" OR "rate differential")'
)


class NewsOrchestrator:
    def __init__(self, db_path: str | Path | None = None, *, session: requests.Session | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)
        self.repository = NewsRepository(self.db_path)
        self.session = session or requests.Session()

    @staticmethod
    def _secret(state: Mapping[str, Any], provider: str) -> str:
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            return str(resolve_api_key(provider.lower(), state) or "").strip()
        except Exception:
            return ""

    def _cache_is_fresh(self, ttl_minutes: int) -> bool:
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            row = conn.execute("SELECT MAX(fetched_at) FROM news_articles").fetchone()
        if not row or not row[0]:
            return False
        try:
            fetched = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - fetched.astimezone(timezone.utc) < timedelta(minutes=ttl_minutes)
        except Exception:
            return False

    def _deduplicate(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not items:
            return []
        texts = [normalized_text(f"{item.get('title','')} {item.get('description','')}") for item in items]
        groups = list(range(len(items)))
        similarity: list[list[float]] | None = None
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            matrix = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english").fit_transform(texts)
            similarity = cosine_similarity(matrix).tolist()
        except Exception:
            similarity = None
        for i in range(len(items)):
            for j in range(i):
                exact = text_hash(texts[i]) == text_hash(texts[j])
                close = similarity is not None and similarity[i][j] >= 0.86
                if exact or close:
                    groups[i] = groups[j]
                    break
        group_sizes: dict[int, int] = {}
        for group in groups:
            group_sizes[group] = group_sizes.get(group, 0) + 1
        output: list[dict[str, Any]] = []
        seen: set[int] = set()
        for idx, item in enumerate(items):
            group = groups[idx]
            if group in seen:
                continue
            seen.add(group)
            scored = score_article(item)
            scored["duplicate_group"] = f"DG-{text_hash(texts[group])[:16]}"
            scored["novelty_score"] = max(0.0, 100.0 / group_sizes[group])
            scored["title_hash"] = text_hash(scored.get("title"))
            scored["body_hash"] = text_hash(scored.get("description"))
            output.append(scored)
        return output

    def _gdelt(self, *, limit: int = 100) -> list[dict[str, Any]]:
        response = self.session.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": QUERY, "mode": "ArtList", "maxrecords": min(max(10, limit), 250), "format": "json", "sort": "HybridRel"},
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for article in data.get("articles", []) or []:
            rows.append({
                "article_id": text_hash(f"GDELT|{article.get('url')}|{article.get('seendate')}"),
                "provider": "GDELT", "source": article.get("domain") or article.get("sourcecountry") or "",
                "source_quality": 65.0, "title": article.get("title") or "",
                "description": article.get("socialimage") or "", "article_url": article.get("url") or "",
                "published_at": article.get("seendate") or "", "fetched_at": now,
                "language": article.get("language") or "en",
            })
        return rows

    def _finnhub(self, state: Mapping[str, Any], *, limit: int = 100) -> list[dict[str, Any]]:
        key = self._secret(state, "finnhub")
        if not key:
            return []
        now_dt = datetime.now(timezone.utc)
        response = self.session.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": key}, timeout=20,
        )
        response.raise_for_status()
        now = now_dt.isoformat()
        rows = []
        for article in (response.json() or [])[:limit]:
            published = datetime.fromtimestamp(float(article.get("datetime") or now_dt.timestamp()), tz=timezone.utc).isoformat()
            rows.append({
                "article_id": text_hash(f"FINNHUB|{article.get('id')}|{article.get('url')}"),
                "provider": "FINNHUB", "source": article.get("source") or "", "source_quality": 70.0,
                "title": article.get("headline") or "", "description": article.get("summary") or "",
                "article_url": article.get("url") or "", "published_at": published, "fetched_at": now,
                "language": "en", "provider_sentiment": None,
            })
        return rows

    def _alpha(self, state: Mapping[str, Any], *, limit: int = 50) -> list[dict[str, Any]]:
        key = self._secret(state, "alpha_vantage")
        if not key:
            return []
        response = self.session.get(
            "https://www.alphavantage.co/query",
            params={"function": "NEWS_SENTIMENT", "tickers": "FOREX:EUR,FOREX:USD", "limit": min(limit, 1000), "apikey": key},
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("Note") or data.get("Information"):
            return []
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for article in data.get("feed", []) or []:
            published = str(article.get("time_published") or "")
            try:
                published = datetime.strptime(published, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
            rows.append({
                "article_id": text_hash(f"ALPHA_VANTAGE|{article.get('url')}|{published}"),
                "provider": "ALPHA_VANTAGE", "source": article.get("source") or "", "source_quality": 72.0,
                "title": article.get("title") or "", "description": article.get("summary") or "",
                "article_url": article.get("url") or "", "published_at": published, "fetched_at": now,
                "language": "en", "provider_sentiment": article.get("overall_sentiment_score"),
            })
        return rows

    def collect(
        self,
        state: Mapping[str, Any] | None = None,
        *,
        force: bool = False,
        ttl_minutes: int = 20,
        limit: int = 150,
    ) -> dict[str, Any]:
        state = state if isinstance(state, Mapping) else {}
        if not force and self._cache_is_fresh(ttl_minutes):
            cached = self.repository.recent(limit=limit)
            return {"ok": bool(cached), "provider": "LOCAL_NEWS_CACHE", "status": "CACHED_VALID", "articles": cached, "sentiment": aggregate(cached)}
        attempts: list[dict[str, Any]] = []
        collected: list[dict[str, Any]] = []
        for provider, fetcher in (("GDELT", lambda: self._gdelt(limit=limit)), ("FINNHUB", lambda: self._finnhub(state, limit=limit)), ("ALPHA_VANTAGE", lambda: self._alpha(state, limit=min(limit, 50)))):
            try:
                rows = fetcher()
                attempts.append({"provider": provider, "ok": bool(rows), "count": len(rows)})
                collected.extend(rows)
                # GDELT is the primary free pool. Supplement it, but do not fail
                # the run when paid-key providers are absent.
            except Exception as exc:
                attempts.append({"provider": provider, "ok": False, "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
                LOGGER.info("news_provider_failed provider=%s type=%s", provider, type(exc).__name__)
        deduplicated = self._deduplicate(collected)
        if deduplicated:
            persistence = self.repository.save(deduplicated)
            recent = self.repository.recent(limit=limit)
            return {
                "ok": True, "provider": "MULTI_SOURCE_FREE_FIRST", "status": "LIVE_PRIMARY",
                "articles": recent, "attempts": attempts, "persistence": persistence,
                "dataset_hash": self.repository.dataset_hash(recent), "sentiment": aggregate(recent),
            }
        cached = self.repository.recent(limit=limit)
        return {
            "ok": bool(cached), "provider": "LOCAL_NEWS_CACHE", "status": "CACHED_VALID" if cached else "INSUFFICIENT",
            "articles": cached, "attempts": attempts, "dataset_hash": self.repository.dataset_hash(cached),
            "sentiment": aggregate(cached),
        }


__all__ = ["NEWS_PROVIDER_PRIORITY", "NewsOrchestrator"]
