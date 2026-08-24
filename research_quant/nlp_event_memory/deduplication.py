from __future__ import annotations
from hashlib import sha256
import re
from typing import Iterable, Mapping


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", str(value).lower())).strip()

def text_hash(value: str) -> str:
    return sha256(normalize_text(value).encode("utf-8")).hexdigest()

def classify_duplicate(current: Mapping, history: Iterable[Mapping], *, similarity_threshold: float = 0.90) -> str:
    title = normalize_text(str(current.get("headline") or current.get("title") or ""))
    body = normalize_text(str(current.get("text") or current.get("summary") or ""))
    current_hash = text_hash(title + " " + body)
    title_tokens = set(title.split())
    for item in history:
        other_title = normalize_text(str(item.get("headline") or item.get("title") or ""))
        other_body = normalize_text(str(item.get("text") or item.get("summary") or ""))
        if text_hash(other_title + " " + other_body) == current_hash:
            return "DUPLICATE"
        other_tokens = set(other_title.split())
        union = title_tokens | other_tokens
        similarity = len(title_tokens & other_tokens) / len(union) if union else 0.0
        if similarity >= similarity_threshold:
            return "UPDATED_EVENT" if body != other_body else "RELATED"
    return "NEW"
