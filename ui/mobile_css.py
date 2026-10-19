"""Central mobile/CSS injector for the future-proof app shell."""
from __future__ import annotations
import streamlit as st


def inject_mobile_css() -> None:
    st.session_state["future_mobile_css_loaded"] = True
    phone = bool(st.session_state.get("phone_mode", False))
    phone_css = """
    .main .block-container{max-width:100%!important;padding-left:.28rem!important;padding-right:.28rem!important;padding-top:.32rem!important}
    .stApp{font-size:15px!important}
    .stButton>button{min-height:42px!important;font-size:.82rem!important;padding:.35rem .42rem!important}
    [data-testid="stMetric"]{padding:.46rem .48rem!important;min-height:76px!important;height:auto!important;min-width:0!important;overflow:visible!important}
    [data-testid="stMetricValue"]{font-size:clamp(1rem,5vw,1.28rem)!important;line-height:1.06!important;white-space:normal!important;overflow-wrap:anywhere!important;word-break:break-word!important}
    [data-testid="stMetricLabel"]{font-size:.74rem!important;line-height:1.08!important;white-space:normal!important;overflow-wrap:anywhere!important}
    [data-testid="stMetricDelta"]{font-size:.68rem!important;white-space:normal!important}
    [data-testid="column"]{min-width:0!important}
    input,textarea,[data-baseweb="select"]>div{font-size:.90rem!important;min-height:43px!important}
    div[data-testid="stDataFrame"]{font-size:.78rem!important;max-width:100%!important;overflow:auto!important}
    section[data-testid="stSidebar"]{min-width:min(52vw,190px)!important;max-width:min(52vw,190px)!important}
    details summary{min-height:38px!important;font-size:.80rem!important}
    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]){flex-wrap:wrap!important;align-items:stretch!important}
    div[data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) > div[data-testid="column"]{flex:1 1 calc(50% - .38rem)!important;min-width:142px!important;width:auto!important}
    .new7-card,.new7-top-status,.new7-health-card,[data-testid="stMetric"]{box-shadow:none!important;backdrop-filter:none!important;-webkit-backdrop-filter:none!important}
    """ if phone else ""
    st.markdown(f"""
<style id="new7-future-mobile-css-20260617">
:root{{--new7-card-radius:24px;--new7-soft-border:rgba(15,23,42,.08);--new7-soft-shadow:0 16px 42px rgba(15,23,42,.075);}}
.main .block-container{{padding-top:.72rem!important;}}
.new7-card,.new7-top-status,.new7-health-card{{border:1px solid var(--new7-soft-border);border-radius:var(--new7-card-radius);background:linear-gradient(145deg,rgba(255,255,255,.88),rgba(239,246,255,.66));box-shadow:var(--new7-soft-shadow);padding:.82rem .92rem;margin:.42rem 0;}}
.new7-top-status{{position:sticky;top:.18rem;z-index:50;backdrop-filter:blur(16px) saturate(160%);-webkit-backdrop-filter:blur(16px) saturate(160%);}}
.new7-status-line{{display:flex;flex-wrap:wrap;gap:.34rem;align-items:center;color:#475569;font-size:.76rem;line-height:1.28;}}
.new7-pill{{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;padding:.24rem .58rem;background:rgba(255,255,255,.74);border:1px solid rgba(14,116,144,.10);font-weight:850;color:#334155;font-size:.74rem;}}
.stButton>button{{min-height:44px!important;border-radius:18px!important;font-weight:900!important;box-shadow:0 8px 22px rgba(15,23,42,.045)!important;}}
div[data-testid="stDataFrame"], div[data-testid="stTable"]{{overflow-x:auto!important;}}
[data-testid="stMetric"]{{border-radius:18px!important;}}
textarea,input{{border-radius:16px!important;}}
@media(max-width:780px){{.main .block-container{{padding-left:.50rem!important;padding-right:.50rem!important;padding-top:.48rem!important;}}.new7-card,.new7-top-status,.new7-health-card{{border-radius:22px;padding:.68rem .70rem;margin:.34rem 0;}}.new7-status-line{{gap:.24rem;font-size:.72rem;}}.new7-pill{{font-size:.69rem;padding:.20rem .44rem;}}div[data-testid="stHorizontalBlock"]{{gap:.38rem!important;}}.stButton>button{{min-height:46px!important;font-size:.82rem!important;padding:.45rem .52rem!important;}}}}
{phone_css}
</style>
""", unsafe_allow_html=True)
