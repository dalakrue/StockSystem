"""2026-06-12 Data Visualization News/NLP intelligence upgrade.

Adds one run-gated open/close section under Data Visualization:
News + NLP confirmation, KNN/Greedy display priority, descriptive/predictive/
prescriptive cards, and an accuracy-adjusted projection overlay. It is additive:
Twelve Data remains the price source and News/NLP never overrides the Unified
PowerBI regime/direction.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json
    import math
    import re
    import time
    import xml.etree.ElementTree as ET
    from typing import Any, Dict, List, Tuple

    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    import requests
    import streamlit as st

    UNIQUE = "20260612_nlpdv"

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _safe(obj: Any, rows: int = 80) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(int(rows)).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe(v, rows=rows) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(x, rows=rows) for x in list(obj)[:rows]]
            return obj
        except Exception:
            return str(obj)

    def _json_text(payload: Dict[str, Any]) -> str:
        return json.dumps(_safe(payload, rows=120), indent=2, ensure_ascii=False, default=str)

    def _prepare_ohlc(limit: int = 2400) -> pd.DataFrame:
        raw = st.session_state.get("dv_pp_df")
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            raw = st.session_state.get("last_df")
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        if callable(prep):
            try:
                out = prep(raw, limit=int(limit))
                if isinstance(out, pd.DataFrame) and not out.empty:
                    return out.tail(int(limit)).reset_index(drop=True)
            except Exception:
                pass
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            return pd.DataFrame()
        d = raw.copy().tail(int(limit)).reset_index(drop=True)
        low = {str(c).strip().lower(): c for c in d.columns}
        rename = {}
        for old, new in {"datetime": "time", "date": "time", "timestamp": "time", "o": "open", "h": "high", "l": "low", "c": "close"}.items():
            if old in low and new not in d.columns:
                rename[low[old]] = new
        if rename:
            d = d.rename(columns=rename)
        if "close" not in d.columns:
            return pd.DataFrame()
        if "time" not in d.columns:
            d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        for c in ["open", "high", "low", "close", "volume"]:
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        if "open" not in d.columns:
            d["open"] = d["close"].shift(1).fillna(d["close"])
        if "high" not in d.columns:
            d["high"] = d[["open", "close"]].max(axis=1)
        if "low" not in d.columns:
            d["low"] = d[["open", "close"]].min(axis=1)
        return d.dropna(subset=["time", "open", "high", "low", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    def _master_regime() -> str:
        reg = st.session_state.get("dv_pp_regime_summary", {})
        if isinstance(reg, dict) and reg.get("current_regime"):
            return str(reg.get("current_regime"))
        pack = st.session_state.get("nylo_unified_home_sync_20260612", {})
        if isinstance(pack, dict):
            summ = pack.get("summary", {}) if isinstance(pack.get("summary"), dict) else {}
            if summ.get("current_powerbi_regime"):
                return str(summ.get("current_powerbi_regime"))
        return "RANGE_NORMAL"

    def _dir_from_regime(regime: Any) -> str:
        s = str(regime or "").upper()
        if "BEAR" in s:
            return "SELL"
        if "BULL" in s:
            return "BUY"
        return "WAIT"

    def _sentiment_score(text: str) -> float:
        txt = " " + re.sub(r"[^a-z0-9% ]+", " ", str(text).lower()) + " "
        try:
            from nltk.sentiment import SentimentIntensityAnalyzer  # optional only
            return float(SentimentIntensityAnalyzer().polarity_scores(txt).get("compound", 0.0))
        except Exception:
            positive = ["beat", "beats", "strong", "stronger", "rises", "rise", "hawkish", "growth", "hot", "higher", "improve", "improves", "surge", "upbeat"]
            negative = ["miss", "misses", "weak", "weaker", "falls", "fall", "dovish", "cut", "cuts", "recession", "cool", "lower", "slowdown", "slump", "risk"]
            p = sum(1 for w in positive if f" {w} " in txt)
            n = sum(1 for w in negative if f" {w} " in txt)
            return max(-1.0, min(1.0, (p - n) / max(3.0, p + n)))

    def _impact_article(article: Dict[str, Any]) -> Dict[str, Any]:
        title = str(article.get("headline") or article.get("title") or article.get("summary") or "")
        summary = str(article.get("summary") or article.get("description") or "")
        text = (title + " " + summary).lower()
        text_clean = " " + re.sub(r"[^a-z0-9% ]+", " ", text) + " "
        eur_pos = ["ecb hawkish", "ecb hike", "euro rises", "euro stronger", "euro up", "eurozone pmi beat", "german pmi beat", "eurozone inflation hot", "spanish inflation picks up", "french inflation accelerates", "germany inflation picked up", "euro area growth", "european traders steady", "euro supported"]
        eur_neg = ["ecb cut", "ecb dovish", "euro falls", "euro weaker", "euro down", "eurozone pmi miss", "german pmi miss", "eurozone recession", "french risk", "italy risk", "political risk", "eurozone demand weak"]
        usd_pos = ["fed hawkish", "fed hike", "dollar rises", "dollar stronger", "dollar up", "nfp beat", "jobs beat", "cpi hot", "treasury yields rise", "yield rises", "retail sales beat", "safe haven dollar", "geopolitical risk", "iran", "middle east conflict"]
        usd_neg = ["fed cut", "fed dovish", "dollar falls", "dollar weaker", "dollar down", "nfp miss", "jobs miss", "cpi cool", "treasury yields fall", "yield falls", "retail sales miss", "deal optimism", "risk rally"]
        high_topics = ["fed", "fomc", "ecb", "cpi", "nfp", "jobs", "pmi", "inflation", "interest rate", "rate cut", "rate hike", "treasury", "yield"]
        eur_score = 0.0
        usd_score = 0.0
        topic_hits = []
        for phrase in eur_pos:
            if phrase in text_clean:
                eur_score += 1.35
        for phrase in eur_neg:
            if phrase in text_clean:
                eur_score -= 1.35
        for phrase in usd_pos:
            if phrase in text_clean:
                usd_score += 1.35
        for phrase in usd_neg:
            if phrase in text_clean:
                usd_score -= 1.35
        for word in high_topics:
            if word in text_clean:
                topic_hits.append(word)
        # Broad keyword scoring prevents all-zero NLP tables from neutral headlines.
        if any(w in text_clean for w in [" euro ", " eur ", " eurozone ", " european ", "german", "french", "spanish", "ecb"]):
            eur_score += 0.18 + _sentiment_score(text_clean) * 0.55
        if any(w in text_clean for w in [" dollar ", " usd ", " fed ", " treasury ", "yield", "us ", "u s ", "nfp", "cpi"]):
            usd_score += 0.18 + _sentiment_score(text_clean) * 0.55
        if any(w in text_clean for w in ["iran", "geopolitical", "conflict", "oil", "risk off", "safe haven"]):
            usd_score += 0.45
        if any(w in text_clean for w in ["inflation picks up", "inflation accelerates", "core inflation", "services inflation"]):
            eur_score += 0.55 if any(w in text_clean for w in ["spanish", "french", "german", "eurozone", "european"]) else 0.15
        delta = eur_score - usd_score
        direction = "BUY" if delta >= 0.80 else "SELL" if delta <= -0.80 else "WAIT"
        impact = "HIGH" if len(topic_hits) >= 2 else "MEDIUM" if topic_hits else "LOW"
        try:
            ts = article.get("datetime") or article.get("publishedDate") or article.get("pubDate") or article.get("date")
            if isinstance(ts, (int, float)):
                age_hours = max(0.0, (time.time() - float(ts)) / 3600.0)
            else:
                t = pd.to_datetime(ts, errors="coerce", utc=True)
                age_hours = 999.0 if pd.isna(t) else max(0.0, (pd.Timestamp.utcnow() - t).total_seconds() / 3600.0)
        except Exception:
            age_hours = 999.0
        freshness = "FRESH" if age_hours <= 8 else "RECENT" if age_hours <= 48 else "OLD"
        priority_weight = (2.0 if impact == "HIGH" else 1.25 if impact == "MEDIUM" else 0.75) * (1.0 if freshness == "FRESH" else 0.70 if freshness == "RECENT" else 0.35)
        return {
            "title": title[:220],
            "source": str(article.get("source") or article.get("site") or article.get("category") or "news"),
            "published": str(article.get("datetime") or article.get("publishedDate") or article.get("pubDate") or article.get("date") or ""),
            "url": str(article.get("url") or ""),
            "EUR Impact Score": round(eur_score, 3),
            "USD Impact Score": round(usd_score, 3),
            "EURUSD News Direction": direction,
            "Impact": impact,
            "Freshness": freshness,
            "Priority Weight": round(priority_weight, 3),
            "Static Impact Note": ("EUR stronger / USD weaker supports BUY" if direction == "BUY" else "EUR weaker / USD stronger supports SELL" if direction == "SELL" else "mixed or low-impact headline -> WAIT"),
            "Detected Topics": ", ".join(topic_hits[:8]) if topic_hits else "general",
        }

    def _fetch_finnhub(api_key: str, limit: int) -> Tuple[List[Dict[str, Any]], str]:
        if not api_key:
            return [], "Finnhub key empty"
        r = requests.get("https://finnhub.io/api/v1/news", params={"category": "forex", "token": api_key}, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return [], "Finnhub returned non-list payload"
        return data[: int(limit)], "Finnhub forex news"

    def _fetch_fmp(api_key: str, limit: int) -> Tuple[List[Dict[str, Any]], str]:
        if not api_key:
            return [], "FMP key empty"
        url = "https://financialmodelingprep.com/stable/news/forex"
        r = requests.get(url, params={"apikey": api_key, "limit": int(limit)}, timeout=8)
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, list):
            return [], "FMP returned non-list payload"
        mapped = []
        for row in data[: int(limit)]:
            if isinstance(row, dict):
                mapped.append({
                    "headline": row.get("title") or row.get("headline"),
                    "summary": row.get("text") or row.get("summary"),
                    "url": row.get("url"),
                    "publishedDate": row.get("publishedDate") or row.get("date"),
                    "source": row.get("site") or "FMP",
                })
        return mapped, "FMP forex news"

    def _fetch_rss(limit: int) -> Tuple[List[Dict[str, Any]], str]:
        feeds = [
            "https://www.forexlive.com/feed/news/",
            "https://www.fxstreet.com/rss/news",
            "https://www.investing.com/rss/news_1.rss",
        ]
        rows: List[Dict[str, Any]] = []
        for url in feeds:
            try:
                r = requests.get(url, timeout=7, headers={"User-Agent": "Mozilla/5.0"})
                if r.status_code >= 400:
                    continue
                root = ET.fromstring(r.content)
                for item in root.findall(".//item"):
                    title = item.findtext("title") or ""
                    desc = item.findtext("description") or ""
                    link = item.findtext("link") or ""
                    pub = item.findtext("pubDate") or ""
                    rows.append({"headline": title, "summary": desc, "url": link, "pubDate": pub, "source": url.split("/")[2]})
                    if len(rows) >= int(limit):
                        return rows, "RSS fallback"
            except Exception:
                continue
        return rows[: int(limit)], "RSS fallback"

    def _fetch_news(source_mode: str, finnhub_key: str, fmp_key: str, limit: int) -> Tuple[List[Dict[str, Any]], str, str]:
        errors = []
        order = []
        if source_mode == "Finnhub first":
            order = ["finnhub", "fmp", "rss"]
        elif source_mode == "FMP first":
            order = ["fmp", "finnhub", "rss"]
        else:
            order = ["rss"]
        for src in order:
            try:
                if src == "finnhub":
                    rows, label = _fetch_finnhub(finnhub_key, limit)
                elif src == "fmp":
                    rows, label = _fetch_fmp(fmp_key, limit)
                else:
                    rows, label = _fetch_rss(limit)
                if rows:
                    return rows, label, ""
                errors.append(f"{src}: empty")
            except Exception as exc:
                errors.append(f"{src}: {exc}")
        return [], "no news source", "; ".join(errors[-3:])

    def _news_nlp_pack(news_rows: List[Dict[str, Any]], source_label: str, master_dir: str, limit: int) -> Dict[str, Any]:
        keywords = ("eurusd", "eur/usd", "euro", "eur ", " eurozone", "ecb", "fed", "fomc", "dollar", "usd", "cpi", "nfp", "pmi", "treasury", "yield", "inflation", "jobs")
        filtered = []
        for row in news_rows:
            text = (str(row.get("headline") or row.get("title") or "") + " " + str(row.get("summary") or row.get("description") or "")).lower()
            if any(k in text for k in keywords):
                filtered.append(row)
        if not filtered:
            filtered = news_rows[: int(limit)]
        scored = [_impact_article(x) for x in filtered[: int(limit)]]
        table = pd.DataFrame(scored)
        if table.empty:
            summary = {"ok": False, "source": source_label, "message": "No EURUSD-related news found", "news_direction": "WAIT", "news_relationship": "LOW PRIORITY"}
            return {"summary": summary, "news_table": table}
        w = pd.to_numeric(table["Priority Weight"], errors="coerce").fillna(1.0)
        eur = float((pd.to_numeric(table["EUR Impact Score"], errors="coerce").fillna(0.0) * w).sum() / max(w.sum(), 1e-9))
        usd = float((pd.to_numeric(table["USD Impact Score"], errors="coerce").fillna(0.0) * w).sum() / max(w.sum(), 1e-9))
        delta = eur - usd
        news_dir = "BUY" if delta >= 0.55 else "SELL" if delta <= -0.55 else "WAIT"
        if news_dir == "WAIT":
            relation = "NEUTRAL"
        elif master_dir in {"BUY", "SELL"} and news_dir == master_dir:
            relation = "CONFIRM"
        elif master_dir in {"BUY", "SELL"} and news_dir != master_dir:
            relation = "CONFLICT"
        else:
            relation = "LOW PRIORITY"
        high_count = int((table["Impact"].astype(str) == "HIGH").sum())
        fresh_count = int((table["Freshness"].astype(str) == "FRESH").sum())
        summary = {
            "ok": True,
            "source": source_label,
            "articles_used": int(len(table)),
            "news_direction": news_dir,
            "news_relationship_to_powerbi": relation,
            "weighted_eur_impact": round(eur, 3),
            "weighted_usd_impact": round(usd, 3),
            "eur_minus_usd": round(delta, 3),
            "high_impact_news_count": high_count,
            "fresh_news_count": fresh_count,
            "rule": "News/NLP confirms or warns only; it cannot override Unified PowerBI direction.",
        }
        return {"summary": summary, "news_table": table.sort_values(["Freshness", "Priority Weight"], ascending=[True, False]).reset_index(drop=True)}

    def _market_quality(d: pd.DataFrame, bt: Dict[str, Any], relation: str) -> float:
        err = _num((bt or {}).get("avg_abs_close_error_pct", 0.08), 0.08)
        acc = _num((bt or {}).get("direction_accuracy_pct", 50), 50)
        vol_pen = 0.0
        if isinstance(d, pd.DataFrame) and len(d) > 30:
            ret = pd.to_numeric(d["close"], errors="coerce").pct_change().abs().tail(24).mean()
            vol_pen = min(25.0, float(ret or 0.0) * 26000.0)
        bonus = 8.0 if relation == "CONFIRM" else -12.0 if relation == "CONFLICT" else 0.0
        return max(0.0, min(100.0, 45.0 + acc * 0.35 - err * 95.0 - vol_pen + bonus))

    def _build_adjusted_projection(d: pd.DataFrame, pred: pd.DataFrame, summary: Dict[str, Any], master_dir: str, bt: Dict[str, Any]) -> pd.DataFrame:
        if not isinstance(d, pd.DataFrame) or d.empty or "close" not in d.columns:
            return pd.DataFrame()
        last = float(pd.to_numeric(d["close"], errors="coerce").dropna().iloc[-1])
        p = pred.copy() if isinstance(pred, pd.DataFrame) else pd.DataFrame()
        if p.empty:
            return pd.DataFrame()
        lower = {str(c).lower(): c for c in p.columns}
        close_col = next((lower.get(k) for k in ["predicted_close", "close", "projected close", "prediction close"] if lower.get(k) is not None), None)
        if close_col is None:
            nums = p.select_dtypes(include="number").columns.tolist()
            close_col = nums[-1] if nums else None
        if close_col is None:
            return pd.DataFrame()
        out = p.head(12).copy().reset_index(drop=True)
        raw = pd.to_numeric(out[close_col], errors="coerce").ffill().fillna(last)
        err_pct = _num((bt or {}).get("avg_abs_close_error_pct", 0.08), 0.08)
        accuracy_weight = max(0.45, min(1.0, 1.0 - err_pct * 2.75))
        atr = float((pd.to_numeric(d["high"], errors="coerce") - pd.to_numeric(d["low"], errors="coerce")).tail(14).mean()) if {"high", "low"}.issubset(d.columns) else abs(last) * 0.0008
        atr = max(atr, abs(last) * 0.00035, 0.00001)
        rel = str(summary.get("news_relationship_to_powerbi", "NEUTRAL"))
        dir_sign = 1 if master_dir == "BUY" else -1 if master_dir == "SELL" else 0
        shift_mult = 0.12 if rel == "CONFIRM" else -0.08 if rel == "CONFLICT" else 0.0
        steps = np.arange(1, len(out) + 1, dtype=float)
        adjusted = last + (raw - last) * accuracy_weight + dir_sign * atr * shift_mult * np.sqrt(steps)
        band = atr * (1.0 + err_pct * 12.0) * np.sqrt(steps)
        out["Raw Projection Close"] = raw.round(5)
        out["Accuracy Adjusted Close"] = pd.Series(adjusted).round(5)
        out["Accuracy Adjusted Upper"] = pd.Series(adjusted + band).round(5)
        out["Accuracy Adjusted Lower"] = pd.Series(adjusted - band).round(5)
        out["Backtest Accuracy Weight"] = round(float(accuracy_weight), 3)
        out["News Sync"] = rel
        return out

    def _knn_greedy_priority(d: pd.DataFrame, adjusted: pd.DataFrame, master_dir: str, nlp_summary: Dict[str, Any], bt: Dict[str, Any]) -> pd.DataFrame:
        if not isinstance(d, pd.DataFrame) or len(d) < 60 or not isinstance(adjusted, pd.DataFrame) or adjusted.empty:
            return pd.DataFrame()
        x = d.copy().reset_index(drop=True)
        close = pd.to_numeric(x["close"], errors="coerce")
        ret1 = close.pct_change().fillna(0)
        ret3 = close.pct_change(3).fillna(0)
        vol = ret1.abs().rolling(12, min_periods=3).mean().fillna(0)
        one_hour_return = close.pct_change()
        completed_next_return = pd.Series(list(one_hour_return.iloc[1:]) + [np.nan], index=close.index, dtype=float)
        base = pd.DataFrame({"ret1": ret1, "ret3": ret3, "vol": vol, "next_ret": completed_next_return})
        cur = base[["ret1", "ret3", "vol"]].iloc[-1].to_numpy(dtype=float)
        hist = base.iloc[:-2].dropna().copy()
        if hist.empty:
            knn_buy_prob = 50.0
            avg_move = 0.0
        else:
            mat = hist[["ret1", "ret3", "vol"]].to_numpy(dtype=float)
            dist = np.sqrt(((mat - cur) ** 2).sum(axis=1))
            hist["dist"] = dist
            top = hist.nsmallest(min(25, len(hist)), "dist")
            knn_buy_prob = float((top["next_ret"] > 0).mean() * 100.0)
            avg_move = float(top["next_ret"].mean())
        master_prob = knn_buy_prob if master_dir == "BUY" else (100.0 - knn_buy_prob if master_dir == "SELL" else 50.0)
        relation = str(nlp_summary.get("news_relationship_to_powerbi", "NEUTRAL"))
        err = _num((bt or {}).get("avg_abs_close_error_pct", 0.08), 0.08)
        mquality = _market_quality(d, bt, relation)
        rows = []
        last = float(close.dropna().iloc[-1])
        for i, row in adjusted.head(6).iterrows():
            adj = _num(row.get("Accuracy Adjusted Close"), last)
            raw_dir = "BUY" if adj > last else "SELL" if adj < last else "WAIT"
            confirm_bonus = 18 if relation == "CONFIRM" else -20 if relation == "CONFLICT" else 0
            dir_bonus = 16 if raw_dir == master_dir else -18 if raw_dir in {"BUY", "SELL"} and master_dir in {"BUY", "SELL"} else 0
            decay = max(0, 9 - int(i) * 1.3)
            score = max(0.0, min(100.0, master_prob * 0.28 + mquality * 0.33 + (100.0 - err * 200.0) * 0.14 + confirm_bonus + dir_bonus + decay))
            if score >= 72 and relation != "CONFLICT":
                decision = f"{master_dir} allowed" if master_dir in {"BUY", "SELL"} else "WATCH"
            elif relation == "CONFLICT":
                decision = "Conflict: no trade"
            elif score >= 58:
                decision = "Watch / wait pullback"
            else:
                decision = "Avoid entry"
            rows.append({
                "Priority Rank": i + 1,
                "Step": i + 1,
                "Master Direction": master_dir,
                "Adjusted Direction": raw_dir,
                "KNN Similarity Direction Prob": round(master_prob, 1),
                "Greedy Priority Score": round(score, 1),
                "Average Historical Move": round(avg_move, 6),
                "Reason Label": f"{relation} + PowerBI {master_dir} + quality {mquality:.0f}",
                "Prescriptive Label": decision,
                "Adjusted Price": round(adj, 5),
            })
        return pd.DataFrame(rows).sort_values("Greedy Priority Score", ascending=False).reset_index(drop=True)

    def _build_story(d: pd.DataFrame, adjusted: pd.DataFrame, priority: pd.DataFrame, nlp: Dict[str, Any], master_regime: str, master_dir: str, bt: Dict[str, Any]) -> Dict[str, Any]:
        summary = nlp.get("summary", {}) if isinstance(nlp, dict) else {}
        relation = str(summary.get("news_relationship_to_powerbi", "NEUTRAL"))
        mquality = _market_quality(d, bt, relation)
        err = _num((bt or {}).get("avg_abs_close_error_pct", 0.0), 0.0)
        acc = _num((bt or {}).get("direction_accuracy_pct", 0.0), 0.0)
        last = _num(pd.to_numeric(d["close"], errors="coerce").dropna().iloc[-1], 0.0) if isinstance(d, pd.DataFrame) and not d.empty else 0.0
        if isinstance(adjusted, pd.DataFrame) and not adjusted.empty:
            nxt = _num(adjusted.iloc[0].get("Accuracy Adjusted Close"), last)
            upper = _num(adjusted.iloc[0].get("Accuracy Adjusted Upper"), nxt)
            lower = _num(adjusted.iloc[0].get("Accuracy Adjusted Lower"), nxt)
        else:
            nxt, upper, lower = last, last, last
        cont = max(5.0, min(95.0, 50.0 + (12.0 if relation == "CONFIRM" else -18.0 if relation == "CONFLICT" else 0.0) + (mquality - 50.0) * 0.42 + (acc - 50.0) * 0.18))
        rev = round(100.0 - cont, 1)
        if relation == "CONFLICT":
            prescriptive = "Conflict: no trade / protect position"
        elif master_dir in {"BUY", "SELL"} and cont >= 58:
            prescriptive = f"{master_dir} allowed only after normal entry confirmation"
        elif master_dir == "WAIT":
            prescriptive = "WAIT / range confirmation needed"
        else:
            prescriptive = "WATCH / wait for pullback"
        story = f"Unified PowerBI regime is {master_regime}, so master direction is {master_dir}. News/NLP is {relation} with {summary.get('news_direction','WAIT')} pressure. Market quality is {mquality:.0f}/100 and prediction close error is {err:.4f}%."
        return {
            "descriptive": {
                "Current Market Story": story,
                "Master Regime": master_regime,
                "Master Direction": master_dir,
                "Conflict Status": relation,
                "Market Quality": round(mquality, 1),
                "News Pressure": summary.get("news_direction", "WAIT"),
                "Current Prediction Error": f"{err:.4f}%",
                "Volatility State": "High / protect" if mquality < 45 else "Normal" if mquality < 70 else "Clean / usable",
            },
            "predictive": {
                "Next 1H Reasonable Direction": master_dir,
                "Next 1H Reasonable Price": round(nxt, 5),
                "Next 1H Range": f"{round(lower,5)} → {round(upper,5)}",
                "Regime Continuation Probability": round(cont, 1),
                "Reversal Warning": f"{rev}%",
                "Prediction Confidence": round((cont + mquality) / 2.0, 1),
            },
            "prescriptive": {
                "Action Label": prescriptive,
                "Rule": "News confirms/warns only. One Unified PowerBI remains master.",
                "Best Opportunity": priority.iloc[0].to_dict() if isinstance(priority, pd.DataFrame) and not priority.empty else {},
            },
        }

    def _update_visual_export(extra_payload: Dict[str, Any]) -> str:
        existing = st.session_state.get("lunch_visualization_export", "")
        payload: Any
        if isinstance(existing, str) and existing.strip():
            try:
                payload = json.loads(existing)
            except Exception:
                payload = {"previous_visualization_export_text": existing[:20000]}
        elif isinstance(existing, dict):
            payload = existing
        else:
            payload = {"export_type": "DATA_VISUALIZATION_EXPORT_WITH_NLP_20260612"}
        if not isinstance(payload, dict):
            payload = {"previous_visualization_export": payload}
        payload["news_nlp_knn_greedy_intelligence_20260612"] = _safe(extra_payload, rows=120)
        text = _json_text(payload)
        st.session_state["lunch_visualization_export"] = text
        st.session_state["dv_news_nlp_export_text_20260612"] = _json_text(extra_payload)
        return text

    def _run_news_nlp(source_mode: str, finnhub_key: str, fmp_key: str, limit: int, cache_min: int) -> Dict[str, Any]:
        fingerprint = (source_mode, bool(finnhub_key), bool(fmp_key), int(limit))
        cached = st.session_state.get("dv_news_nlp_cache_20260612")
        now = time.time()
        if isinstance(cached, dict) and cached.get("fingerprint") == fingerprint and now - float(cached.get("time", 0)) < int(cache_min) * 60:
            return cached.get("payload", {})
        news_rows, source_label, err = _fetch_news(source_mode, finnhub_key, fmp_key, int(limit))
        regime = _master_regime()
        master_dir = _dir_from_regime(regime)
        nlp = _news_nlp_pack(news_rows, source_label, master_dir, int(limit))
        if err:
            nlp.setdefault("summary", {})["fetch_warning"] = err
        d = _prepare_ohlc(limit=2400)
        pred = st.session_state.get("dv_pp_predicted", pd.DataFrame())
        bt = st.session_state.get("dv_pp_bt_summary", {}) or {}
        adjusted = _build_adjusted_projection(d, pred if isinstance(pred, pd.DataFrame) else pd.DataFrame(), nlp.get("summary", {}), master_dir, bt)
        priority = _knn_greedy_priority(d, adjusted, master_dir, nlp.get("summary", {}), bt)
        story = _build_story(d, adjusted, priority, nlp, regime, master_dir, bt)
        payload = {
            "export_type": "DATA_VISUALIZATION_NEWS_NLP_KNN_GREEDY_20260612",
            "built_at": str(pd.Timestamp.now()),
            "news_source": source_label,
            "symbol": st.session_state.get("symbol", "EURUSD"),
            "timeframe": st.session_state.get("timeframe", "H1"),
            "master_regime": regime,
            "master_direction": master_dir,
            "news_nlp_summary": nlp.get("summary", {}),
            "news_table": nlp.get("news_table", pd.DataFrame()),
            "descriptive_analysis": story.get("descriptive", {}),
            "predictive_analysis": story.get("predictive", {}),
            "prescriptive_analysis": story.get("prescriptive", {}),
            "accuracy_adjusted_projection": adjusted,
            "knn_greedy_priority": priority,
        }
        st.session_state["dv_news_nlp_pack_20260612"] = payload
        st.session_state["dv_news_nlp_cache_20260612"] = {"fingerprint": fingerprint, "time": now, "payload": payload}
        _update_visual_export(payload)
        return payload

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, text, key)
        except Exception:
            st.text_area(label, text, height=240, key=key + "_fallback")

    def _render_projection_chart(adjusted: pd.DataFrame) -> None:
        if not isinstance(adjusted, pd.DataFrame) or adjusted.empty:
            st.info("Run News/NLP after Data Visualization projection is ready to show the accuracy-adjusted projection path.")
            return
        fig = go.Figure()
        x = adjusted.index + 1
        fig.add_trace(go.Scatter(x=x, y=adjusted["Raw Projection Close"], mode="lines+markers", name="Original projection close"))
        fig.add_trace(go.Scatter(x=x, y=adjusted["Accuracy Adjusted Close"], mode="lines+markers", name="NLP + backtest adjusted close"))
        fig.add_trace(go.Scatter(x=x, y=adjusted["Accuracy Adjusted Upper"], mode="lines", name="Adjusted upper band"))
        fig.add_trace(go.Scatter(x=x, y=adjusted["Accuracy Adjusted Lower"], mode="lines", name="Adjusted lower band"))
        fig.update_layout(height=380, margin=dict(l=8, r=8, t=30, b=8), xaxis_title="Future step", yaxis_title="EURUSD price", xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "responsive": True})

    def _render_news_nlp_section(location: str = "Data Visualization") -> None:
        with st.expander("📰 Open / Close — News NLP + KNN/Greedy Priority + Accuracy-Adjusted Projection", expanded=False):
            st.caption("Manual-run only. Twelve Data remains the price source. Finnhub/FMP/RSS news is used only as confirmation/conflict filter, never as the master direction.")
            top = st.columns([1.1, 1.1, .9, .65])
            with top[0]:
                try:
                    from core.finnhub_connector import connection_status, get_session_key
                    _fh = connection_status(); finnhub_key = get_session_key()
                    st.metric("Finnhub", "CONNECTED" if _fh.get("connected") else "DISCONNECTED", _fh.get("availability", "UNKNOWN"))
                    st.caption("Connect or disconnect only in the sidebar connector.")
                except Exception:
                    finnhub_key = ""
                    st.metric("Finnhub", "DISCONNECTED", "Use sidebar connector")
            with top[1]:
                fmp_key = st.text_input("FMP API key backup", value=st.session_state.get("dv_nlp_fmp_key_saved", ""), type="password", key=f"dv_nlp_fmp_key_{UNIQUE}")
                st.session_state["dv_nlp_fmp_key_saved"] = fmp_key
            with top[2]:
                source_mode = st.selectbox("News source", ["Finnhub first", "FMP first", "RSS only"], key=f"dv_nlp_source_{UNIQUE}")
                limit = st.selectbox("News limit", [8, 12, 20, 30], index=1, key=f"dv_nlp_limit_{UNIQUE}")
            with top[3]:
                cache_min = st.selectbox("Cache", [30, 45, 60], index=2, key=f"dv_nlp_cache_{UNIQUE}")
                run = st.button("▶ Run News/NLP", use_container_width=True, key=f"dv_nlp_run_{UNIQUE}")
            if run:
                with st.spinner("Fetching news and building NLP confirmation / KNN+Greedy priority…"):
                    payload = _run_news_nlp(source_mode, finnhub_key.strip(), fmp_key.strip(), int(limit), int(cache_min))
                if isinstance(payload, dict) and payload.get("news_nlp_summary", {}).get("ok"):
                    st.success("News/NLP intelligence is ready and included in copy exports.")
                else:
                    st.warning((payload.get("news_nlp_summary", {}) if isinstance(payload, dict) else {}).get("message", "News/NLP did not find usable news."))
            payload = st.session_state.get("dv_news_nlp_pack_20260612", {})
            if not isinstance(payload, dict) or not payload:
                st.info("Press **Run News/NLP**. No API/news request runs on page load.")
                return
            s = payload.get("news_nlp_summary", {}) if isinstance(payload.get("news_nlp_summary"), dict) else {}
            desc = payload.get("descriptive_analysis", {}) if isinstance(payload.get("descriptive_analysis"), dict) else {}
            pred = payload.get("predictive_analysis", {}) if isinstance(payload.get("predictive_analysis"), dict) else {}
            pres = payload.get("prescriptive_analysis", {}) if isinstance(payload.get("prescriptive_analysis"), dict) else {}
            c = st.columns(6)
            c[0].metric("Master Regime", payload.get("master_regime", "-"))
            c[1].metric("Master Direction", payload.get("master_direction", "WAIT"))
            c[2].metric("News Direction", s.get("news_direction", "WAIT"))
            c[3].metric("News Sync", s.get("news_relationship_to_powerbi", "NEUTRAL"))
            c[4].metric("Next 1H Price", pred.get("Next 1H Reasonable Price", "-"))
            c[5].metric("Action", pres.get("Action Label", "WAIT"))
            st.info(desc.get("Current Market Story", "No descriptive story ready."))
            tabs = st.tabs(["Projection", "KNN + Greedy", "News Table", "D/P/P", "Copy"])
            with tabs[0]:
                adjusted = payload.get("accuracy_adjusted_projection", pd.DataFrame())
                _render_projection_chart(adjusted if isinstance(adjusted, pd.DataFrame) else pd.DataFrame())
                if isinstance(adjusted, pd.DataFrame) and not adjusted.empty:
                    st.dataframe(adjusted.head(12), use_container_width=True, hide_index=True, height=260)
            with tabs[1]:
                pr = payload.get("knn_greedy_priority", pd.DataFrame())
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr.head(8), use_container_width=True, hide_index=True, height=300)
                    b1, b2 = st.columns(2)
                    b1.metric("Best Opportunity #1", pr.iloc[0].get("Prescriptive Label", "-"), f"Score {pr.iloc[0].get('Greedy Priority Score','-')}")
                    if len(pr) > 1:
                        b2.metric("Best Opportunity #2", pr.iloc[1].get("Prescriptive Label", "-"), f"Score {pr.iloc[1].get('Greedy Priority Score','-')}")
                else:
                    st.info("KNN/Greedy priority needs projection output and at least 60 existing candles.")
            with tabs[2]:
                nt = payload.get("news_table", pd.DataFrame())
                if isinstance(nt, pd.DataFrame) and not nt.empty:
                    st.dataframe(nt.head(20), use_container_width=True, hide_index=True, height=340)
                else:
                    st.info("No scored news table available.")
            with tabs[3]:
                st.json({"descriptive": desc, "predictive": pred, "prescriptive": pres})
            with tabs[4]:
                full_text = _update_visual_export(payload)
                compact = _json_text({
                    "master_regime": payload.get("master_regime"),
                    "master_direction": payload.get("master_direction"),
                    "news_nlp_summary": s,
                    "descriptive": desc,
                    "predictive": pred,
                    "prescriptive": pres,
                    "knn_greedy_top": _safe(payload.get("knn_greedy_priority", pd.DataFrame()), rows=8),
                })
                cc = st.columns(2)
                with cc[0]:
                    _copy_button("Copy News/NLP Compact", compact, f"copy_dv_nlp_compact_{UNIQUE}")
                with cc[1]:
                    _copy_button("Copy Data Visualization Full + News/NLP", full_text, f"copy_dv_nlp_full_{UNIQUE}")

    prev_dv = ns.get("_render_lunch_data_visualization_inner_tab")

    def _render_dv_with_news_nlp() -> None:
        if callable(prev_dv):
            prev_dv()
        _render_news_nlp_section("Data Visualization")

    prev_copy = ns.get("_build_lunch_all_copy_text")

    def _build_copy_with_news_nlp() -> str:
        base = prev_copy() if callable(prev_copy) else ""
        extra = st.session_state.get("dv_news_nlp_export_text_20260612", "")
        if not extra:
            pack = st.session_state.get("dv_news_nlp_pack_20260612", {})
            extra = _json_text(pack) if isinstance(pack, dict) and pack else "News/NLP not run yet."
        return str(base) + "\n\nDATA VISUALIZATION NEWS NLP + KNN/GREEDY 2026-06-12\n" + "=" * 64 + "\n" + str(extra)

    prev_finder = ns.get("_render_doo_finder")

    def _render_finder_with_news_nlp(results=None):
        if callable(prev_finder):
            try:
                prev_finder(results)
            except TypeError:
                prev_finder()
        try:
            with st.expander("📰 Finder Sync — News NLP + Data Visualization Priority", expanded=False):
                pack = st.session_state.get("dv_news_nlp_pack_20260612", {})
                if not isinstance(pack, dict) or not pack:
                    st.info("Run Data Visualization → News/NLP first. Finder will mirror master regime, news sync, and KNN/Greedy priority here.")
                    return
                s = pack.get("news_nlp_summary", {}) if isinstance(pack.get("news_nlp_summary"), dict) else {}
                p = pack.get("prescriptive_analysis", {}) if isinstance(pack.get("prescriptive_analysis"), dict) else {}
                pr = pack.get("knn_greedy_priority", pd.DataFrame())
                c = st.columns(4)
                c[0].metric("PowerBI Master", pack.get("master_regime", "-"))
                c[1].metric("Master Direction", pack.get("master_direction", "WAIT"))
                c[2].metric("News Sync", s.get("news_relationship_to_powerbi", "NEUTRAL"))
                c[3].metric("Finder Action", p.get("Action Label", "WAIT"))
                if isinstance(pr, pd.DataFrame) and not pr.empty:
                    st.dataframe(pr.head(6), use_container_width=True, hide_index=True, height=230)
        except Exception as exc:
            st.caption(f"Finder News/NLP sync skipped safely: {exc}")

    ns["_render_lunch_data_visualization_inner_tab"] = _render_dv_with_news_nlp
    ns["_build_lunch_all_copy_text"] = _build_copy_with_news_nlp
    ns["_render_doo_finder"] = _render_finder_with_news_nlp
    ns["_render_dv_news_nlp_section_20260612"] = _render_news_nlp_section
