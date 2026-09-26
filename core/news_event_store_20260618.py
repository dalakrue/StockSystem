"""Persistent, secret-safe real-news event ledger for the existing NLP workspace."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from core.prediction_ledger_20260617 import DEFAULT_DB_PATH

_LOCK = threading.RLock()
_MEMORY: dict[str, dict[str, Any]] = {}
_SECRET_TOKENS = ("api_key", "apikey", "secret", "password", "authorization", "bearer", "access_token")


def _clean_text(value: Any, limit: int = 4000) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def _title(row: Mapping[str, Any]) -> str:
    return _clean_text(row.get("headline") or row.get("title") or row.get("Title") or row.get("Headline"), 600)


def _source(row: Mapping[str, Any]) -> str:
    return _clean_text(row.get("source") or row.get("Source") or row.get("provider") or "Unknown", 200)


def _timestamp(row: Mapping[str, Any]) -> pd.Timestamp:
    value = None
    for key in ("publication_time", "publishedDate", "published", "datetime", "timestamp", "Time", "Published", "date"):
        if row.get(key) not in (None, ""):
            value = row.get(key); break
    try:
        if isinstance(value, (int, float)):
            unit = "ms" if abs(float(value)) > 10_000_000_000 else "s"
            ts = pd.to_datetime(value, unit=unit, errors="coerce", utc=True)
        else:
            ts = pd.to_datetime(value, errors="coerce", utc=True)
        return pd.Timestamp(ts) if not pd.isna(ts) else pd.NaT
    except Exception:
        return pd.NaT


def _normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _safe_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        lower = str(key).lower()
        if any(token in lower for token in _SECRET_TOKENS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            out[str(key)] = value
        elif isinstance(value, (pd.Timestamp, datetime)):
            out[str(key)] = pd.Timestamp(value).isoformat()
        elif isinstance(value, (list, tuple, dict)):
            out[str(key)] = value
        else:
            out[str(key)] = str(value)
    return out


def normalize_article(row: Mapping[str, Any], *, now: pd.Timestamp | None = None) -> dict[str, Any] | None:
    headline = _title(row)
    if not headline:
        return None
    source = _source(row)
    published = _timestamp(row)
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    if pd.isna(published) or published > current + pd.Timedelta(minutes=5):
        return None
    normalized = _normalized_title(headline)
    url = _clean_text(row.get("url") or row.get("URL"), 1500)
    duplicate_identity = hashlib.sha256(f"{normalized}|{source.lower()}".encode()).hexdigest()[:24]
    article_id = _clean_text(row.get("article_id") or row.get("id"), 200)
    if not article_id:
        article_id = hashlib.sha256(f"{duplicate_identity}|{url}|{published.isoformat()}".encode()).hexdigest()
    retrieval = pd.Timestamp.now(tz="UTC").isoformat()
    payload = _safe_payload(row)
    return {
        **payload,
        "article_id": article_id,
        "duplicate_identity": duplicate_identity,
        "headline": headline,
        "title": headline,
        "source": source,
        "url": url,
        "publication_time": published.isoformat(),
        "datetime": published.isoformat(),
        "retrieval_time": _clean_text(row.get("retrieval_time") or retrieval, 100),
        "cache_freshness": _clean_text(row.get("cache_freshness") or "PERSISTED", 80),
    }


def _near_duplicate(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    if str(a.get("source", "")).lower() != str(b.get("source", "")).lower():
        return False
    ta = _normalized_title(str(a.get("headline", "")))
    tb = _normalized_title(str(b.get("headline", "")))
    if not ta or not tb:
        return False
    try:
        da = pd.Timestamp(a.get("publication_time")); db = pd.Timestamp(b.get("publication_time"))
        if abs((da - db).total_seconds()) > 24 * 3600:
            return False
    except Exception:
        return False
    ratio = SequenceMatcher(None, ta, tb).ratio()
    tokens_a, tokens_b = set(ta.split()), set(tb.split())
    jaccard = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
    return ratio >= 0.965 and jaccard >= 0.94


def deduplicate_articles(rows: Iterable[Mapping[str, Any]], *, now: pd.Timestamp | None = None) -> list[dict[str, Any]]:
    normalized = [item for raw in rows if isinstance(raw, Mapping) and (item := normalize_article(raw, now=now))]
    normalized.sort(key=lambda x: str(x.get("publication_time")), reverse=True)
    selected: list[dict[str, Any]] = []
    exact: set[str] = set()
    for row in normalized:
        identity = str(row.get("duplicate_identity"))
        if identity in exact:
            continue
        if any(_near_duplicate(row, prior) for prior in selected):
            continue
        exact.add(identity)
        selected.append(row)
    return selected


def _connect(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS news_event_ledger_20260618 (
            article_id TEXT PRIMARY KEY,
            duplicate_identity TEXT NOT NULL,
            publication_time TEXT NOT NULL,
            retrieval_time TEXT NOT NULL,
            source TEXT,
            headline TEXT NOT NULL,
            url TEXT,
            payload_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_news_event_pub_20260618 ON news_event_ledger_20260618(publication_time DESC)")
    return conn


def persist_articles(
    rows: Iterable[Mapping[str, Any]],
    *,
    db_path: Path | str = DEFAULT_DB_PATH,
    now: pd.Timestamp | None = None,
) -> int:
    """Persist genuine articles using one deterministic freshness reference."""
    articles = deduplicate_articles(rows, now=now)
    if not articles:
        return 0
    count = 0
    try:
        with _LOCK, _connect(db_path) as conn:
            for row in articles:
                conn.execute(
                    """INSERT INTO news_event_ledger_20260618(
                        article_id,duplicate_identity,publication_time,retrieval_time,source,headline,url,payload_json,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(article_id) DO UPDATE SET
                        duplicate_identity=excluded.duplicate_identity,
                        publication_time=excluded.publication_time,
                        retrieval_time=excluded.retrieval_time,
                        source=excluded.source,
                        headline=excluded.headline,
                        url=excluded.url,
                        payload_json=excluded.payload_json,
                        updated_at=excluded.updated_at""",
                    (
                        row["article_id"], row["duplicate_identity"], row["publication_time"],
                        row["retrieval_time"], row.get("source"), row["headline"], row.get("url"),
                        json.dumps(_safe_payload(row), ensure_ascii=False, default=str),
                        pd.Timestamp.now(tz="UTC").isoformat(),
                    ),
                )
                _MEMORY[row["article_id"]] = row
                count += 1
        return count
    except Exception:
        for row in articles:
            _MEMORY[row["article_id"]] = row
        return len(articles)


def load_recent_articles(*, days: int = 10, limit: int = 1000, db_path: Path | str = DEFAULT_DB_PATH, now: pd.Timestamp | None = None) -> list[dict[str, Any]]:
    current = pd.Timestamp(now or datetime.now(timezone.utc))
    current = current.tz_localize("UTC") if current.tzinfo is None else current.tz_convert("UTC")
    cutoff = current - pd.Timedelta(days=max(1, int(days)))
    rows: list[dict[str, Any]] = []
    try:
        with _LOCK, _connect(db_path) as conn:
            db_rows = conn.execute(
                "SELECT payload_json FROM news_event_ledger_20260618 WHERE publication_time>=? AND publication_time<=? ORDER BY publication_time DESC LIMIT ?",
                (cutoff.isoformat(), (current + pd.Timedelta(minutes=5)).isoformat(), int(limit)),
            ).fetchall()
        for item in db_rows:
            try:
                payload = json.loads(item["payload_json"])
                if isinstance(payload, dict): rows.append(payload)
            except Exception:
                continue
    except Exception:
        rows.extend(_MEMORY.values())
    return deduplicate_articles(rows, now=current)[: max(0, int(limit))]


__all__ = ["normalize_article", "deduplicate_articles", "persist_articles", "load_recent_articles"]
