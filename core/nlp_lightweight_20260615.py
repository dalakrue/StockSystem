"""Lightweight local NLP pipeline for 2026-06-15.

No external API, no downloads, no heavy model.  The functions below are
rule-based / optional-library safe helpers so Streamlit Cloud and phone mode do
not break when spaCy/NLTK models are absent.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
import streamlit as st

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "to", "of", "for", "from", "in", "on", "at", "by",
    "with", "without", "is", "are", "was", "were", "be", "been", "being", "am", "do", "does", "did", "can", "could",
    "should", "would", "will", "shall", "may", "might", "must", "i", "me", "my", "you", "your", "we", "our", "they",
    "their", "it", "its", "this", "that", "these", "those", "now", "please", "give", "tell", "show", "make", "want",
}

IRREGULAR_LEMMAS = {
    "went": "go", "gone": "go", "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "bought": "buy", "sold": "sell", "selling": "sell", "buying": "buy", "entries": "entry",
    "prices": "price", "candles": "candle", "signals": "signal", "regimes": "regime", "risks": "risk",
}

TRADING_TERMS = {
    "eurusd": "SYMBOL", "xauusd": "SYMBOL", "gbpusd": "SYMBOL", "usd": "CURRENCY", "eur": "CURRENCY",
    "buy": "DIRECTION", "sell": "DIRECTION", "wait": "DIRECTION", "tp": "TARGET", "sl": "RISK", "stoploss": "RISK",
    "entry": "TRADE_ACTION", "exit": "TRADE_ACTION", "regime": "MARKET_STATE", "risk": "RISK", "alpha": "METRIC", "delta": "METRIC",
}

TOPIC_KEYWORDS = {
    "entry": ["entry", "enter", "scalp", "buy", "sell", "long", "short"],
    "take_profit": ["tp", "target", "profit", "zone", "reach"],
    "risk_exit": ["risk", "exit", "protect", "close", "drawdown", "avoid"],
    "regime": ["regime", "bull", "bear", "range", "compression", "trend"],
    "prediction": ["prediction", "forecast", "path", "powerbi", "projection", "blue", "red"],
    "nlp": ["token", "stem", "lemma", "pos", "ner", "dependency", "summary", "topic"],
    "quality": ["accuracy", "confidence", "reliability", "quality", "agreement"],
}

WSD_SENSES = {
    "entry": "trading entry point / opening a position",
    "exit": "trade protection / close or reduce position",
    "risk": "probability and impact of bad trade outcome",
    "regime": "market state such as BULL, BEAR, RANGE, or COMPRESSION",
    "alpha": "difference/edge between two projection paths",
    "delta": "change from previous point to current point",
    "token": "NLP unit extracted from text",
}


def normalize_text(text: Any) -> str:
    s = str(text or "")
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
    s = re.sub(r"[^A-Za-z0-9_+\-./%:$@\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def sentence_split(text: Any) -> List[str]:
    raw = str(text or "")
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", raw) if p.strip()]
    return parts or ([normalize_text(raw)] if normalize_text(raw) else [])


def tokenize(text: Any) -> List[str]:
    s = normalize_text(text).lower()
    return re.findall(r"[a-z]+(?:'[a-z]+)?|\d+(?:\.\d+)?%?|[A-Z]{2,6}(?:/[A-Z]{2,6})?", s, flags=re.I)


def remove_stopwords(tokens: Iterable[str]) -> List[str]:
    return [t for t in tokens if str(t).lower() not in STOPWORDS and len(str(t).strip()) > 0]


def stem_token(token: str) -> str:
    t = str(token).lower()
    for suf in ("ization", "ational", "fulness", "iveness", "ingly", "edly", "ment", "ness", "tion", "ing", "ed", "ly", "es", "s"):
        if len(t) > len(suf) + 2 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def lemmatize_token(token: str) -> str:
    t = str(token).lower()
    if t in IRREGULAR_LEMMAS:
        return IRREGULAR_LEMMAS[t]
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 5 and t.endswith("ing"):
        base = t[:-3]
        return base[:-1] if len(base) > 2 and base[-1] == base[-2] else base
    if len(t) > 4 and t.endswith("ed"):
        return t[:-2]
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def pos_tag(tokens: Iterable[str]) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    verbs = {"buy", "sell", "wait", "enter", "exit", "close", "protect", "reach", "run", "calculate", "show", "add", "move"}
    adjectives = {"safe", "safer", "risky", "high", "low", "strong", "weak", "bull", "bear", "current", "next", "good", "bad"}
    for tok in tokens:
        t = str(tok).lower()
        if re.fullmatch(r"\d+(\.\d+)?%?", t):
            tag = "NUM"
        elif t in {"i", "you", "we", "it", "he", "she", "they", "this", "that"}:
            tag = "PRON"
        elif t in verbs or t.endswith("ing") or t.endswith("ed"):
            tag = "VERB"
        elif t in adjectives or t.endswith(("ive", "al", "ous", "ful", "less")):
            tag = "ADJ"
        elif t in STOPWORDS:
            tag = "STOP"
        elif t in TRADING_TERMS:
            tag = "NOUN"
        else:
            tag = "NOUN"
        out.append((str(tok), tag))
    return out


def dependency_parse(tokens: List[str], pos: List[Tuple[str, str]]) -> List[Dict[str, Any]]:
    if not tokens:
        return []
    verb_i = next((i for i, (_, tag) in enumerate(pos) if tag == "VERB"), 0)
    rows = []
    for i, tok in enumerate(tokens):
        if i == verb_i:
            rel, head = "ROOT", tok
        elif i < verb_i and pos[i][1] in {"NOUN", "PRON"}:
            rel, head = "nsubj", tokens[verb_i]
        elif i > verb_i and pos[i][1] in {"NOUN", "NUM"}:
            rel, head = "obj", tokens[verb_i]
        elif pos[i][1] == "ADJ":
            rel, head = "amod", tokens[min(i + 1, len(tokens)-1)]
        else:
            rel, head = "dep", tokens[verb_i]
        rows.append({"token": tok, "pos": pos[i][1], "head": head, "dependency": rel})
    return rows


def constituency_parse(tokens: List[str], pos: List[Tuple[str, str]]) -> Dict[str, Any]:
    chunks: List[Dict[str, str]] = []
    cur: List[str] = []
    cur_type = "NP"
    for tok, tag in pos:
        typ = "VP" if tag == "VERB" else "NP" if tag in {"NOUN", "PRON", "ADJ", "NUM"} else "O"
        if typ != cur_type and cur:
            chunks.append({"type": cur_type, "text": " ".join(cur)})
            cur = []
        cur_type = typ
        if typ != "O":
            cur.append(tok)
    if cur:
        chunks.append({"type": cur_type, "text": " ".join(cur)})
    return {"tree": "S(" + " ".join(f"{c['type']}[{c['text']}]" for c in chunks) + ")", "chunks": chunks}


def named_entities(text: Any, tokens: List[str]) -> List[Dict[str, Any]]:
    ents: List[Dict[str, Any]] = []
    raw = str(text or "")
    for m in re.finditer(r"\b[A-Z]{3,6}(?:/[A-Z]{3,6})?\b", raw):
        label = "SYMBOL" if any(x in m.group(0).replace("/", "") for x in ["EURUSD", "XAUUSD", "GBPUSD", "USDJPY"]) else "ORG_OR_SYMBOL"
        ents.append({"text": m.group(0), "label": label, "start": m.start(), "end": m.end()})
    for m in re.finditer(r"\b\d+\.\d{3,5}\b", raw):
        ents.append({"text": m.group(0), "label": "PRICE", "start": m.start(), "end": m.end()})
    for m in re.finditer(r"\b(?:BUY|SELL|WAIT|BULL|BEAR|RANGE|REGIME|TP|SL)\b", raw, flags=re.I):
        val = m.group(0).upper()
        ents.append({"text": m.group(0), "label": TRADING_TERMS.get(val.lower(), "TRADING_TERM"), "start": m.start(), "end": m.end()})
    for m in re.finditer(r"\b(?:next|last|within)\s+\d+\s*(?:h|hour|hours|minute|minutes|day|days)\b", raw, flags=re.I):
        ents.append({"text": m.group(0), "label": "TIME_WINDOW", "start": m.start(), "end": m.end()})
    seen = set()
    uniq = []
    for e in ents:
        key = (e["text"].lower(), e["label"], e.get("start", -1))
        if key not in seen:
            seen.add(key); uniq.append(e)
    return uniq


def word_sense_disambiguation(tokens: Iterable[str], topics: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    topic_names = {t.get("topic") for t in topics[:3]}
    rows = []
    for tok in tokens:
        lemma = lemmatize_token(tok)
        if lemma in WSD_SENSES:
            sense = WSD_SENSES[lemma]
            if lemma == "risk" and "entry" in topic_names:
                sense = "entry risk / whether the trade is safe now"
            rows.append({"word": tok, "lemma": lemma, "sense": sense})
    return rows


def coreference_resolution(sentences: List[str], entities: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    last_entity = entities[0]["text"] if entities else "current market setup"
    rows: List[Dict[str, str]] = []
    for sent in sentences:
        for pron in re.findall(r"\b(it|this|that|they|them|he|she)\b", sent, flags=re.I):
            rows.append({"mention": pron, "resolved_to": last_entity, "sentence": sent[:180]})
        sent_ents = named_entities(sent, tokenize(sent))
        if sent_ents:
            last_entity = sent_ents[-1]["text"]
    return rows


def mention_extraction(tokens: List[str], pos: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    cons = constituency_parse(tokens, pos)
    mentions = []
    for ch in cons.get("chunks", []):
        if ch.get("type") == "NP" and ch.get("text"):
            mentions.append({"mention": ch["text"], "type": "noun_phrase"})
    return mentions[:80]


def relation_extraction(tokens: List[str], pos: List[Tuple[str, str]]) -> List[Dict[str, str]]:
    deps = dependency_parse(tokens, pos)
    roots = [r for r in deps if r["dependency"] == "ROOT"]
    root = roots[0]["token"] if roots else (tokens[0] if tokens else "")
    subjects = [r["token"] for r in deps if r["dependency"] == "nsubj"] or ["user/system"]
    objects = [r["token"] for r in deps if r["dependency"] == "obj"] or ["current setup"]
    return [{"subject": subjects[0], "relation": root, "object": objects[0]}]


def entry_extraction(text: Any, tokens: List[str], entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Small trading-specific entity/entry extractor.

    The user often asks for entry, TP, BUY/SELL, and price levels. This is
    display-only NLP metadata; it does not create or change trading signals.
    """
    raw = str(text or "")
    rows: List[Dict[str, Any]] = []
    direction = "BUY" if re.search(r"\b(buy|long|bull)\b", raw, flags=re.I) else "SELL" if re.search(r"\b(sell|short|bear)\b", raw, flags=re.I) else "UNKNOWN"
    prices = re.findall(r"(?<!\d)(\d\.\d{3,6})(?!\d)", raw)
    horizons = re.findall(r"\b(?:next|within|last)?\s*\d+\s*(?:h|hour|hours|minute|minutes|day|days)\b", raw, flags=re.I)
    if direction != "UNKNOWN":
        rows.append({"field": "direction", "value": direction, "type": "trade_side"})
    for i, price in enumerate(prices[:6], 1):
        role = "entry_price" if re.search(r"\b(entry|entries|entered|enter)\b", raw, flags=re.I) and i <= 3 else "price_level"
        rows.append({"field": f"price_{i}", "value": price, "type": role})
    for i, h in enumerate(horizons[:4], 1):
        rows.append({"field": f"time_window_{i}", "value": h.strip(), "type": "horizon"})
    if any(t in {"tp", "target", "profit"} for t in [x.lower() for x in tokens]):
        rows.append({"field": "target_request", "value": "TP / take-profit requested", "type": "intent"})
    if any(t in {"risk", "exit", "protect", "sl", "stoploss"} for t in [x.lower() for x in tokens]):
        rows.append({"field": "risk_request", "value": "risk/exit protection requested", "type": "intent"})
    return rows


def topic_detection(lemmas: List[str]) -> List[Dict[str, Any]]:
    counts = Counter(lemmas)
    rows = []
    for topic, kws in TOPIC_KEYWORDS.items():
        score = sum(counts.get(k, 0) for k in kws)
        if score:
            rows.append({"topic": topic, "score": int(score), "keywords": ", ".join([k for k in kws if counts.get(k, 0)])})
    rows.sort(key=lambda r: (-r["score"], r["topic"]))
    if not rows:
        rows = [{"topic": "general", "score": 1, "keywords": "fallback"}]
    return rows


def summarize_text(sentences: List[str], lemmas: List[str], max_sentences: int = 2) -> str:
    if not sentences:
        return "No text available to summarize."
    counts = Counter([x for x in lemmas if x not in STOPWORDS])
    scored = []
    for i, sent in enumerate(sentences):
        toks = [lemmatize_token(t) for t in tokenize(sent)]
        score = sum(counts.get(t, 0) for t in toks) + (1.0 if i == 0 else 0.0)
        scored.append((score, i, sent))
    keep = sorted(scored, reverse=True)[:max_sentences]
    keep = sorted(keep, key=lambda x: x[1])
    return " ".join(k[2] for k in keep)


def generate_text(topics: List[Dict[str, Any]], entities: List[Dict[str, Any]], summary: str) -> str:
    topic = topics[0]["topic"] if topics else "general"
    ents = ", ".join(e["text"] for e in entities[:5]) or "current text"
    if topic in {"entry", "take_profit", "risk_exit", "regime", "prediction", "quality"}:
        return f"Generated local response seed: topic={topic}; entities={ents}. Use the existing trading metrics first, then explain the risk/confirmation before any BUY/SELL wording. Summary: {summary[:220]}"
    if topic == "nlp":
        return f"Generated local NLP note: text was normalized, tokenized, stemmed, lemmatized, tagged, parsed, and summarized. Main entities: {ents}."
    return f"Generated local response seed: main topic={topic}; entities={ents}; summary={summary[:220]}"


def run_lightweight_nlp(text: Any) -> Dict[str, Any]:
    normalized = normalize_text(text)
    sentences = sentence_split(normalized)
    tokens = tokenize(normalized)
    no_stop = remove_stopwords(tokens)
    stems = [stem_token(t) for t in no_stop]
    lemmas = [lemmatize_token(t) for t in no_stop]
    pos = pos_tag(tokens)
    deps = dependency_parse(tokens, pos)
    cons = constituency_parse(tokens, pos)
    ents = named_entities(str(text or ""), tokens)
    topics = topic_detection(lemmas)
    wsd = word_sense_disambiguation(no_stop, topics)
    coref = coreference_resolution(sentences, ents)
    mentions = mention_extraction(tokens, pos)
    entries = entry_extraction(str(text or ""), tokens, ents)
    relations = relation_extraction(tokens, pos)
    summary = summarize_text(sentences, lemmas, max_sentences=2)
    generated = generate_text(topics, ents, summary)
    token_rows = pd.DataFrame({
        "token": tokens,
        "stopword": [str(t).lower() in STOPWORDS for t in tokens],
        "stem": [stem_token(t) for t in tokens],
        "lemma": [lemmatize_token(t) for t in tokens],
        "pos": [tag for _, tag in pos],
    }) if tokens else pd.DataFrame(columns=["token", "stopword", "stem", "lemma", "pos"])
    return {
        "normalized_text": normalized,
        "sentences": sentences,
        "tokens": tokens,
        "tokens_without_stopwords": no_stop,
        "stems": stems,
        "lemmas": lemmas,
        "pos_tags": pos,
        "dependency_parse": deps,
        "constituency_parse": cons,
        "named_entities": ents,
        "word_sense_disambiguation": wsd,
        "coreference_resolution": coref,
        "mentions": mentions,
        "entities": ents,
        "entries": entries,
        "relations": relations,
        "topics": topics,
        "summary": summary,
        "generated_text": generated,
        "token_table": token_rows,
        "dependency_table": pd.DataFrame(deps),
        "entity_table": pd.DataFrame(ents),
        "topic_table": pd.DataFrame(topics),
        "entry_table": pd.DataFrame(entries),
        "relation_table": pd.DataFrame(relations),
        "mention_table": pd.DataFrame(mentions),
        "wsd_table": pd.DataFrame(wsd),
        "coref_table": pd.DataFrame(coref),
    }


def _show_table(df: pd.DataFrame, key: str, height: int = 230) -> None:
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.caption("No rows for this step yet.")
        return
    try:
        from ui.stable_ui_libs_20260615 import modern_table
        modern_table(df, key, height=height)
    except Exception:
        st.dataframe(df, use_container_width=True, hide_index=True, height=height)


def render_nlp_pipeline_panel(text: Any, key: str = "nlp_lightweight", *, title: str = "Local NLP Pipeline") -> Dict[str, Any]:
    st.markdown(f"#### 🧠 {title}")
    st.caption("Rule-based local NLP only: no external API, no downloads, no heavy model. Safe for Streamlit Cloud and phone mode.")
    sample = str(text or "").strip()
    if not sample:
        sample = "EURUSD H1 entry now? Need BUY or SELL TP plan and risk explanation."
    run_key = f"{key}_text"
    user_text = st.text_area("NLP text input", value=sample, height=110, key=run_key)
    result = run_lightweight_nlp(user_text)
    tabs = st.tabs([
        "Normalize", "Token/Stem/Lemma", "POS + Dependency", "Constituency", "NER/Entity/Entry",
        "WSD/Coref", "Mentions/Relations", "Topic", "Summary/Generation",
    ])
    with tabs[0]:
        st.text_area("Text normalization", result["normalized_text"], height=105, key=f"{key}_normalized")
        st.write({"sentence_count": len(result["sentences"]), "token_count": len(result["tokens"]), "content_tokens": len(result["tokens_without_stopwords"])})
    with tabs[1]:
        _show_table(result["token_table"], f"{key}_tokens", 280)
    with tabs[2]:
        _show_table(result["dependency_table"], f"{key}_deps", 280)
    with tabs[3]:
        st.code(result["constituency_parse"].get("tree", "S()"), language="text")
        _show_table(pd.DataFrame(result["constituency_parse"].get("chunks", [])), f"{key}_const", 220)
    with tabs[4]:
        _show_table(result["entity_table"], f"{key}_ents", 210)
        _show_table(result["entry_table"], f"{key}_entry_extract", 170)
    with tabs[5]:
        _show_table(result["wsd_table"], f"{key}_wsd", 200)
        _show_table(result["coref_table"], f"{key}_coref", 200)
    with tabs[6]:
        _show_table(result["mention_table"], f"{key}_mentions", 220)
        _show_table(result["relation_table"], f"{key}_relations", 180)
    with tabs[7]:
        _show_table(result["topic_table"], f"{key}_topics", 220)
    with tabs[8]:
        st.markdown("**Text summarization**")
        st.write(result["summary"])
        st.markdown("**Text generation seed**")
        st.write(result["generated_text"])
    st.session_state[f"{key}_result_20260615"] = result
    return result
