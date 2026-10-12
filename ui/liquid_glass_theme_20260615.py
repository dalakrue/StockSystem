"""Liquid-glass UI layer for the stable Streamlit shell.

Normal Streamlit/CSS only. No JavaScript DOM open/close hacks. All drawer/menu
state is handled through st.session_state buttons.
"""
from __future__ import annotations
import streamlit as st


def apply_liquid_glass_theme() -> None:
    st.markdown(
        """
<style id="new7-liquid-glass-theme-20260615">
:root{
  --lg-bg1:#dff5ff;--lg-bg2:#eaf8ff;--lg-ink:#0f172a;--lg-muted:#64748b;
  --lg-border:rgba(255,255,255,.52);--lg-line:rgba(15,23,42,.08);--lg-blue:rgba(56,189,248,.34);
  --lg-shadow:0 22px 58px rgba(15,23,42,.16), inset 0 1px 0 rgba(255,255,255,.72);
}
html,body,[data-testid="stAppViewContainer"]{
  background:
    radial-gradient(circle at 8% 2%, rgba(125,211,252,.50), transparent 28%),
    radial-gradient(circle at 94% 4%, rgba(186,230,253,.68), transparent 31%),
    linear-gradient(135deg,#eefaff 0%,#dbeafe 42%,#f8fafc 100%)!important;
}
.main .block-container{max-width:1240px;padding-top:.48rem!important;}
.new7-liquid-rail,.new7-liquid-drawer,.new7-floating-control,.new7-top-status,.new7-modern-card,.new7-card,.ai-lite-shell{
  border:1px solid var(--lg-border)!important;
  background:linear-gradient(140deg,rgba(255,255,255,.52),rgba(224,242,254,.35) 52%,rgba(255,255,255,.32))!important;
  box-shadow:var(--lg-shadow)!important;
  backdrop-filter:blur(22px) saturate(170%)!important;-webkit-backdrop-filter:blur(22px) saturate(170%)!important;
}
.new7-liquid-rail{position:sticky;top:.16rem;z-index:80;border-radius:28px;padding:10px 12px;margin:.18rem 0 .50rem;}
.new7-liquid-row{display:flex;align-items:center;gap:9px;flex-wrap:wrap;}
.new7-liquid-brand{font-weight:1000;font-size:1.02rem;color:var(--lg-ink);letter-spacing:-.02em;display:flex;align-items:center;gap:7px;}
.new7-liquid-dots{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:999px;background:rgba(255,255,255,.48);border:1px solid rgba(255,255,255,.62);box-shadow:inset 0 1px 0 rgba(255,255,255,.72),0 10px 24px rgba(15,23,42,.08);font-size:1.18rem;line-height:1;color:#0f172a;}
.new7-liquid-chip{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:5px 10px;background:rgba(255,255,255,.44);border:1px solid rgba(255,255,255,.52);font-size:.72rem;font-weight:950;color:#334155;box-shadow:inset 0 1px 0 rgba(255,255,255,.62)}
.new7-liquid-drawer{border-radius:30px;padding:14px;margin:.30rem 0 .70rem;}
.new7-liquid-drawer-title{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:8px;}
.new7-liquid-section{border:1px solid rgba(255,255,255,.45);border-radius:24px;background:rgba(255,255,255,.30);padding:12px;margin:8px 0;}
.stButton>button,.stDownloadButton>button{border-radius:18px!important;border:1px solid rgba(255,255,255,.52)!important;background:linear-gradient(135deg,rgba(255,255,255,.72),rgba(224,242,254,.52))!important;color:#0f172a!important;font-weight:950!important;box-shadow:0 10px 28px rgba(15,23,42,.08),inset 0 1px 0 rgba(255,255,255,.82)!important;}
.stButton>button:hover,.stDownloadButton>button:hover{border-color:rgba(14,165,233,.48)!important;box-shadow:0 12px 32px rgba(14,165,233,.16),inset 0 1px 0 rgba(255,255,255,.88)!important;}
div[data-testid="stSelectbox"]>div,div[data-baseweb="select"],input,textarea{border-radius:18px!important;}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,rgba(255,255,255,.60),rgba(224,242,254,.38))!important;backdrop-filter:blur(22px) saturate(170%)!important;-webkit-backdrop-filter:blur(22px) saturate(170%)!important;border-right:1px solid rgba(255,255,255,.55)!important;box-shadow:16px 0 48px rgba(15,23,42,.14)!important;}
section[data-testid="stSidebar"] .block-container{padding:.75rem .65rem!important;}
section[data-testid="stSidebar"] *{color:#0f172a;}
.new7-glass-mini-sidebar{border-radius:999px;padding:10px;background:rgba(255,255,255,.44);border:1px solid rgba(255,255,255,.58);box-shadow:0 18px 42px rgba(15,23,42,.11);}
@media(max-width:780px){.main .block-container{padding-left:.42rem!important;padding-right:.42rem!important}.new7-liquid-rail{border-radius:22px;padding:8px 9px;top:.05rem}.new7-liquid-drawer{border-radius:22px;padding:10px}.new7-liquid-brand{font-size:.92rem}.new7-liquid-chip{font-size:.66rem;padding:4px 8px}.new7-liquid-row{gap:5px}.stButton>button,.stDownloadButton>button{min-height:44px!important;font-size:.78rem!important;padding:.38rem .45rem!important}}
@media(max-width:390px){.new7-liquid-chip.hide-phone{display:none}.new7-liquid-rail{border-radius:20px}.new7-liquid-drawer{border-radius:20px}}
</style>
        """,
        unsafe_allow_html=True,
    )
