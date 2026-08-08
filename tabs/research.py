"""2026-06-12 Research tab.

Final-year CS workspace for Data Analysis, Data Mining, and NLP.  Every heavy
calculation is manually run-gated so the mobile app stays light.
"""
from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import streamlit as st

from core.research_causality_20260618 import causal_binary_target, purged_time_order_split

UNIQUE = "20260612_research"


def _num(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else float(default)
    except Exception:
        return float(default)


def _optional_import(name: str):
    try:
        module = __import__(name)
        return True, getattr(module, "__version__", "installed")
    except Exception as exc:
        return False, str(exc).splitlines()[0][:80]


def _lib_status() -> pd.DataFrame:
    libs = [
        ("JavaScript helper", "streamlit_js_eval"),
        ("Polars", "polars"),
        ("DuckDB", "duckdb"),
        ("Numba", "numba"),
        ("PyArrow", "pyarrow"),
        ("Plotly Resampler", "plotly_resampler"),
        ("Streamlit Copy Button", "streamlit_copy_button"),
        ("CacheTools", "cachetools"),
        ("Scikit-learn", "sklearn"),
        ("LightGBM", "lightgbm"),
        ("CatBoost", "catboost"),
        ("Statsmodels", "statsmodels"),
        ("HMMLearn", "hmmlearn"),
        ("NLTK", "nltk"),
        ("VADER Sentiment", "vaderSentiment"),
    ]
    rows = []
    for label, mod in libs:
        ok, msg = _optional_import(mod)
        rows.append({"Library": label, "Import Name": mod, "Status": "READY" if ok else "OPTIONAL / NOT INSTALLED", "Version / Note": msg})
    return pd.DataFrame(rows)


def _prep_df(limit: int = 6000) -> pd.DataFrame:
    raw = st.session_state.get("dv_pp_df")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        raw = st.session_state.get("last_df")
    if not isinstance(raw, pd.DataFrame) or raw.empty:
        return pd.DataFrame()
    d = raw.copy().tail(int(limit)).reset_index(drop=True)
    low = {str(c).lower(): c for c in d.columns}
    ren = {"datetime": "time", "date": "time", "timestamp": "time", "o": "open", "h": "high", "l": "low", "c": "close"}
    for src, dst in ren.items():
        if src in low and dst not in d.columns:
            d = d.rename(columns={low[src]: dst})
    if "time" not in d.columns:
        return pd.DataFrame()
    for col in ["open", "high", "low", "close"]:
        if col not in d.columns:
            d[col] = d.get("close", np.nan)
        d[col] = pd.to_numeric(d[col], errors="coerce")
    d["time"] = pd.to_datetime(d["time"], errors="coerce")
    return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)


def _master_regime() -> str:
    for key in ("dv_pp_regime_summary", "final_merged_intelligence_pack_20260612", "lunch_5layer_powerbi_result"):
        obj = st.session_state.get(key, {})
        if isinstance(obj, dict):
            cur = obj.get("current_regime") or obj.get("master_regime")
            if cur:
                return str(cur)
    return "RANGE_NORMAL"


def _dir(regime: Any) -> str:
    s = str(regime).upper()
    if "BEAR" in s:
        return "SELL"
    if "BULL" in s:
        return "BUY"
    return "WAIT"

def _master_direction() -> str:
    canonical = st.session_state.get("canonical_decision_result_20260617", {})
    if isinstance(canonical, dict):
        value = canonical.get("full_metric_direction") or (canonical.get("final_decision") or {}).get("directional_market_view")
        if value:
            return _dir(value)
    return _dir(_master_regime())


def _copy_button(label: str, text: str, key: str) -> None:
    try:
        from ui.copy_tools import central_copy_button
        central_copy_button(label, text, key, show_fallback=True)
    except Exception:
        st.text_area(label, text, height=220, key=key + "_fallback")


def _analysis_pack(d: pd.DataFrame) -> Dict[str, Any]:
    if d.empty:
        return {"ok": False, "message": "No EURUSD H1 data loaded."}
    c = d["close"].astype(float)
    ret = c.pct_change().fillna(0)
    rng = (d["high"] - d["low"]).abs().replace(0, np.nan).ffill().fillna(c.abs() * 0.0005)
    desc = {
        "Rows": int(len(d)),
        "Last Time": str(d["time"].iloc[-1]),
        "Last Close": round(float(c.iloc[-1]), 5),
        "H1 Volatility pips": round(float(ret.tail(24).std()) * 10000, 3),
        "H4 Volatility pips": round(float(ret.rolling(4).sum().tail(42).std()) * 10000, 3),
        "D1 Volatility pips": round(float(ret.rolling(24).sum().tail(30).std()) * 10000, 3),
        "Avg Range pips": round(float(rng.tail(24).mean()) * 10000, 3),
        "Master Regime": _master_regime(),
        "Master Direction": _master_direction(),
    }
    # Optional Polars/DuckDB proof without making them required at runtime.
    engines = []
    try:
        import polars as pl
        pl.DataFrame(d.tail(48)).select(pl.col("close").mean())
        engines.append("Polars READY")
    except Exception:
        engines.append("Polars optional")
    try:
        import duckdb
        duckdb.sql("select avg(close) as avg_close from d").fetchall()
        engines.append("DuckDB READY")
    except Exception:
        engines.append("DuckDB optional")
    desc["Engine Alignment"] = ", ".join(engines)
    return {"ok": True, "summary": desc}


def _features(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    c = x["close"].astype(float)
    x["ret1"] = c.pct_change()
    x["ret3"] = c.pct_change(3)
    x["ret6"] = c.pct_change(6)
    x["ma12_gap"] = c / c.rolling(12).mean() - 1
    x["ma48_gap"] = c / c.rolling(48).mean() - 1
    x["range_pct"] = (x["high"] - x["low"]).abs() / c.replace(0, np.nan)
    x["vol24"] = x["ret1"].rolling(24).std()
    x["hour"] = pd.to_datetime(x["time"]).dt.hour
    x["target_up"] = causal_binary_target(c)
    feature_cols = ["ret1", "ret3", "ret6", "ma12_gap", "ma48_gap", "range_pct", "vol24", "hour"]
    return x.dropna(subset=feature_cols).reset_index(drop=True)


def _data_mining_pack(d: pd.DataFrame) -> Dict[str, Any]:
    if len(d) < 160:
        return {"ok": False, "message": "Need at least 160 H1 candles for research data mining."}
    f = _features(d).tail(3500)
    cols = ["ret1", "ret3", "ret6", "ma12_gap", "ma48_gap", "range_pct", "vol24", "hour"]
    train, test = purged_time_order_split(
        f, target_col="target_up", train_fraction=0.78, purge_rows=1, minimum_train=80
    )
    master = _master_direction()
    rows: List[Dict[str, Any]] = []
    rf_summary: Dict[str, Any] = {"status": "scikit-learn optional"}
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score
        from sklearn.neighbors import NearestNeighbors
        if train.empty or train["target_up"].nunique() < 2:
            raise ValueError("Insufficient causal labeled rows for Random Forest")
        model = RandomForestClassifier(n_estimators=80, max_depth=5, min_samples_leaf=8, random_state=42, n_jobs=1)
        model.fit(train[cols], train["target_up"].astype(int))
        pred = model.predict(test[cols]) if len(test) else []
        acc = float(accuracy_score(test["target_up"].astype(int), pred)) if len(test) else 0.0
        proba = float(model.predict_proba(f[cols].tail(1))[0][1])
        rf_dir = "BUY" if proba >= 0.55 else "SELL" if proba <= 0.45 else "WAIT"
        rf_summary = {"status": "READY", "Random Forest Accuracy %": round(acc * 100, 2), "RF Next 1H Up Probability %": round(proba * 100, 2), "RF Direction": rf_dir, "Master Direction": master, "RF Sync": "CONFIRM" if rf_dir == master else "CONFLICT" if rf_dir in ("BUY", "SELL") and master in ("BUY", "SELL") else "NEUTRAL"}
        nn = NearestNeighbors(n_neighbors=min(14, len(f) - 2), metric="euclidean")
        z = (f[cols] - f[cols].mean()) / f[cols].std().replace(0, 1)
        nn.fit(z.iloc[:-1])
        dist, idx = nn.kneighbors(z.tail(1), return_distance=True)
        for rank, (i, di) in enumerate(zip(idx[0], dist[0]), 1):
            row = f.iloc[int(i)]
            next_move = float(f["close"].iloc[min(int(i) + 1, len(f) - 1)] - row["close"])
            hist_dir = "BUY" if next_move > 0 else "SELL" if next_move < 0 else "WAIT"
            score = 100 - min(70, float(di) * 14)
            label = f"{master} allowed" if hist_dir == master and score >= 55 else "WATCH / WAIT"
            rows.append({"Priority Rank": rank, "Hour": int(row["hour"]), "Similarity Score": round(score, 2), "Historical Next 1H Dir": hist_dir, "Historical Move pips": round(next_move * 10000, 2), "Master Direction": master, "Prescriptive Label": label, "Reason": "KNN similar row + RF support"})
    except Exception as exc:
        rf_summary["error"] = str(exc)[:160]
    pr = pd.DataFrame(rows)
    if not pr.empty:
        pr = pr.sort_values(["Priority Rank"], ascending=True).reset_index(drop=True)
    return {"ok": True, "random_forest": rf_summary, "knn_priority": pr}


def _fetch_news(limit: int) -> Tuple[List[Dict[str, Any]], str]:
    """Use the one canonical session-only Finnhub connector, then public RSS.

    No API key is accepted by this renderer. The key remains inside the active
    Streamlit session owned by ``core.finnhub_connector``.
    """
    try:
        from core.finnhub_connector import fetch_market_news, connection_status
        status = connection_status()
        if status.get("connected"):
            rows = fetch_market_news("forex", force=False)
            if isinstance(rows, list) and rows:
                return rows[:limit], "Finnhub"
    except Exception:
        pass
    rows = []
    for url in ["https://www.forexlive.com/feed/news/", "https://www.fxstreet.com/rss/news"]:
        try:
            import requests
            r = requests.get(url, timeout=7, headers={"User-Agent": "Mozilla/5.0"})
            root = ET.fromstring(r.content)
            for it in root.findall(".//item"):
                rows.append({"headline": it.findtext("title") or "", "summary": it.findtext("description") or "", "publishedDate": it.findtext("pubDate") or "", "source": url.split("/")[2]})
                if len(rows) >= limit:
                    return rows, "RSS"
        except Exception:
            pass
    return rows, "RSS / LOCAL CACHE"


def _score_news(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    try:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        vader = SentimentIntensityAnalyzer()
    except Exception:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            vader = SentimentIntensityAnalyzer()
        except Exception:
            vader = None
    kw = ("eurusd", "eur/usd", "euro", "eurozone", "ecb", "fed", "dollar", "usd", "cpi", "nfp", "pmi", "inflation", "yield")
    eur_pos, eur_neg = ("euro rises", "euro stronger", "ecb hawkish", "pmi beat", "spanish inflation picks up", "french inflation accelerates", "germany inflation picked up", "core inflation"), ("euro falls", "euro weaker", "ecb dovish", "pmi miss", "recession", "political risk")
    usd_pos, usd_neg = ("dollar rises", "dollar stronger", "fed hawkish", "nfp beat", "cpi hot", "yields rise", "iran", "middle east conflict", "safe haven"), ("dollar falls", "dollar weaker", "fed cut", "fed dovish", "nfp miss", "cpi cool", "deal optimism", "risk rally")
    out = []
    for r in rows:
        text = (str(r.get("headline") or "") + " " + str(r.get("summary") or "")).lower()
        if not any(k in text for k in kw):
            continue
        sent = float(vader.polarity_scores(text).get("compound", 0.0)) if vader else 0.0
        eur = sum(1.25 for p in eur_pos if p in text) - sum(1.25 for p in eur_neg if p in text) + sent * 0.25
        usd = sum(1.25 for p in usd_pos if p in text) - sum(1.25 for p in usd_neg if p in text) - sent * 0.10
        if any(w in text for w in ["euro", "eurozone", "european", "ecb", "german", "french", "spanish"]):
            eur += 0.18
        if any(w in text for w in ["dollar", "usd", "fed", "treasury", "yield", " nfp", " cpi"]):
            usd += 0.18
        if any(w in text for w in ["iran", "geopolitical", "conflict", "oil", "safe haven"]):
            usd += 0.45
        delta = eur - usd
        nd = "BUY" if delta > 0.35 else "SELL" if delta < -0.35 else "WAIT"
        out.append({"Priority Rank": len(out)+1, "Title": str(r.get("headline") or "")[:160], "Source": str(r.get("source") or "news"), "EUR Impact": round(eur, 2), "USD Impact": round(usd, 2), "VADER": round(sent, 3), "News Direction": nd, "Static Impact": "BUY support" if nd=="BUY" else "SELL support" if nd=="SELL" else "WAIT / mixed", "Published": str(r.get("publishedDate") or "")[:35]})
    df = pd.DataFrame(out[:30])
    if not df.empty:
        df["Impact Abs"] = (pd.to_numeric(df["EUR Impact"], errors="coerce").fillna(0) - pd.to_numeric(df["USD Impact"], errors="coerce").fillna(0)).abs()
        df = df.sort_values(["Impact Abs", "Priority Rank"], ascending=[False, True]).reset_index(drop=True)
        df["Priority Rank"] = df.index + 1
        df = df.drop(columns=["Impact Abs"], errors="ignore")
    master = _dir(_master_regime())
    if df.empty:
        summary = {"News Direction": "WAIT", "News Sync": "LOW PRIORITY", "Articles Used": 0, "Master Direction": master}
    else:
        eur = pd.to_numeric(df["EUR Impact"], errors="coerce").fillna(0).mean()
        usd = pd.to_numeric(df["USD Impact"], errors="coerce").fillna(0).mean()
        nd = "BUY" if eur - usd > 0.25 else "SELL" if eur - usd < -0.25 else "WAIT"
        sync = "CONFIRM" if nd == master and nd != "WAIT" else "CONFLICT" if nd in ("BUY", "SELL") and master in ("BUY", "SELL") and nd != master else "NEUTRAL"
        summary = {"News Direction": nd, "News Sync": sync, "Articles Used": int(len(df)), "Master Direction": master, "Avg EUR Impact": round(float(eur), 3), "Avg USD Impact": round(float(usd), 3)}
    return {"summary": summary, "table": df}


def _regime_nlp_history(d: pd.DataFrame, news_summary: Dict[str, Any]) -> pd.DataFrame:
    if d.empty:
        return pd.DataFrame()
    x = d.tail(25 * 24).copy()
    x["hour"] = pd.to_datetime(x["time"]).dt.hour
    x = x[(x["hour"] >= 1) & (x["hour"] <= 14)].copy()
    if x.empty:
        return pd.DataFrame()
    c = x["close"].astype(float)
    x["ma12"] = c.rolling(12, min_periods=3).mean()
    x["ma48"] = c.rolling(48, min_periods=10).mean()
    x["Regime Direction"] = np.where(x["ma12"] > x["ma48"], "BUY", np.where(x["ma12"] < x["ma48"], "SELL", "WAIT"))
    master = _dir(_master_regime())
    news_sync = news_summary.get("News Sync", "NEUTRAL")
    x["Greedy Score"] = np.where(x["Regime Direction"] == master, 68, 42) + (12 if news_sync == "CONFIRM" else -14 if news_sync == "CONFLICT" else 0)
    x["Entry Opportunity"] = np.where((x["Greedy Score"] >= 64) & (x["Regime Direction"] == master), "YES", "WATCH")
    keep = x.tail(25 * 14).sort_values(["Greedy Score", "time"], ascending=[False, False]).copy()
    keep = keep.reset_index(drop=True)
    keep["Priority Rank"] = keep.index + 1
    keep["Date"] = pd.to_datetime(keep["time"], errors="coerce").dt.strftime("%Y-%m-%d")
    return keep[["Priority Rank", "Date", "time", "hour", "Regime Direction", "Greedy Score", "Entry Opportunity"]]


def _run_research(news_limit: int, selected: str = "Data Analysis") -> Dict[str, Any]:
    """Build only the selected Research inner tab and retain prior cached peers."""
    selected = selected if selected in {"Data Analysis", "Data Mining", "NLP"} else "Data Analysis"
    existing = st.session_state.get("research_pack_20260612")
    existing = existing if isinstance(existing, dict) else {}
    d = _prep_df(6000)
    analysis = existing.get("data_analysis", {}) if isinstance(existing.get("data_analysis"), dict) else {}
    mining = existing.get("data_mining", {}) if isinstance(existing.get("data_mining"), dict) else {}
    nlp = existing.get("nlp", {}) if isinstance(existing.get("nlp"), dict) else {}
    hist = existing.get("regime_nlp_history", pd.DataFrame())

    if selected == "Data Analysis":
        analysis = _analysis_pack(d)
        try:
            from core.advanced_analytics_20260615 import build_diagnostic_analysis_table, build_sampling_estimating_hypothesis_tables
            analysis["diagnostic_table"] = build_diagnostic_analysis_table(d)
            analysis["sampling_estimating_hypothesis"] = build_sampling_estimating_hypothesis_tables(d)
        except Exception as exc:
            analysis["diagnostic_error"] = str(exc)[:160]
    elif selected == "Data Mining":
        mining = _data_mining_pack(d)
        try:
            from core.advanced_analytics_20260615 import build_data_mining_extension_tables
            mining["advanced_tables"] = build_data_mining_extension_tables(d)
        except Exception as exc:
            mining["advanced_error"] = str(exc)[:160]
    else:
        rows, source = _fetch_news(int(news_limit))
        nlp = _score_news(rows)
        nlp["source"] = source
        canonical_history = st.session_state.get("canonical_priority_table_20260617")
        hist = canonical_history if isinstance(canonical_history, pd.DataFrame) and not canonical_history.empty else _regime_nlp_history(d, nlp.get("summary", {}))

    causal_support = st.session_state.get("causal_quant_support_20260618")
    causal_support = causal_support if isinstance(causal_support, dict) else existing.get("causal_quant_support", {})
    pack = {
        "export_type": "RESEARCH_DATA_ANALYSIS_MINING_NLP_20260612",
        "built_at": str(pd.Timestamp.now()), "symbol": "EURUSD", "timeframe": "H1",
        "library_status": _lib_status(), "data_analysis": analysis, "data_mining": mining,
        "nlp": nlp, "regime_nlp_history": hist,
        "causal_quant_support": causal_support,
        "selected_inner_tab_built": selected,
    }
    text = json.dumps(_safe(pack), indent=2, ensure_ascii=False, default=str)
    st.session_state["research_pack_20260612"] = pack
    st.session_state["research_export_20260612"] = text
    return pack


def build_all_research_pack_for_settings(
    data: pd.DataFrame,
    *,
    nlp_result: Dict[str, Any] | None = None,
    canonical_history: pd.DataFrame | None = None,
) -> Dict[str, Any]:
    """Build every existing Research inner-tab cache during the Settings run.

    This is a non-UI orchestration helper. It reuses the established analysis,
    mining and NLP outputs and never adds a model or starts a second page-level
    calculation.
    """
    d = _prep_df(10000) if not isinstance(data, pd.DataFrame) or data.empty else data.copy(deep=False)
    analysis = _analysis_pack(d)
    mining = _data_mining_pack(d)
    try:
        from core.advanced_analytics_20260615 import (
            build_diagnostic_analysis_table,
            build_sampling_estimating_hypothesis_tables,
            build_data_mining_extension_tables,
        )
        analysis["diagnostic_table"] = build_diagnostic_analysis_table(d)
        analysis["sampling_estimating_hypothesis"] = build_sampling_estimating_hypothesis_tables(d)
        mining["advanced_tables"] = build_data_mining_extension_tables(d)
    except Exception as exc:
        analysis["advanced_error"] = str(exc)[:200]
        mining["advanced_error"] = str(exc)[:200]

    raw_nlp = nlp_result if isinstance(nlp_result, dict) else {}
    articles = raw_nlp.get("articles") if isinstance(raw_nlp, dict) else None
    nlp = {
        "summary": raw_nlp.get("summary", {}) if isinstance(raw_nlp, dict) else {},
        "table": articles if isinstance(articles, pd.DataFrame) else pd.DataFrame(),
        "source": raw_nlp.get("source", "published NLP pipeline") if isinstance(raw_nlp, dict) else "published NLP pipeline",
        "news_mining": raw_nlp.get("news_mining", {}) if isinstance(raw_nlp, dict) else {},
        "event_response": raw_nlp.get("event_response", pd.DataFrame()) if isinstance(raw_nlp, dict) else pd.DataFrame(),
        "aggregates": raw_nlp.get("aggregates", pd.DataFrame()) if isinstance(raw_nlp, dict) else pd.DataFrame(),
        "error_analysis": raw_nlp.get("error_analysis", {}) if isinstance(raw_nlp, dict) else {},
    }
    hist = canonical_history if isinstance(canonical_history, pd.DataFrame) and not canonical_history.empty else _regime_nlp_history(d, nlp.get("summary", {}))
    causal_support = st.session_state.get("causal_quant_support_20260618")
    causal_support = causal_support if isinstance(causal_support, dict) else {}
    pack = {
        "export_type": "RESEARCH_DATA_ANALYSIS_MINING_NLP_20260612",
        "built_at": str(pd.Timestamp.now()),
        "symbol": "EURUSD",
        "timeframe": "H1",
        "library_status": _lib_status(),
        "data_analysis": analysis,
        "data_mining": mining,
        "nlp": nlp,
        "regime_nlp_history": hist,
        "causal_quant_support": causal_support,
        "selected_inner_tab_built": "ALL_FROM_SETTINGS",
        "all_inner_tabs_ready": True,
    }
    st.session_state["research_pack_20260612"] = pack
    st.session_state["research_export_20260612"] = json.dumps(_safe(pack), indent=2, ensure_ascii=False, default=str)
    st.session_state["research_run_calculate"] = True
    return pack


def _safe(obj: Any) -> Any:
    if isinstance(obj, pd.DataFrame):
        return obj.head(200).to_dict("records")
    if isinstance(obj, pd.Series):
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): _safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe(x) for x in obj[:200]]
    return obj


def _dict_table(obj: Any, prefix: str = "") -> pd.DataFrame:
    rows = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                rows.extend(_dict_table(value, name).to_dict("records"))
            elif isinstance(value, pd.DataFrame):
                rows.append({"Metric": name, "Value": f"DataFrame {len(value)} rows"})
            else:
                rows.append({"Metric": name, "Value": str(value)})
    elif obj is not None:
        rows.append({"Metric": prefix or "Value", "Value": str(obj)})
    return pd.DataFrame(rows, columns=["Metric", "Value"])


def _render_pack(pack: Dict[str, Any], selected: str) -> None:
    """Render one canonical Research inner tab selected by ``research_inner_tab``."""
    st.markdown("### 🎓 Research Workspace Result")
    selected = selected if selected in {"Data Analysis", "Data Mining", "NLP"} else "Data Analysis"

    if selected == "Data Analysis":
        st.subheader("Descriptive Data Analysis")
        try:
            from tabs.dinner_morning_data_patch_20260614 import render_data_analysis_result_table_20260614
            render_data_analysis_result_table_20260614("research_data_analysis")
        except Exception as exc:
            st.caption(f"Current result table skipped safely: {exc}")
        summ = pack.get("data_analysis", {}).get("summary", {})
        if summ:
            cols = st.columns(4)
            cols[0].metric("Rows", summ.get("Rows", "-"))
            cols[1].metric("Last Close", summ.get("Last Close", "-"))
            cols[2].metric("Master Regime", summ.get("Master Regime", "-"))
            cols[3].metric("Master Direction", summ.get("Master Direction", "-"))
            st.dataframe(_dict_table(summ), use_container_width=True, hide_index=True)
        else:
            st.info(pack.get("data_analysis", {}).get("message", "No analysis yet."))

    elif selected == "Data Mining":
        st.subheader("Data Mining: Random Forest + KNN Priority")
        mining = pack.get("data_mining", {})
        st.dataframe(_dict_table(mining.get("random_forest", {})), use_container_width=True, hide_index=True)
        pr = mining.get("knn_priority", pd.DataFrame())
        if isinstance(pr, pd.DataFrame) and not pr.empty:
            st.dataframe(pr, use_container_width=True, hide_index=True, height=320)
        try:
            from core.advanced_analytics_20260615 import render_data_mining_advanced_panel
            render_data_mining_advanced_panel(key="research_data_mining", expanded=False)
        except Exception as exc:
            st.caption(f"Advanced data-mining evaluation skipped safely: {exc}")
        causal = pack.get("causal_quant_support", {}) if isinstance(pack.get("causal_quant_support"), dict) else {}
        if causal:
            pattern = causal.get("pattern_memory", {}) if isinstance(causal.get("pattern_memory"), dict) else {}
            transition = causal.get("transition_risk", {}) if isinstance(causal.get("transition_risk"), dict) else {}
            actionability = causal.get("actionability", {}) if isinstance(causal.get("actionability"), dict) else {}
            evidence_summary = {
                "cache_status": causal.get("cache_status"),
                "retained_h1_rows": causal.get("retained_rows"),
                "pattern_confirmation": pattern.get("pattern_confirmation"),
                "pattern_confidence": pattern.get("pattern_confidence", pattern.get("confidence")),
                "pattern_sample_count": pattern.get("sample_count"),
                "transition_status": transition.get("status"),
                "transition_risk": transition.get("value"),
                "structural_break_strength": transition.get("structural_break_strength"),
                "entropy_increase": transition.get("entropy_increase"),
                "actionability_label": actionability.get("current_label"),
                "actionability_sample_count": actionability.get("sample_count"),
                "expected_value": actionability.get("expected_value"),
                "fractional_feature_weight": (causal.get("fractional_differentiation") or {}).get("weight"),
                "duplicate_evidence_penalty": (causal.get("duplicate_evidence_control") or {}).get("duplicate_penalty"),
            }
            st.dataframe(_dict_table(evidence_summary), use_container_width=True, hide_index=True, height=360)
        with st.expander("Open / Close — Mirrored Home/Data Visualization mining logic", expanded=False):
            merged = st.session_state.get("final_merged_intelligence_pack_20260612", {})
            if isinstance(merged, dict) and merged:
                st.caption("Related mining/priority outputs are mirrored here for CS practice; original logic remains in place.")
                st.dataframe(_dict_table({"master_regime": merged.get("master_regime"), "master_direction": merged.get("master_direction"), "market_story": merged.get("market_story")}), use_container_width=True, hide_index=True)
                mp = merged.get("knn_greedy_priority", pd.DataFrame())
                if isinstance(mp, pd.DataFrame) and not mp.empty:
                    st.dataframe(mp, use_container_width=True, hide_index=True, height=260)
            else:
                st.info("Run Data Visualization → Final Merged Intelligence to mirror more mining logic here.")

    else:
        st.subheader("NLP: EURUSD News Confirmation + Regime History")
        nlp = pack.get("nlp", {})
        st.dataframe(_dict_table(nlp.get("summary", {})), use_container_width=True, hide_index=True)
        nt = nlp.get("table", pd.DataFrame())
        # The one-row legacy NLP snapshot is supporting detail only. The visible
        # primary table is the ranked 10-day news table rendered at the top of
        # the NLP workspace, so users never mistake a single snapshot for the
        # complete news history.
        if isinstance(nt, pd.DataFrame) and not nt.empty:
            with st.expander("Open / Close — Legacy NLP source snapshot", expanded=False):
                st.dataframe(nt, use_container_width=True, hide_index=True, height=260)
        canonical_hist = st.session_state.get("canonical_priority_table_20260617")
        hist = canonical_hist if isinstance(canonical_hist, pd.DataFrame) and not canonical_hist.empty else pack.get("regime_nlp_history", pd.DataFrame())
        if isinstance(hist, pd.DataFrame) and not hist.empty:
            # The regime/NLP history contract remains window_days=25; the
            # separate news-priority table intentionally uses a recent 10-day window.
            st.markdown("#### 25-Day Regime Prediction History + NLP — hourly ranked rows")
            display_rows = 168 if bool(st.session_state.get("phone_mode", False)) else 360
            try:
                from ui.table_ordering_20260618 import newest_first
                hist_view = newest_first(hist, display_rows)
            except Exception:
                hist_view = hist.sort_index(ascending=False).head(display_rows).reset_index(drop=True)
            st.dataframe(hist_view, use_container_width=True, hide_index=True, height=320)
        with st.expander("🧠 Open / Close — NLP Processing Pipeline", expanded=False):
            try:
                from core.nlp_lightweight_20260615 import render_nlp_pipeline_panel
                text_rows = []
                if isinstance(nt, pd.DataFrame) and not nt.empty:
                    for _, row in nt.head(8).iterrows():
                        text_rows.extend([str(row.get("Title", "")), str(row.get("Static Impact", ""))])
                sample = " ".join([x for x in text_rows if x and x != "nan"]) or json.dumps(nlp.get("summary", {}), ensure_ascii=False, default=str)
                render_nlp_pipeline_panel(sample, key=f"research_nlp_pipeline_{UNIQUE}", title="Research NLP: normalization, entities, topics, sentiment, direction, summary and reliability")
            except Exception as exc:
                st.caption(f"NLP pipeline skipped safely: {exc}")

    # Preserve supporting tools as expandable fields, not competing selectors.
    with st.expander("Open / Close — Research Library Status", expanded=False):
        status = pack.get("library_status", pd.DataFrame())
        if isinstance(status, pd.DataFrame):
            st.dataframe(status, use_container_width=True, hide_index=True, height=420)
    with st.expander("Open / Close — Research Copy / Export", expanded=False):
        text = st.session_state.get("research_export_20260612", json.dumps(_safe(pack), indent=2, default=str))
        _copy_button("Copy Research Full", text, f"copy_research_full_{UNIQUE}")
        _copy_button("Copy Research Necessary 100 Lines", "\n".join(text.splitlines()[:100]), f"copy_research_100_{UNIQUE}")

def show() -> None:
    st.markdown("# 🎓 Research")
    st.caption("Data Analysis, Data Mining and NLP reuse the one generation built by Settings. Switching inner tabs never starts a second calculation.")
    c = st.columns([1, 1, 1])
    try:
        from core.canonical_runtime_20260617 import get_canonical
        canonical = get_canonical(st.session_state)
    except Exception:
        canonical = {}
    canonical_ready = bool(canonical)
    st.session_state["research_run_calculate"] = bool(canonical_ready or st.session_state.get("research_pack_20260612"))
    c[0].metric("Canonical H1", "READY" if canonical_ready else "NOT READY", f"Generation {canonical.get('calculation_generation', '-') if isinstance(canonical, dict) else '-'}")
    c[1].metric("Research Cache", "READY" if st.session_state.get("research_pack_20260612") else "CHECK", "Built by Settings one-click run")
    try:
        from core.finnhub_connector import connection_status
        fh_status = connection_status()
        c[2].metric("Finnhub", "CONNECTED" if fh_status.get("connected") else "DISCONNECTED", fh_status.get("availability", "UNKNOWN"))
    except Exception:
        c[2].metric("Finnhub", "DISCONNECTED", "Connector unavailable")
    st.info("Research tab mirrors Home/Data Visualization logic only when useful. It does not override Unified PowerBI direction.")
    try:
        research = st.session_state.get("research_model_validation_20260708")
        ranking = st.session_state.get("field10_institutional_ranking_20260708")
        news = st.session_state.get("field10_news_nlp_evidence_20260708")
        selected_symbol = ""
        if any(isinstance(x, pd.DataFrame) and not x.empty for x in (research, ranking, news)):
            from core.canonical_symbol_selection_20260709 import render_selector, filter_frame_for_symbol, active_symbol
            selected_symbol, _, _ = render_selector(st, st.session_state, surface="research", title="Research Multi-Symbol Selector — Load Model Evidence")
            selected_symbol = selected_symbol or active_symbol(st.session_state, surface="research")
        if isinstance(research, pd.DataFrame) and not research.empty:
            with st.expander("🏛️ Open / Close — Institutional Research Validation from Super Quick Run", expanded=True):
                st.caption("Calculated research tables, not background text: Brier/log/CRPS, conformal coverage, SPA/MCS/White Reality/PBO proxies, rank stability, duplicate exposure, changepoint, and data quality.")
                view = filter_frame_for_symbol(research, selected_symbol) if selected_symbol else research
                st.dataframe(view if not view.empty else research, use_container_width=True, hide_index=True)
        if isinstance(ranking, pd.DataFrame) and not ranking.empty:
            with st.expander("🏛️ Open / Close — Research Field 10 Ranking Evidence", expanded=False):
                cols = [c for c in ["Rank", "Symbol", "InstitutionalUtility", "Brier score", "Log score", "CRPS score", "Calibration score", "Rank stability", "Changepoint risk using BOCPD", "Duplicate exposure penalty"] if c in ranking.columns]
                view = filter_frame_for_symbol(ranking, selected_symbol) if selected_symbol else ranking
                st.dataframe((view[cols] if cols and not view.empty else ranking[cols] if cols else view), use_container_width=True, hide_index=True)
        if isinstance(news, pd.DataFrame) and not news.empty:
            with st.expander("📰 Open / Close — AI/NLP Saved Evidence by Symbol", expanded=False):
                view = filter_frame_for_symbol(news, selected_symbol) if selected_symbol else news
                st.dataframe(view if not view.empty else news, use_container_width=True, hide_index=True)
    except Exception as institutional_research_exc_20260708:
        st.caption(f"Institutional research snapshot unavailable: {type(institutional_research_exc_20260708).__name__}")
    research_options = ["Data Analysis", "Data Mining", "NLP"]
    requested = str(st.session_state.get("research_inner_tab", "Data Analysis"))
    if requested not in research_options:
        requested = "Data Analysis"
        st.session_state["research_inner_tab"] = requested
    st.session_state.setdefault("research_inner_tab", requested)
    try:
        from ui.stable_ui_libs_20260615 import inject_stable_ui_css, segmented_choice
        inject_stable_ui_css()
        st.markdown(
            """
            <div class="new7-modern-card">
              <b>Research Workspace</b><br>
              <span>Choose one full-width workspace button. Only the selected analysis is rendered, reducing phone load.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        selected = segmented_choice(
            "Research workspace",
            research_options,
            key="research_inner_tab",
            default=requested,
        )
    except Exception:
        cols = st.columns(len(research_options))
        selected = requested
        for index, option in enumerate(research_options):
            active = st.session_state.get("research_inner_tab") == option
            if cols[index].button(("✅ " if active else "") + option, key=f"research_choice_button_{index}_{UNIQUE}", use_container_width=True):
                st.session_state["research_inner_tab"] = option
                selected = option
    # NLP connector status, actions and the ranked real-news table belong at the
    # very top of the NLP inner tab. This is also the only active Research path;
    # it contains no duplicated API-key password input.
    shared_nlp_workspace_rendered = False
    if selected == "NLP":
        try:
            from ui.nlp_research_panel import render_nlp_research_workspace
            render_nlp_research_workspace(selected)
            shared_nlp_workspace_rendered = True
        except Exception as exc:
            st.caption(f"Shared NLP workspace skipped safely: {exc}")

    pack = st.session_state.get("research_pack_20260612")
    if isinstance(pack, dict) and pack:
        _render_pack(pack, selected)
    else:
        try:
            from core.system_wide_completion_20260618 import readiness_message
            st.warning(readiness_message(st.session_state, "Research Data Analysis" if selected == "Data Analysis" else "Research Data Mining" if selected == "Data Mining" else "NLP 10-Day News"))
        except Exception:
            st.warning("Research output is missing from the published generation. Open Settings → Errors / Fix Fast.")

    # Data Analysis and Data Mining do not import the NLP workspace. The selected
    # workspace is the only one instantiated on this rerun.
