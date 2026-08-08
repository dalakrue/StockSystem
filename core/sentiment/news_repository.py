"""Persistent, deduplicated financial-news repository."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import re
import sqlite3

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema


def normalized_text(value: Any) -> str:
    return " ".join(re.sub(r"[^a-z0-9%$€]+", " ", str(value or "").lower()).split())


def text_hash(value: Any) -> str:
    return hashlib.sha256(normalized_text(value).encode("utf-8")).hexdigest()


class NewsRepository:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)

    def save(self, items: Iterable[Mapping[str, Any]]) -> dict[str, int]:
        inserted = duplicates = rejected = 0
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(str(self.db_path), timeout=20) as conn:
            conn.execute("PRAGMA busy_timeout=12000")
            conn.execute("BEGIN IMMEDIATE")
            for item in items:
                title = str(item.get("title") or item.get("headline") or "").strip()
                if not title:
                    rejected += 1
                    continue
                description = str(item.get("description") or item.get("summary") or "").strip()
                title_digest = str(item.get("title_hash") or text_hash(title))
                body_digest = str(item.get("body_hash") or text_hash(description)) if description else ""
                article_id = str(item.get("article_id") or item.get("id") or text_hash(
                    f"{item.get('provider')}|{title_digest}|{item.get('published_at')}"
                ))
                if conn.execute("SELECT 1 FROM news_articles WHERE article_id=?", (article_id,)).fetchone():
                    duplicates += 1
                conn.execute(
                    """INSERT INTO news_articles(
                       article_id,provider,source,source_quality,title,description,article_url,published_at,fetched_at,
                       language,translated_title,title_hash,body_hash,duplicate_group,novelty_score,eur_relevance,
                       usd_relevance,eurusd_relevance,event_type,event_importance,finbert_result,vader_result,
                       provider_sentiment,pair_direction_implication,freshness_score,uncertainty,reliability,payload_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(article_id) DO UPDATE SET
                       provider=excluded.provider,source=excluded.source,source_quality=excluded.source_quality,
                       title=excluded.title,description=excluded.description,article_url=excluded.article_url,
                       published_at=excluded.published_at,fetched_at=excluded.fetched_at,language=excluded.language,
                       translated_title=excluded.translated_title,title_hash=excluded.title_hash,body_hash=excluded.body_hash,
                       duplicate_group=excluded.duplicate_group,novelty_score=excluded.novelty_score,
                       eur_relevance=excluded.eur_relevance,usd_relevance=excluded.usd_relevance,
                       eurusd_relevance=excluded.eurusd_relevance,event_type=excluded.event_type,
                       event_importance=excluded.event_importance,finbert_result=excluded.finbert_result,
                       vader_result=excluded.vader_result,provider_sentiment=excluded.provider_sentiment,
                       pair_direction_implication=excluded.pair_direction_implication,freshness_score=excluded.freshness_score,
                       uncertainty=excluded.uncertainty,reliability=excluded.reliability,payload_json=excluded.payload_json""",
                    (
                        article_id, str(item.get("provider") or "LOCAL").upper(), str(item.get("source") or ""),
                        float(item.get("source_quality") or 50), title, description,
                        str(item.get("article_url") or item.get("url") or ""), str(item.get("published_at") or ""),
                        str(item.get("fetched_at") or now), str(item.get("language") or "en"),
                        str(item.get("translated_title") or ""), title_digest, body_digest,
                        str(item.get("duplicate_group") or title_digest), float(item.get("novelty_score") or 100),
                        float(item.get("eur_relevance") or 0), float(item.get("usd_relevance") or 0),
                        float(item.get("eurusd_relevance") or 0), str(item.get("event_type") or "OTHER"),
                        float(item.get("event_importance") or 0), str(item.get("finbert_result") or ""),
                        None if item.get("vader_result") is None else float(item.get("vader_result")),
                        None if item.get("provider_sentiment") is None else float(item.get("provider_sentiment")),
                        None if item.get("pair_direction_implication") is None else float(item.get("pair_direction_implication")),
                        float(item.get("freshness_score") or 0), float(item.get("uncertainty") or 0),
                        float(item.get("reliability") or 0), json.dumps(dict(item), default=str, ensure_ascii=False),
                    ),
                )
                inserted += 1
            conn.commit()
        return {"inserted_or_updated": inserted, "duplicates": duplicates, "rejected": rejected}

    def recent(self, *, limit: int = 250, max_age_hours: int = 720) -> list[dict[str, Any]]:
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """SELECT * FROM news_articles
                   WHERE published_at='' OR datetime(published_at)>=datetime('now', ?)
                   ORDER BY COALESCE(NULLIF(published_at,''),fetched_at) DESC LIMIT ?""",
                (f"-{int(max_age_hours)} hours", int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def dataset_hash(self, items: Iterable[Mapping[str, Any]] | None = None) -> str:
        rows = list(items) if items is not None else self.recent(limit=500)
        material = "|".join(sorted(str(row.get("article_id") or row.get("title_hash") or "") for row in rows))
        return hashlib.sha256(material.encode()).hexdigest()


__all__ = ["NewsRepository", "normalized_text", "text_hash"]
