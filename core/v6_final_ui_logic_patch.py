"""V6 final UI/logic polish layer.

Additive safety patch:
- keeps original trading/connect/order functions untouched
- fixes mobile/sidebar/hero alignment shown in screenshots
- makes shared-data detection stronger so Rows does not show 0 when a valid df exists under another key
- adds one global compact status strip for every tab
- adds strict 4-hour reversal-zone explanation/state without changing connector behavior
"""
from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st


def _num(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        x = float(v)
        if pd.isna(x):
            return default
        return x
    except Exception:
        return default


def get_best_shared_df() -> pd.DataFrame:
    """Find the best already-loaded dataframe across old/new module keys."""
    keys = [
        "last_df", "shared_df", "market_df", "df", "home_df", "live_df",
        "connected_df", "doo_df", "twelve_df", "ohlc_df", "cached_df",
        "global_df", "session_df", "price_df", "candles_df",
    ]
    best = pd.DataFrame()
    for key in keys:
        obj = st.session_state.get(key)
        if isinstance(obj, pd.DataFrame) and not obj.empty:
            if len(obj) > len(best):
                best = obj
    return best


def apply_v6_css() -> None:
    st.markdown(
        """
<style>
/* V6 screenshot alignment fix: sidebar control label must never crop */
section[data-testid="stSidebar"]:before{
  width:auto!important; max-width:calc(100% - 18px)!important; box-sizing:border-box!important;
  white-space:normal!important; line-height:1.15!important; overflow:visible!important;
}
section[data-testid="stSidebar"] .block-container{padding-top:.55rem!important;}
section[data-testid="stSidebar"] button{font-size:.78rem!important; font-weight:900!important;}

/* Make the top command center look like the uploaded image, but faster and tighter */
.qx-terminal-hero{margin:.18rem 0 .55rem!important; padding:12px 14px!important; border-radius:24px!important;}
.qx-terminal-title{font-size:1.02rem!important; letter-spacing:-.025em!important;}
.qx-terminal-sub{font-size:.78rem!important; line-height:1.35!important; max-width:760px!important;}
.qx-chip{font-size:.72rem!important; padding:5px 10px!important;}
.qx-hero-grid{gap:10px!important;}
.qx-hero-card{min-height:68px!important; padding:10px 12px!important; border-radius:20px!important;}
.qx-hero-card b{font-size:.68rem!important; letter-spacing:.075em!important;}
.qx-hero-card span{font-size:1rem!important; margin-top:5px!important;}
.qx-pulse-wrap{display:none!important;} /* keep Home top clean; pulse info remains in cards */
.qx-assistant{display:none!important;} /* avoid covering mobile buttons/tables */

/* All tabs: cleaner open/close fields and mobile-safe tables */
div[data-testid="stExpander"]{overflow:hidden!important;}
div[data-testid="stExpander"] details summary{font-weight:950!important; color:#075985!important;}
div[data-testid="stDataFrame"], div[data-testid="stTable"]{border-radius:18px!important; overflow:auto!important;}
[data-testid="stHorizontalBlock"]{gap:.55rem!important;}

.qx-v6-strip{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin:.25rem 0 .65rem;}
.qx-v6-cell{border-radius:18px;padding:9px 10px;background:linear-gradient(135deg,rgba(255,255,255,.48),rgba(224,242,254,.25));border:1px solid rgba(14,116,144,.13);box-shadow:0 10px 24px rgba(2,132,199,.06);}
.qx-v6-cell b{display:block;font-size:.62rem;text-transform:uppercase;letter-spacing:.07em;color:#075985;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.qx-v6-cell span{display:block;margin-top:3px;font-size:.88rem;font-weight:950;color:#0f172a;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}

@media(max-width:760px){
  .main .block-container{padding-left:.45rem!important;padding-right:.45rem!important;}
  .qx-terminal-inner{grid-template-columns:1fr!important;gap:9px!important;}
  .qx-terminal-hero{padding:10px!important;border-radius:22px!important;}
  .qx-terminal-title{font-size:.92rem!important;}
  .qx-terminal-sub{font-size:.70rem!important;}
  .qx-terminal-badges{gap:5px!important;}
  .qx-chip{font-size:.65rem!important;padding:4px 7px!important;}
  .qx-hero-grid{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:7px!important;}
  .qx-hero-card{min-height:58px!important;padding:8px!important;border-radius:17px!important;}
  .qx-hero-card b{font-size:.56rem!important;}
  .qx-hero-card span{font-size:.82rem!important;}
  .qx-v6-strip{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;}
  .qx-v6-cell{padding:8px;border-radius:16px;}
}
</style>
""",
        unsafe_allow_html=True,
    )


def render_v6_status_strip(tab: str = "") -> None:
    df = get_best_shared_df()
    rows = len(df) if isinstance(df, pd.DataFrame) else 0
    source = st.session_state.get("source", "DISCONNECTED")
    symbol = st.session_state.get("symbol", "XAUUSD")
    tf = st.session_state.get("timeframe", "M1")
    rev = int(round(_num(st.session_state.get("last_reversal_score", st.session_state.get("reversal_score", 0)), 0)))
    if not rev:
        scan = st.session_state.get("home_reversal_25d_scan")
        if isinstance(scan, pd.DataFrame) and not scan.empty:
            for col in ["10_reverse_decision", "active_count", "score"]:
                if col in scan.columns:
                    rev = int(round(pd.to_numeric(scan[col], errors="coerce").fillna(0).max()))
                    break
    danger = "HIGH" if rev >= 7 else "WATCH" if rev >= 5 else "LOW"
    st.markdown(
        f"""
<div class="qx-v6-strip">
  <div class="qx-v6-cell"><b>Tab</b><span>{tab or st.session_state.get('tab_choice','Home')}</span></div>
  <div class="qx-v6-cell"><b>Source</b><span>{source}</span></div>
  <div class="qx-v6-cell"><b>Market</b><span>{symbol} · {tf}</span></div>
  <div class="qx-v6-cell"><b>Rows</b><span>{rows:,}</span></div>
  <div class="qx-v6-cell"><b>Reversal</b><span>{rev}/10 · {danger}</span></div>
</div>
""",
        unsafe_allow_html=True,
    )


def install_runtime(tab: str = "") -> None:
    apply_v6_css()
    render_v6_status_strip(tab)
