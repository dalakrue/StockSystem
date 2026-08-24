"""2026-06-12 final unified Data Visualization/Home merge.

Creates one run-gated merged intelligence field under the PowerBI projection,
keeps old logic/functions available, and refreshes Home/Finder copy sync.
"""
from __future__ import annotations


def install(ns: dict) -> None:
    import json, math, os, re, time, xml.etree.ElementTree as ET
    from pathlib import Path
    from typing import Any, Dict, List, Tuple
    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    import requests
    import streamlit as st

    UNIQUE = "20260612_finalmerge"

    def _num(v: Any, default: float = 0.0) -> float:
        try:
            x = float(v)
            return x if math.isfinite(x) else float(default)
        except Exception:
            return float(default)

    def _safe(obj: Any, rows: int = 80) -> Any:
        try:
            if isinstance(obj, pd.DataFrame):
                return obj.head(rows).to_dict("records")
            if isinstance(obj, pd.Series):
                return obj.to_dict()
            if isinstance(obj, pd.Timestamp):
                return str(obj)
            if isinstance(obj, dict):
                return {str(k): _safe(v, rows) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_safe(x, rows) for x in list(obj)[:rows]]
            return obj
        except Exception:
            return str(obj)

    def _json(obj: Any, rows: int = 120) -> str:
        return json.dumps(_safe(obj, rows), indent=2, ensure_ascii=False, default=str)

    def _copy_button(label: str, text: str, key: str) -> None:
        try:
            from core.pro_terminal_uiux import render_mobile_copy_button
            render_mobile_copy_button(label, text, key)
        except Exception:
            st.text_area(label, text, height=220, key=key + "_fallback")

    def _app_css() -> None:
        big = bool(st.session_state.get("mobile_app_big_mode_20260612", False))
        mult = 1.18 if big else 1.0
        st.markdown(f"""
        <style>
        .block-container{{max-width:1180px;padding-top:.65rem!important}}
        div[data-testid="stMetric"]{{border-radius:20px!important;padding:{10*mult:.0f}px {12*mult:.0f}px!important;border:1px solid rgba(99,102,241,.20);box-shadow:0 8px 24px rgba(15,23,42,.08)}}
        .stButton>button{{border-radius:999px!important;min-height:{46*mult:.0f}px!important;font-size:{15*mult:.0f}px!important;font-weight:850!important}}
        textarea, input, [data-testid="stSelectbox"], [data-testid="stSlider"]{{font-size:{15*mult:.0f}px!important}}
        @media(max-width:780px){{
          .block-container{{padding-left:.45rem!important;padding-right:.45rem!important}}
          div[data-testid="column"]{{min-width:0!important}}
          div[data-testid="stMetric"]{{margin:.18rem 0!important}}
          .stDataFrame{{font-size:{12*mult:.0f}px!important}}
          [data-testid="stHorizontalBlock"]{{gap:.35rem!important}}
          h1,h2,h3{{letter-spacing:-.02em!important}}
        }}
        </style>
        """, unsafe_allow_html=True)

    def _app_login_bar() -> None:
        path = Path("data/app_login_20260612.json")
        try:
            saved = json.loads(path.read_text()) if path.exists() else {}
        except Exception:
            saved = {}
        st.session_state.setdefault("app_login_user_20260612", saved.get("user", "admin"))
        st.session_state.setdefault("app_login_pass_20260612", saved.get("password", "1234"))
        if st.session_state.get("app_logged_in_20260612"):
            a, b, c = st.columns([1, 1, 1])
            a.metric("App Login", st.session_state.get("app_login_user_20260612", "admin"), "guest" if st.session_state.get("app_guest_mode_20260612") else "session active")
            if b.button("📱 Toggle Real Mobile Big UI", use_container_width=True, key=f"mobile_big_toggle_{UNIQUE}"):
                st.session_state["mobile_app_big_mode_20260612"] = not bool(st.session_state.get("mobile_app_big_mode_20260612", False))
                st.rerun()
            if c.button("🚪 Logout", use_container_width=True, key=f"logout_{UNIQUE}"):
                st.session_state["app_logged_in_20260612"] = False
                st.rerun()
            return
        with st.expander("🔐 App Login / Logout — saved locally", expanded=True):
            c1, c2, c3, c4 = st.columns([1, 1, .75, .75])
            user = c1.text_input("Account", value=st.session_state.get("app_login_user_20260612", "admin"), key=f"login_user_{UNIQUE}")
            pwd = c2.text_input("Password", value=st.session_state.get("app_login_pass_20260612", "1234"), type="password", key=f"login_pass_{UNIQUE}")
            if c3.button("Login / Save", use_container_width=True, key=f"login_save_{UNIQUE}"):
                st.session_state["app_login_user_20260612"] = user or "admin"
                st.session_state["app_login_pass_20260612"] = pwd or "1234"
                st.session_state["app_logged_in_20260612"] = True
                st.session_state["app_guest_mode_20260612"] = False
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps({"user": user or "admin", "password": pwd or "1234"}, indent=2))
                except Exception:
                    pass
                st.success("Login saved. This account/password file stays after code update inside the same app folder.")
                st.rerun()
            if c4.button("Guest", use_container_width=True, key=f"login_guest_{UNIQUE}"):
                st.session_state["app_logged_in_20260612"] = True
                st.session_state["app_guest_mode_20260612"] = True
                st.session_state["app_login_user_20260612"] = "Guest"
                st.success("Guest mode opened. No account/password required.")
                st.rerun()
            st.caption("Default is admin / 1234. Use Guest for quick open without login. Saved account stays in data/app_login_20260612.json.")

    def _prep_ohlc(limit: int = 6000) -> pd.DataFrame:
        raw = st.session_state.get("dv_pp_df")
        if not isinstance(raw, pd.DataFrame) or raw.empty:
            raw = st.session_state.get("last_df")
        prep = ns.get("_dv_prepare_ohlc_v20260609")
        if callable(prep):
            try:
                out = prep(raw, limit=int(limit))
                if isinstance(out, pd.DataFrame) and not out.empty:
                    return out.tail(limit).reset_index(drop=True)
            except Exception:
                pass
        if not isinstance(raw, pd.DataFrame) or raw.empty or "close" not in [str(c).lower() for c in raw.columns]:
            return pd.DataFrame()
        d = raw.copy().tail(limit).reset_index(drop=True)
        low = {str(c).lower(): c for c in d.columns}
        for src, dst in {"datetime":"time","date":"time","timestamp":"time","o":"open","h":"high","l":"low","c":"close"}.items():
            if src in low and dst not in d.columns:
                d = d.rename(columns={low[src]: dst})
        if "time" not in d.columns:
            d["time"] = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=len(d), freq="h")
        for col in ["open", "high", "low", "close"]:
            if col not in d.columns and col != "close":
                d[col] = d["close"]
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["time"] = pd.to_datetime(d["time"], errors="coerce")
        return d.dropna(subset=["time", "close"]).sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)

    def _master_regime() -> str:
        for key in ("dv_pp_regime_summary", "lunch_5layer_powerbi_result", "nylo_unified_home_sync_20260612"):
            obj = st.session_state.get(key, {})
            if isinstance(obj, dict):
                cur = obj.get("current_regime") or obj.get("master_regime")
                if not cur and isinstance(obj.get("summary"), dict):
                    cur = obj["summary"].get("current_powerbi_regime")
                if cur:
                    return str(cur)
        return "RANGE_NORMAL"

    def _dir(regime: Any) -> str:
        s = str(regime).upper()
        if "BEAR" in s: return "SELL"
        if "BULL" in s: return "BUY"
        return "WAIT"

    def _fetch_news(mode: str, finnhub: str, fmp: str, limit: int) -> Tuple[List[Dict[str, Any]], str]:
        def fx_finnhub():
            r = requests.get("https://finnhub.io/api/v1/news", params={"category":"forex", "token":finnhub}, timeout=8); r.raise_for_status(); return r.json(), "Finnhub"
        def fx_fmp():
            r = requests.get("https://financialmodelingprep.com/stable/news/forex", params={"apikey":fmp,"limit":limit}, timeout=8); r.raise_for_status();
            rows=[]
            for x in r.json()[:limit]: rows.append({"headline":x.get("title"),"summary":x.get("text"),"publishedDate":x.get("publishedDate"),"source":x.get("site"),"url":x.get("url")})
            return rows, "FMP"
        def fx_rss():
            rows=[]
            for url in ["https://www.forexlive.com/feed/news/", "https://www.fxstreet.com/rss/news"]:
                try:
                    r=requests.get(url,timeout=7,headers={"User-Agent":"Mozilla/5.0"})
                    root=ET.fromstring(r.content)
                    for it in root.findall(".//item"):
                        rows.append({"headline":it.findtext("title") or "", "summary":it.findtext("description") or "", "publishedDate":it.findtext("pubDate") or "", "source":url.split('/')[2], "url":it.findtext("link") or ""})
                        if len(rows)>=limit: return rows, "RSS"
                except Exception: pass
            return rows, "RSS"
        order = [fx_finnhub, fx_fmp, fx_rss] if mode == "Finnhub first" else [fx_fmp, fx_finnhub, fx_rss] if mode == "FMP first" else [fx_rss]
        for fn in order:
            try:
                rows, src = fn()
                if isinstance(rows, list) and rows: return rows[:limit], src
            except Exception: continue
        return [], "No source"

    def _score_news(rows: List[Dict[str, Any]], master_dir: str) -> Dict[str, Any]:
        kw = ("eurusd","eur/usd","euro","eurozone","ecb","fed","fomc","dollar","usd","cpi","nfp","pmi","treasury","yield","inflation","jobs")
        ep=("ecb hawkish","euro rises","euro stronger","eurozone pmi beat","german pmi beat","inflation hot")
        en=("ecb cut","ecb dovish","euro falls","euro weaker","pmi miss","recession")
        up=("fed hawkish","fed hike","dollar rises","dollar stronger","nfp beat","cpi hot","yields rise")
        un=("fed cut","fed dovish","dollar falls","dollar weaker","nfp miss","cpi cool","yields fall")
        scored=[]
        for r in rows:
            text = (str(r.get("headline") or r.get("title") or "") + " " + str(r.get("summary") or "")).lower()
            if not any(k in text for k in kw): continue
            eur=sum(1.35 for p in ep if p in text)-sum(1.35 for p in en if p in text)
            usd=sum(1.35 for p in up if p in text)-sum(1.35 for p in un if p in text)
            if "euro" in text or "ecb" in text: eur += .20
            if "fed" in text or "dollar" in text or "usd" in text: usd += .20
            delta=eur-usd; nd="BUY" if delta>.55 else "SELL" if delta<-.55 else "WAIT"
            scored.append({"Title":str(r.get("headline") or r.get("title") or "")[:180], "Source":str(r.get("source") or "news"), "EUR Impact":round(eur,2), "USD Impact":round(usd,2), "News Direction":nd, "Published":str(r.get("publishedDate") or r.get("pubDate") or "")[:40]})
        df=pd.DataFrame(scored[:30])
        if df.empty:
            return {"summary":{"ok":False,"news_direction":"WAIT","news_sync":"LOW PRIORITY","message":"No EURUSD related news found."},"table":df}
        eur=float(pd.to_numeric(df["EUR Impact"],errors="coerce").fillna(0).mean()); usd=float(pd.to_numeric(df["USD Impact"],errors="coerce").fillna(0).mean())
        nd="BUY" if eur-usd>.35 else "SELL" if eur-usd<-.35 else "WAIT"
        sync="CONFIRM" if nd==master_dir and nd!="WAIT" else "CONFLICT" if nd in ("BUY","SELL") and master_dir in ("BUY","SELL") and nd!=master_dir else "NEUTRAL"
        return {"summary":{"ok":True,"news_direction":nd,"news_sync":sync,"weighted_eur_impact":round(eur,3),"weighted_usd_impact":round(usd,3),"articles_used":int(len(df)),"rule":"News confirms/warns only; PowerBI remains master."},"table":df}

    def _quant_structure(d: pd.DataFrame, master_regime: str) -> Dict[str, Any]:
        if not isinstance(d, pd.DataFrame) or len(d)<80: return {"ok":False,"message":"Need more EURUSD H1 candles."}
        c=pd.to_numeric(d.close,errors="coerce").dropna(); o=pd.to_numeric(d.open,errors="coerce").reindex(c.index).fillna(c); h=pd.to_numeric(d.high,errors="coerce").reindex(c.index).fillna(c); l=pd.to_numeric(d.low,errors="coerce").reindex(c.index).fillna(c)
        ret=c.pct_change().fillna(0); rng=(h-l).abs().replace(0,np.nan).ffill().fillna(c.abs()*0.0005)
        atr12=rng.rolling(12,min_periods=4).mean(); atr72=rng.rolling(72,min_periods=20).median(); ratio=(atr12/atr72.replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(1)
        comp=max(0,min(100,(1.25-float(ratio.iloc[-1]))/.75*100)); exp=max(0,min(100,comp*.55+min(45,abs(float(c.iloc[-1]-c.iloc[-6]))/max(float(atr12.iloc[-1]),1e-9)*13)))
        ma12=c.rolling(12,min_periods=4).mean(); ma48=c.rolling(48,min_periods=16).mean(); derived="BUY" if ma12.iloc[-1]>ma48.iloc[-1] else "SELL" if ma12.iloc[-1]<ma48.iloc[-1] else "WAIT"; md=_dir(master_regime)
        conflict="LOW" if derived==md or md=="WAIT" else "HIGH"; eff=abs(float(c.iloc[-1]-c.iloc[-24]))/max(float(c.diff().abs().tail(24).sum()),1e-9)
        z=(ret.abs()/ret.rolling(72,min_periods=20).std().replace(0,np.nan)).replace([np.inf,-np.inf],np.nan).fillna(0)
        after=max(0,min(100,int((z.tail(12)>2).sum())*16+float(z.tail(6).max())*18)); noise=max(0,min(100,float(((rng-(c-o).abs()).clip(lower=0)/rng).tail(48).mean())*100))
        trend=max(0,min(100,eff*100)); stability=max(0,min(100,100-after*.45-(25 if conflict=="HIGH" else 0)-noise*.18)); score=max(0,min(100,stability*.30+trend*.25+(100-noise)*.20+(100-after)*.25))
        last=float(c.iloc[-1]); band=max(float(atr12.iloc[-1]), last*.00035)*(1+after/180); sign=1 if md=="BUY" else -1 if md=="SELL" else 0; one= last + sign*band*min(1,score/100)*.55
        return {"ok":True,"quant_structure_score":round(score,1),"master_regime":master_regime,"master_direction":md,"compression_expansion":{"Compression Score":round(comp,1),"Expansion Probability":round(exp,1),"Time In Compression":int((ratio.tail(72)<.82).sum()),"Expansion Risk":"HIGH" if exp>=68 else "MEDIUM" if exp>=45 else "LOW"},"regime_vortex":{"Regime Stability":round(stability,1),"Regime Conflict":conflict,"Regime Strength":round(trend,1)},"cycle_drift":{"Dominant Cycle Length":"lightweight H1 rhythm","Cycle Drift Score":round(abs(float(ret.tail(24).mean()-ret.tail(96).mean()))*100000,1),"Cycle Change Warning":"WATCH"},"volatility_waterfall":{"H1 Volatility Energy":round(float(ret.tail(24).std())*10000,2),"H4 Volatility Energy":round(float(ret.rolling(4).sum().tail(42).std())*10000,2),"D1 Volatility Energy":round(float(ret.rolling(24).sum().tail(30).std())*10000,2),"Volatility Drift":round(float((ratio.tail(6).mean()-ratio.tail(72).median())*100),1)},"broadband_shock_signature":{"Shock Probability":round(min(100,float(z.iloc[-1])*28),1),"Shock Magnitude":round(abs(float(ret.iloc[-1]))*10000,2),"Shock Persistence":int((z.tail(12)>2).sum()),"Shock Recovery":round(max(0,100-after*.8),1)},"aftershock_engine":{"Recent Shock":"YES" if bool((z.tail(12)>2.4).any()) else "NO","Aftershock Risk":round(after,1),"Stabilization Score":round(max(0,100-after*.8),1)},"microstructure_reality":{"Noise Level":round(noise,1),"Trend Quality":round(trend,1),"Directional Efficiency":round(trend,1)},"sync_outputs":{"Next 1H Reasonable Direction":md if conflict!="HIGH" and score>=45 else "WAIT","Next 1H Reasonable Price":round(one,5),"Next 1H Lower Band":round(one-band,5),"Next 1H Upper Band":round(one+band,5),"Next Regime Update":"Continuation likely" if stability>=62 and after<55 else "Rotation watch"}}

    def _adjust_projection(d: pd.DataFrame, q: Dict[str, Any], news: Dict[str, Any]) -> pd.DataFrame:
        pred=st.session_state.get("dv_pp_predicted", pd.DataFrame())
        if not isinstance(d,pd.DataFrame) or d.empty: return pd.DataFrame()
        last=float(pd.to_numeric(d.close,errors="coerce").dropna().iloc[-1]); atr=max(float((pd.to_numeric(d.high)-pd.to_numeric(d.low)).tail(14).mean() or 0), last*.00035)
        md=q.get("master_direction", _dir(_master_regime())) if isinstance(q,dict) else _dir(_master_regime()); sign=1 if md=="BUY" else -1 if md=="SELL" else 0
        score=_num(q.get("quant_structure_score",55) if isinstance(q,dict) else 55,55)/100; after=_num(q.get("aftershock_engine",{}).get("Aftershock Risk",0) if isinstance(q,dict) else 0,0)/100
        rel=(news.get("summary",{}) if isinstance(news,dict) else {}).get("news_sync","NEUTRAL"); shift=.10 if rel=="CONFIRM" else -.08 if rel=="CONFLICT" else 0
        rows=[]
        for step in range(1,7):
            raw=last+sign*atr*math.sqrt(step)*(.35+score*.55); adj=raw+sign*atr*shift*math.sqrt(step); band=atr*math.sqrt(step)*(1.0+after*.65)
            rows.append({"Priority Rank":step,"Step":step,"Master Direction":md,"Reasonable Direction":md if sign else "WAIT","Reasonable Price":round(adj,5),"Upper Band":round(adj+band,5),"Lower Band":round(adj-band,5),"Accuracy/Structure Confidence":round(max(5,min(95,55+score*35-after*18)),1),"News Sync":rel})
        return pd.DataFrame(rows)

    def _priority_table(q: Dict[str,Any], news: Dict[str,Any], proj: pd.DataFrame) -> pd.DataFrame:
        md = q.get("master_direction", _dir(_master_regime())) if isinstance(q,dict) else _dir(_master_regime())
        rel = (news.get("summary",{}) if isinstance(news,dict) else {}).get("news_sync","NEUTRAL")
        base = _num(q.get("quant_structure_score",50) if isinstance(q,dict) else 50,50)
        rows=[]
        comps=[("PowerBI master regime", 92 if md in ("BUY","SELL") else 45, f"{_master_regime()} => {md}"),("News/NLP conflict filter", 88 if rel=="CONFIRM" else 52 if rel=="NEUTRAL" else 25, rel),("Quant structure", base, "compression/regime/cycle/shock/microstructure"),("Next 1H projection", _num(proj.iloc[0].get("Accuracy/Structure Confidence"),50) if isinstance(proj,pd.DataFrame) and not proj.empty else 50, "accuracy adjusted path"),("NY/London home sync", 72 if isinstance(st.session_state.get("nylo_unified_home_sync_20260612"),dict) else 45, "current H1 only")]
        for name, score, reason in comps:
            label = f"{md} allowed" if score>=70 and md in ("BUY","SELL") and rel!="CONFLICT" else "Conflict: no trade" if rel=="CONFLICT" else "WATCH / WAIT" if score>=50 else "Avoid"
            rows.append({"Priority Rank":len(rows)+1,"Priority Source":name,"Greedy Score":round(float(score),1),"Master Direction":md,"Prescriptive Label":label,"Reason":reason})
        return pd.DataFrame(rows).sort_values(["Priority Rank"], ascending=True).reset_index(drop=True)

    def _run_unified_intelligence(mode: str, finnhub: str, fmp: str, limit: int, start_hour: int) -> Dict[str,Any]:
        d=_prep_ohlc(6000); reg=_master_regime(); md=_dir(reg)
        q=_quant_structure(d, reg)
        rows, src=_fetch_news(mode, finnhub.strip(), fmp.strip(), int(limit))
        news=_score_news(rows, md); news["source"]=src
        proj=_adjust_projection(d, q if isinstance(q,dict) else {}, news)
        pr=_priority_table(q if isinstance(q,dict) else {}, news, proj)
        nylo={}
        build_nylo=ns.get("_build_synced_nylo_20260612")
        if callable(build_nylo):
            try:
                nylo=build_nylo(int(start_hour))
                st.session_state["nylo_unified_home_sync_20260612"]=nylo
            except Exception as exc:
                nylo={"ok":False,"message":str(exc)}
        tech={}
        tech_fn=ns.get("_u11_compute_technical_logic")
        if callable(tech_fn):
            try:
                tech=tech_fn(d, st.session_state.get("dv_pp_base_result",{}), st.session_state.get("dv_pp_predicted",pd.DataFrame()), horizon=24)
            except Exception as exc:
                tech={"message":str(exc)}
        story=f"Unified PowerBI regime is {reg}, master direction is {md}. News/NLP is {news.get('summary',{}).get('news_sync','NEUTRAL')}. Quant structure score is {q.get('quant_structure_score','-') if isinstance(q,dict) else '-'}; next 1H follows master unless conflict is high."
        payload={"export_type":"FINAL_MERGED_DV_HOME_INTELLIGENCE_20260612","built_at":str(pd.Timestamp.now()),"symbol":"EURUSD","timeframe":"H1","master_regime":reg,"master_direction":md,"market_story":story,"news_nlp":news,"quant_structure":q,"accuracy_adjusted_projection":proj,"knn_greedy_priority":pr,"ny_london_home_sync":nylo,"technical_logic":tech}
        text=_json(payload,160)
        st.session_state["final_merged_intelligence_pack_20260612"]=payload
        st.session_state["final_merged_intelligence_export_20260612"]=text
        st.session_state["lunch_visualization_export"] = str(st.session_state.get("lunch_visualization_export", "")) + "\n\n" + text
        return payload

    def _chart_projection(proj: pd.DataFrame) -> None:
        if not isinstance(proj,pd.DataFrame) or proj.empty: st.info("Run merged intelligence to build projection."); return
        fig=go.Figure(); x=proj["Step"] if "Step" in proj.columns else proj.index+1
        fig.add_trace(go.Scatter(x=x,y=proj["Reasonable Price"],mode="lines+markers",name="Reasonable path"))
        fig.add_trace(go.Scatter(x=x,y=proj["Upper Band"],mode="lines",name="Upper band"))
        fig.add_trace(go.Scatter(x=x,y=proj["Lower Band"],mode="lines",name="Lower band"))
        fig.update_layout(height=330,margin=dict(l=6,r=6,t=30,b=6),xaxis_title="Next H1 step",yaxis_title="EURUSD")
        st.plotly_chart(fig,use_container_width=True,config={"displayModeBar":False,"responsive":True})

    def _render_merged_under_powerbi() -> None:
        with st.expander("🧠 Open / Close — Final Merged Intelligence: Upload + KNN/Greedy + News/NLP + Quant Structure + NY/London Home Sync", expanded=False):
            st.caption("One clean field under PowerBI. Manual-run only. It merges previous Data Visualization add-ons and Home NY/London sync without letting News/NLP override PowerBI.")
            c=st.columns([1.05,1,1,.75,.75])
            try:
                from core.finnhub_connector import connection_status, get_session_key
                _fh = connection_status(); fin = get_session_key()
                c[0].metric("Finnhub", "CONNECTED" if _fh.get("connected") else "DISCONNECTED", _fh.get("availability", "UNKNOWN"))
            except Exception:
                fin = ""; c[0].metric("Finnhub", "DISCONNECTED", "Use sidebar connector")
            fmp=c[1].text_input("FMP API key backup", value=st.session_state.get("dv_nlp_fmp_key_saved", ""), type="password", key=f"final_fmp_{UNIQUE}")
            mode=c[2].selectbox("News source", ["Finnhub first","FMP first","RSS only"], key=f"final_news_mode_{UNIQUE}")
            limit=c[3].selectbox("News limit", [8,12,20,30], index=1, key=f"final_news_limit_{UNIQUE}")
            start=c[4].selectbox("NY/London start", list(range(24)), index=int(st.session_state.get("nylo_start_hour_final",21)) if int(st.session_state.get("nylo_start_hour_final",21)) in range(24) else 21, key=f"final_nylo_start_{UNIQUE}")
            st.session_state["dv_nlp_fmp_key_saved"]=fmp; st.session_state["nylo_start_hour_final"]=int(start)
            r1,r2,r3=st.columns([1,1,1])
            run=r1.button("▶ Run Final Merged Intelligence", use_container_width=True, key=f"final_run_{UNIQUE}")
            if r2.button("📱 Toggle Real Mobile Big UI", use_container_width=True, key=f"final_mobile_toggle_{UNIQUE}"):
                st.session_state["mobile_app_big_mode_20260612"] = not bool(st.session_state.get("mobile_app_big_mode_20260612",False)); st.rerun()
            if r3.button("🔄 Refresh Cached Display", use_container_width=True, key=f"final_refresh_{UNIQUE}"):
                st.session_state.pop("final_merged_intelligence_pack_20260612", None); st.rerun()
            if run:
                with st.spinner("Building one synced KNN/Greedy + NLP + Quant + NY/London intelligence pack…"):
                    payload=_run_unified_intelligence(mode, fin, fmp, int(limit), int(start))
                st.success("Final merged intelligence is synced and copy exports are updated.")
            payload=st.session_state.get("final_merged_intelligence_pack_20260612", {})
            if not isinstance(payload,dict) or not payload:
                st.info("Press **Run Final Merged Intelligence**. Nothing heavy/API-based runs on page load."); return
            m=st.columns(6); q=payload.get("quant_structure",{}); nsumm=payload.get("news_nlp",{}).get("summary",{}); proj=payload.get("accuracy_adjusted_projection",pd.DataFrame()); pr=payload.get("knn_greedy_priority",pd.DataFrame())
            m[0].metric("Master Regime", payload.get("master_regime","-")); m[1].metric("Master Dir", payload.get("master_direction","WAIT")); m[2].metric("News Sync", nsumm.get("news_sync","NEUTRAL")); m[3].metric("Structure Score", q.get("quant_structure_score","-") if isinstance(q,dict) else "-"); m[4].metric("Next 1H", (q.get("sync_outputs",{}) if isinstance(q,dict) else {}).get("Next 1H Reasonable Direction","WAIT")); m[5].metric("Top Priority", pr.iloc[0].get("Prescriptive Label","-") if isinstance(pr,pd.DataFrame) and not pr.empty else "-")
            st.info(payload.get("market_story",""))
            t=st.tabs(["Priority", "Projection", "News/NLP", "Quant Structure", "NY/London + Home", "Copy"])
            with t[0]:
                if isinstance(pr,pd.DataFrame) and not pr.empty: st.dataframe(pr, use_container_width=True, hide_index=True, height=280)
            with t[1]:
                _chart_projection(proj if isinstance(proj,pd.DataFrame) else pd.DataFrame())
                if isinstance(proj,pd.DataFrame) and not proj.empty: st.dataframe(proj, use_container_width=True, hide_index=True, height=230)
            with t[2]:
                st.json(nsumm); nt=payload.get("news_nlp",{}).get("table",pd.DataFrame())
                if isinstance(nt,pd.DataFrame) and not nt.empty: st.dataframe(nt, use_container_width=True, hide_index=True, height=280)
            with t[3]: st.json(_safe(q,80))
            with t[4]: st.json(_safe(payload.get("ny_london_home_sync",{}),80))
            with t[5]:
                full=st.session_state.get("final_merged_intelligence_export_20260612", _json(payload,160))
                lines=full.splitlines()[:100]
                compact="\n".join(lines)
                cc=st.columns(2)
                with cc[0]: _copy_button("Copy Necessary 100 Lines", compact, f"copy_final_necessary_{UNIQUE}")
                with cc[1]: _copy_button("Copy Full Merged Intelligence", full, f"copy_final_full_{UNIQUE}")

    def _render_powerbi_only_then_merged() -> None:
        _app_css()
        st.markdown("### 📊 Data Visualization — One Unified PowerBI Price Projection")
        st.caption("One PowerBI projection first; all added intelligence is merged into one open/close field below it.")
        c=st.columns([1.1,.72,.72,.72,.72,.72])
        run=c[0].button("▶ Run Calculating", use_container_width=True, key=f"dv_run_calculating_{UNIQUE}")
        rows=c[1].slider("Rows used", 800, 12000, int(st.session_state.get("dv_pp_rows_v6",6000)), 400, key=f"dv_rows_{UNIQUE}")
        horizon=c[2].slider("Future candles", 6, 60, int(st.session_state.get("dv_pp_horizon_v6",24)), 6, key=f"dv_horizon_{UNIQUE}")
        yellow=c[3].slider("Yellow prev hours", 1, 12, int(st.session_state.get("yellow_horizon_v6",6)), 1, key=f"dv_yellow_{UNIQUE}")
        mode=c[4].selectbox("Projection choice", ["Balanced","Trend follow","Pullback safer"], key=f"dv_mode_{UNIQUE}")
        risk=c[5].selectbox("Risk filter", ["Low","Medium","High"], index=1, key=f"dv_risk_{UNIQUE}")
        m=st.columns(3); min_days=m[0].slider("Regime min days",3,21,int(st.session_state.get("dv_pp_min_days_v6",5)),1,key=f"dv_mindays_{UNIQUE}"); bt=m[1].slider("Backtest bars",60,360,int(st.session_state.get("dv_pp_bt_v6",180)),20,key=f"dv_bt_{UNIQUE}")
        if m[2].button("📱 Real Mobile Big Mode", use_container_width=True, key=f"dv_phone_big_{UNIQUE}"):
            st.session_state["mobile_app_big_mode_20260612"] = not bool(st.session_state.get("mobile_app_big_mode_20260612",False)); st.rerun()
        if run:
            st.session_state["lunch_bi_visual_ready"]=True
            with st.spinner("Calculating unified PowerBI projection and ML tables…"):
                clean_f=ns.get("_clean_lunch_visual_df"); prep=ns.get("_dv_prepare_ohlc_v20260609")
                clean=clean_f(limit=int(rows)) if callable(clean_f) else st.session_state.get("last_df", pd.DataFrame())
                d=prep(clean, limit=int(rows)) if callable(prep) else _prep_ohlc(int(rows))
                if not isinstance(d,pd.DataFrame) or len(d)<120: st.warning("Need at least 120 clean OHLC candles."); return
                result=ns.get("_five_layer_powerbi_calculate")(d, horizon=int(horizon)) if callable(ns.get("_five_layer_powerbi_calculate")) else {}
                pred=ns.get("_dv_predict_future_candles_v20260609")(d, horizon=int(horizon)) if callable(ns.get("_dv_predict_future_candles_v20260609")) else pd.DataFrame()
                bt_hist,bt_sum=ns.get("_dv_prediction_vs_actual_history_v20260609")(d, lookback=int(bt), horizon=1) if callable(ns.get("_dv_prediction_vs_actual_history_v20260609")) else (pd.DataFrame(),{})
                reg,reg_hist=ns.get("_dv_major_regime_detector_v20260609")(d, min_days=float(min_days), lookback_days=240, horizon=int(horizon)) if callable(ns.get("_dv_major_regime_detector_v20260609")) else ({},pd.DataFrame())
                st.session_state.update({"dv_pp_df":d,"dv_pp_base_result":result,"dv_pp_predicted":pred,"dv_pp_bt_summary":bt_sum,"dv_pp_bt_hist":bt_hist,"dv_pp_regime_summary":reg,"dv_pp_regime_hist":reg_hist,"lunch_5layer_powerbi_result":result,"lunch_5layer_powerbi_df":d})
            st.success("Unified Data Visualization result is ready.")
        if not st.session_state.get("lunch_bi_visual_ready",False): st.info("Press Run Calculating first. No heavy calculation runs on open."); return
        d=st.session_state.get("dv_pp_df",pd.DataFrame()); result=st.session_state.get("dv_pp_base_result",{}); pred=st.session_state.get("dv_pp_predicted",pd.DataFrame()); reg=st.session_state.get("dv_pp_regime_summary",{}); bt_sum=st.session_state.get("dv_pp_bt_summary",{})
        cards=st.columns(6); cards[0].metric("Master", f"{result.get('master_score','-')}/10" if isinstance(result,dict) else "-"); cards[1].metric("Bull", f"{result.get('bull_probability','-')}%" if isinstance(result,dict) else "-"); cards[2].metric("Regime", reg.get("current_regime","-") if isinstance(reg,dict) else "-"); cards[3].metric("Master Dir", _dir(reg.get("current_regime","")) if isinstance(reg,dict) else "WAIT"); cards[4].metric("BT Acc", f"{bt_sum.get('direction_accuracy_pct',0)}%" if isinstance(bt_sum,dict) else "-"); cards[5].metric("BT Error", f"{bt_sum.get('avg_abs_close_error_pct',0)}%" if isinstance(bt_sum,dict) else "-")
        chart=ns.get("_render_unified_powerbi_projection_chart_v6")
        if callable(chart): chart(d,pred,result,reg,horizon=int(horizon),yellow_horizon=int(yellow),mode=mode,risk_filter=risk)
        with st.expander("🧠 ML Tables — kept from original 5-layer PowerBI", expanded=False):
            if isinstance(result,dict):
                for label,key in [("Prediction Ensemble Voting","vote_df"),("Deep AI Table","deep_df"),("Forecast Engine Table","forecast_df"),("History / Layer Table","history")]:
                    val=result.get(key)
                    if isinstance(val,pd.DataFrame) and not val.empty: st.markdown("#### "+label); st.dataframe(val,use_container_width=True,hide_index=True,height=240)
        _render_merged_under_powerbi()

    prev_copy = ns.get("_build_lunch_all_copy_text")
    def _build_copy() -> str:
        base = prev_copy() if callable(prev_copy) else ""
        extra = st.session_state.get("final_merged_intelligence_export_20260612") or "Final merged intelligence not run yet."
        dv_research = st.session_state.get("dv_research_alignment_export_20260612") or "DV research accuracy upgrade not run yet."
        research = st.session_state.get("research_export_20260612") or "Research tab pack not run yet."
        return (
            str(base)
            + "\n\nFINAL MERGED DATA VISUALIZATION + HOME INTELLIGENCE 2026-06-12\n" + "="*78 + "\n" + str(extra)
            + "\n\nDATA VISUALIZATION RESEARCH ACCURACY UPGRADE 2026-06-12\n" + "="*78 + "\n" + str(dv_research)
            + "\n\nRESEARCH TAB EXPORT 2026-06-12\n" + "="*78 + "\n" + str(research)
        )

    def _home_top_copy() -> None:
        full=_build_copy(); compact="\n".join(full.splitlines()[:100])
        c=st.columns(2)
        with c[0]: _copy_button("📋 Copy Necessary 100 Lines — Current H1", compact, f"home_copy_100_{UNIQUE}")
        with c[1]: _copy_button("📋 Copy Full Home H1", full, f"home_copy_full_{UNIQUE}")

    prev_lunch = ns.get("_render_metric_home_combined_inner_tab")
    def _render_lunch() -> None:
        # 2026-06-14 user request: hide the extra App Login / Logout — saved locally section inside Lunch.
        # The main login gate remains in core.light_auth_20260612; only this duplicated Lunch-local panel is hidden.
        _app_css(); st.session_state["lunch_local_login_panel_hidden_20260614"] = True; _home_top_copy()
        if callable(prev_lunch): prev_lunch()

    prev_finder = ns.get("_render_doo_finder")
    def _finder(results=None):
        if callable(prev_finder):
            try: prev_finder(results)
            except TypeError: prev_finder()
        with st.expander("🧠 Finder Sync — Final Merged Data Visualization/Home Intelligence", expanded=False):
            pack=st.session_state.get("final_merged_intelligence_pack_20260612",{})
            if not isinstance(pack,dict) or not pack: st.info("Run Data Visualization → Final Merged Intelligence first."); return
            c=st.columns(5); c[0].metric("Regime",pack.get("master_regime","-")); c[1].metric("Dir",pack.get("master_direction","WAIT")); c[2].metric("News",pack.get("news_nlp",{}).get("summary",{}).get("news_sync","NEUTRAL")); c[3].metric("Structure",pack.get("quant_structure",{}).get("quant_structure_score","-")); c[4].metric("Next 1H",pack.get("quant_structure",{}).get("sync_outputs",{}).get("Next 1H Reasonable Direction","WAIT"))
            pr=pack.get("knn_greedy_priority",pd.DataFrame())
            if isinstance(pr,pd.DataFrame) and not pr.empty: st.dataframe(pr,use_container_width=True,hide_index=True,height=240)

    ns["_render_lunch_data_visualization_inner_tab"] = _render_powerbi_only_then_merged
    ns["_render_metric_home_combined_inner_tab"] = _render_lunch
    ns["_build_lunch_all_copy_text"] = _build_copy
    ns["_render_doo_finder"] = _finder
    ns["_render_final_merged_intelligence_20260612"] = _render_merged_under_powerbi
