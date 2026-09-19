# Cloud-safe flattened implementation.
# Generated from preserved V9 SOURCE_LINES without changing implementation logic.
# Runtime no longer depends on *_v9_parts folders.

"""Self-contained global Streamlit styles.

This module is intentionally flattened for Streamlit Cloud reliability.  The
older split source chunks remain in ``styles_impl_parts`` as an archive, but
runtime imports no longer depend on that package being discovered.
"""

try:
    import streamlit as st
except Exception:  # Allows Cloud preflight/import tests before dependencies install.
    class _StreamlitFallback:
        session_state = {}
        def __getattr__(self, _name):
            return lambda *args, **kwargs: None
    st = _StreamlitFallback()


def apply_global_styles(phone_mode: bool = False):
    maxw = "100vw" if phone_mode else "1180px"
    pad = "0.30rem" if phone_mode else "0.85rem 1.20rem"
    font = "10.8px" if phone_mode else "11.5px"
    h1 = "1.02rem" if phone_mode else "1.35rem"
    h2 = "0.90rem" if phone_mode else "1.12rem"
    h3 = "0.82rem" if phone_mode else "0.98rem"
    btn_h = "34px" if phone_mode else "38px"
    metric_v = "16.5px" if phone_mode else "19px"
    tab_font = "9px" if phone_mode else "10.5px"
    card_pad = "6px" if phone_mode else "11px"
    radius = "13px" if phone_mode else "18px"

    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {{
  --glass: rgba(255,255,255,.78);
  --glass2: rgba(240,249,255,.64);
  --line: rgba(14,116,144,.16);
  --txt:#0f172a;
  --muted:#075985;
  --blue:#38bdf8;
  --green:#16a34a;
  --red:#dc2626;
  --amber:#d97706;
}}

html, body, [class*="css"] {{
  font-family: Inter, sans-serif !important;
  color: var(--txt) !important;
  font-size:{font}!important;
}}

.stApp {{
  background:
    radial-gradient(circle at top left, rgba(224,242,254,.68), transparent 30%),
    radial-gradient(circle at top right, rgba(219,234,254,.55), transparent 34%),
    radial-gradient(circle at bottom right, rgba(240,249,255,.85), transparent 38%),
    linear-gradient(135deg,#f8fbff 0%,#eef8ff 45%,#f8fafc 100%) !important;
  background-attachment: fixed;
}}

.main .block-container {{
  max-width:{maxw}!important;
  width:100%!important;
  padding:{pad}!important;
  margin-left:auto!important;
  margin-right:auto!important;
}}

section[data-testid="stSidebar"] {{
  background: rgba(248,252,255,.82)!important;
  backdrop-filter: blur(26px) saturate(170%)!important;
  border-right:1px solid rgba(14,116,144,.14)!important;
}}

section[data-testid="stSidebar"] * {{
  font-size:{font}!important;
}}

h1 {{
  font-size:{h1}!important;
  line-height:1.18!important;
  margin-top:.20rem!important;
  margin-bottom:.35rem!important;
}}

h2 {{
  font-size:{h2}!important;
  line-height:1.18!important;
  margin-top:.20rem!important;
  margin-bottom:.30rem!important;
}}

h3 {{
  font-size:{h3}!important;
  line-height:1.18!important;
  margin-top:.18rem!important;
  margin-bottom:.25rem!important;
}}

p, li, label, span, div, small {{
  font-size:{font}!important;
}}

.stMarkdown, .stMarkdown * {{
  font-size:{font}!important;
  line-height:1.35!important;
}}

.glass-card,
.metric-glass,
.inner-glass,
.telegram-card,
.ocean-card,
.card,
.profile-glass,
.alert-card,
.status-card,
.regime-card {{
  background: linear-gradient(135deg, rgba(255,255,255,.82), rgba(240,249,255,.68))!important;
  border:1px solid rgba(14,116,144,.14)!important;
  border-radius:{radius}!important;
  padding:{card_pad}!important;
  backdrop-filter: blur(18px) saturate(175%)!important;
  box-shadow:0 6px 18px rgba(2,132,199,.07), inset 0 1px 0 rgba(255,255,255,.72)!important;
  animation: fadeUp .25s ease both;
  overflow-wrap:anywhere!important;
}}

.alert-card {{
  border-left:4px solid var(--amber)!important;
}}

.status-card {{
  border-left:4px solid var(--blue)!important;
}}

.regime-card {{
  border-left:4px solid var(--green)!important;
}}

.badge-buy,
.badge-sell,
.badge-neutral,
.badge-wait,
.badge-danger,
.badge-warning,
.badge-info {{
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  border-radius:999px!important;
  padding:4px 8px!important;
  font-weight:900!important;
  font-size:{font}!important;
  border:1px solid rgba(15,23,42,.08)!important;
}}

.badge-buy {{
  background:rgba(220,252,231,.90)!important;
  color:#166534!important;
}}

.badge-sell {{
  background:rgba(254,226,226,.90)!important;
  color:#991b1b!important;
}}

.badge-neutral,
.badge-wait {{
  background:rgba(241,245,249,.90)!important;
  color:#334155!important;
}}

.badge-danger {{
  background:rgba(254,226,226,.92)!important;
  color:#b91c1c!important;
}}

.badge-warning {{
  background:rgba(254,243,199,.92)!important;
  color:#92400e!important;
}}

.badge-info {{
  background:rgba(224,242,254,.92)!important;
  color:#075985!important;
}}

.stButton>button {{
  width:100%;
  min-height:{btn_h}!important;
  border-radius:{radius}!important;
  border:1px solid rgba(14,116,144,.15)!important;
  background: linear-gradient(135deg, rgba(255,255,255,.84), rgba(224,242,254,.62))!important;
  color:#0f172a!important;
  font-weight:800!important;
  font-size:{font}!important;
  padding:5px 8px!important;
  backdrop-filter: blur(16px)!important;
  box-shadow:0 4px 12px rgba(2,132,199,.07)!important;
  transition:.16s ease!important;
}}

.stButton>button:hover {{
  background:rgba(224,242,254,.78)!important;
  transform: translateY(-1px);
}}

.stButton>button:active {{
  transform: scale(.985);
}}

div[data-testid="metric-container"] {{
  background: rgba(255,255,255,.80)!important;
  border:1px solid rgba(14,116,144,.13)!important;
  border-radius:{radius}!important;
  padding:{card_pad}!important;
  backdrop-filter: blur(16px)!important;
  box-shadow:0 4px 12px rgba(2,132,199,.06)!important;
}}

div[data-testid="metric-container"] label {{
  color:#075985!important;
  font-size:{font}!important;
  font-weight:800!important;
}}

div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
  color:#0f172a!important;
  font-size:{metric_v}!important;
  font-weight:900!important;
}}

.stTabs [data-baseweb="tab-list"] {{
  gap:4px!important;
  flex-wrap:wrap!important;
  background:rgba(255,255,255,.50)!important;
  border-radius:{radius}!important;
  padding:4px!important;
}}

.stTabs [data-baseweb="tab"] {{
  border-radius:{radius}!important;
  padding:5px 7px!important;
  background:rgba(255,255,255,.68)!important;
  color:#0f172a!important;
  font-size:{tab_font}!important;
  min-height:28px!important;
  font-weight:800!important;
}}

.stTabs [aria-selected="true"] {{
  background:rgba(186,230,253,.80)!important;
  color:#075985!important;
}}

input, textarea, select,
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea {{
  background:rgba(255,255,255,.86)!important;
  color:#0f172a!important;
  border-radius:{radius}!important;
  font-size:{font}!important;
  border:1px solid rgba(14,116,144,.16)!important;
}}

[data-testid="stDataFrame"] {{
  border-radius:{radius}!important;
  overflow:hidden!important;
  border:1px solid rgba(14,116,144,.12)!important;
}}

[data-testid="stDataFrame"],
[data-testid="stDataFrame"] * {{
  font-size:{font}!important;
}}
/* Keep wide tables usable on phones instead of forcing the whole page too narrow. */
.element-container:has([data-testid="stDataFrame"]) {{
  overflow-x:auto!important;
}}


div[data-testid="column"] {{
  padding-left:0.16rem!important;
  padding-right:0.16rem!important;
}}

.stProgress > div > div > div > div {{
  background:linear-gradient(90deg,#38bdf8,#22c55e)!important;
}}

.engine-timer-box,
.engine-warning,
.stat-box {{
  border-radius:{radius}!important;
  padding:{card_pad}!important;
  font-size:{font}!important;
}}

.engine-timer-title,
.stat-title {{
  font-size:{font}!important;
}}

.engine-timer-value,
.stat-value {{
  font-size:{metric_v}!important;
}}

hr {{
  margin:.65rem 0!important;
  border-color:rgba(14,116,144,.13)!important;
}}

::-webkit-scrollbar {{
  width:6px;
  height:6px;
}}

::-webkit-scrollbar-thumb {{
  background:rgba(14,116,144,.25);
  border-radius:999px;
}}

::-webkit-scrollbar-track {{
  background:rgba(255,255,255,.35);
}}


/* Compact connector/sidebar helpers */
.compact-hero {{
  padding:7px!important;
  margin-bottom:6px!important;
}}
section[data-testid="stSidebar"] .stExpander {{
  border-radius:14px!important;
  border:1px solid rgba(14,116,144,.12)!important;
  background:rgba(255,255,255,.55)!important;
}}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{
  gap:.35rem!important;
}}
section[data-testid="stSidebar"] hr {{
  margin:.45rem 0!important;
}}


.ws-live-card {{
  background: linear-gradient(135deg, rgba(236,253,245,.88), rgba(224,242,254,.72))!important;
  border:1px solid rgba(16,185,129,.22)!important;
  border-radius:{radius}!important;
  padding:{card_pad}!important;
  box-shadow:0 7px 18px rgba(16,185,129,.08)!important;
}}
.ws-dot-live, .ws-dot-off {{
  display:inline-block!important;
  width:8px!important;
  height:8px!important;
  border-radius:999px!important;
  margin-right:6px!important;
}}
.ws-dot-live {{ background:#16a34a!important; box-shadow:0 0 0 5px rgba(22,163,74,.12)!important; }}
.ws-dot-off {{ background:#dc2626!important; box-shadow:0 0 0 5px rgba(220,38,38,.10)!important; }}

/* New calm/compact layout helpers */
.clean-section {{
  background:linear-gradient(135deg, rgba(255,255,255,.86), rgba(239,248,255,.68))!important;
  border:1px solid rgba(14,116,144,.14)!important;
  border-radius:{radius}!important;
  padding:{card_pad}!important;
  margin:.45rem 0!important;
  box-shadow:0 6px 18px rgba(2,132,199,.06)!important;
}}

div[data-testid="stExpander"] {{
  border:1px solid rgba(14,116,144,.14)!important;
  border-radius:{radius}!important;
  background:rgba(255,255,255,.58)!important;
  box-shadow:0 4px 14px rgba(2,132,199,.045)!important;
  overflow:hidden!important;
}}

div[data-testid="stExpander"] summary {{
  font-weight:900!important;
  color:#075985!important;
}}

.sidebar-timer-card {{
  border:1px solid rgba(14,116,144,.14)!important;
  border-radius:16px!important;
  padding:9px!important;
  margin:.35rem 0 .55rem 0!important;
  background:linear-gradient(135deg, rgba(255,255,255,.88), rgba(224,242,254,.72))!important;
  box-shadow:0 5px 14px rgba(2,132,199,.055)!important;
}}
.sidebar-timer-big {{
  font-weight:950!important;
  font-size:1.10rem!important;
  letter-spacing:.04em!important;
  color:#0f172a!important;
}}

@keyframes fadeUp {{
  from {{ opacity:0; transform:translateY(5px); }}
  to {{ opacity:1; transform:translateY(0); }}
}}

/* 2026-06-01 restored compact animated glass open/close fields */
div[data-testid="stExpander"] {{
  border:1px solid rgba(56,189,248,.16)!important;
  border-radius:14px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.38), rgba(224,242,254,.22))!important;
  backdrop-filter: blur(22px) saturate(180%)!important;
  -webkit-backdrop-filter: blur(22px) saturate(180%)!important;
  box-shadow:0 8px 24px rgba(2,132,199,.055), inset 0 1px 0 rgba(255,255,255,.55)!important;
  overflow:hidden!important;
  margin:.28rem 0!important;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease!important;
  animation: glassPop .22s ease both;
}}
div[data-testid="stExpander"]:hover {{
  transform: translateY(-1px);
  border-color:rgba(14,165,233,.26)!important;
  box-shadow:0 12px 26px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.68)!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:27px!important;
  padding:5px 8px!important;
  font-size:10.5px!important;
  font-weight:850!important;
  color:#075985!important;
  background:rgba(255,255,255,.18)!important;
}}
div[data-testid="stExpander"] details[open] summary {{
  border-bottom:1px solid rgba(56,189,248,.10)!important;
}}
div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] {{
  gap:.28rem!important;
}}
.stButton>button, div[data-testid="metric-container"], .glass-card, .metric-glass, .clean-section {{
  background:linear-gradient(135deg, rgba(255,255,255,.46), rgba(224,242,254,.25))!important;
  backdrop-filter: blur(20px) saturate(175%)!important;
  -webkit-backdrop-filter: blur(20px) saturate(175%)!important;
  border-color:rgba(56,189,248,.16)!important;
  box-shadow:0 7px 18px rgba(2,132,199,.045), inset 0 1px 0 rgba(255,255,255,.55)!important;
}}
.stButton>button {{
  min-height:32px!important;
  padding:4px 7px!important;
}}
div[data-testid="metric-container"] {{
  padding:7px!important;
}}
@keyframes glassPop {{
  from {{ opacity:0; transform:translateY(6px) scale(.992); filter:blur(1px); }}
  to {{ opacity:1; transform:translateY(0) scale(1); filter:blur(0); }}
}}

@media(max-width:430px) {{
  .main .block-container {{
    max-width:100vw!important;
    width:100vw!important;
    min-width:0!important;
    padding:0.28rem!important;
    margin-left:0!important;
    margin-right:0!important;
  }}

  html, body, [class*="css"],
  p, li, label, span, div, small,
  .stMarkdown, .stMarkdown * {{
    font-size:10.8px!important;
    line-height:1.24!important;
  }}

  /* Phone fix: Streamlit normally stacks every st.columns() item into one long vertical list.
     Keep metric/button rows as a compact grid so phone mode still feels like laptop mode. */
  div[data-testid="stHorizontalBlock"] {{
    display:grid!important;
    grid-template-columns:repeat(auto-fit, minmax(104px, 1fr))!important;
    gap:.28rem!important;
    align-items:stretch!important;
    width:100%!important;
  }}

  div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
    width:100%!important;
    min-width:0!important;
    flex:unset!important;
    padding-left:0!important;
    padding-right:0!important;
  }}

  div[data-testid="metric-container"] {{
    min-height:72px!important;
    overflow:hidden!important;
  }}

  div[data-testid="metric-container"] [data-testid="stMetricLabel"] {{
    white-space:normal!important;
    overflow-wrap:anywhere!important;
  }}

  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    white-space:normal!important;
    overflow-wrap:anywhere!important;
    line-height:1.05!important;
  }}

  h1 {{
    font-size:1rem!important;
    line-height:1.12!important;
  }}

  h2 {{
    font-size:.88rem!important;
    line-height:1.12!important;
  }}

  h3 {{
    font-size:.80rem!important;
    line-height:1.12!important;
  }}

  .stButton>button {{
    min-height:33px!important;
    font-size:9.8px!important;
    padding:4px 6px!important;
    border-radius:12px!important;
  }}

  div[data-testid="metric-container"] {{
    padding:7px!important;
    border-radius:12px!important;
  }}

  div[data-testid="metric-container"] label {{
    font-size:9.3px!important;
  }}

  div[data-testid="metric-container"] [data-testid="stMetricValue"] {{
    font-size:16px!important;
  }}

  .stTabs [data-baseweb="tab"] {{
    font-size:8.8px!important;
    padding:4px 5px!important;
    min-height:26px!important;
  }}

  .ocean-card,
  .glass-card,
  .inner-glass,
  .card,
  .profile-glass,
  .alert-card,
  .status-card,
  .regime-card {{
    padding:7px!important;
    border-radius:12px!important;
  }}

  section[data-testid="stSidebar"] {{
    width:230px!important;
    min-width:230px!important;
  }}

  div[data-testid="column"] {{
    padding-left:0.10rem!important;
    padding-right:0.10rem!important;
  }}

  .block-container > div {{
    max-width:100%!important;
  }}
}}

@media(max-width:380px) {{
  .main .block-container {{
    max-width:360px!important;
    width:100%!important;
    min-width:0!important;
    padding:0.34rem!important;
  }}

  html, body, [class*="css"],
  p, li, label, span, div, small,
  .stMarkdown, .stMarkdown * {{
    font-size:9.4px!important;
  }}

  .stButton>button {{
    min-height:31px!important;
    font-size:9.3px!important;
  }}
}}


/* === 2026 UI/UX full upgrade: universal page shell, stronger mobile grid, safer readability === */
.qx-page-head {{
  display:flex!important;
  align-items:stretch!important;
  justify-content:space-between!important;
  gap:.65rem!important;
  margin:.35rem 0 .45rem 0!important;
  padding:12px 13px!important;
  border-radius:22px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.90), rgba(224,242,254,.72))!important;
  border:1px solid rgba(14,116,144,.16)!important;
  box-shadow:0 12px 32px rgba(2,132,199,.09), inset 0 1px 0 rgba(255,255,255,.86)!important;
  backdrop-filter:blur(22px) saturate(180%)!important;
}}
.qx-title-wrap {{ min-width:0!important; }}
.qx-kicker {{
  color:#075985!important;
  font-weight:900!important;
  letter-spacing:.08em!important;
  text-transform:uppercase!important;
  font-size:10px!important;
  margin-bottom:2px!important;
}}
.qx-title {{
  color:#0f172a!important;
  font-weight:950!important;
  font-size:1.38rem!important;
  line-height:1.05!important;
  letter-spacing:-.03em!important;
}}
.qx-subtitle {{
  color:#475569!important;
  font-size:11px!important;
  font-weight:750!important;
  margin-top:4px!important;
  overflow-wrap:anywhere!important;
}}
.qx-status {{
  display:flex!important;
  align-items:center!important;
  justify-content:center!important;
  min-width:118px!important;
  border-radius:18px!important;
  padding:9px 12px!important;
  font-size:10px!important;
  font-weight:950!important;
  letter-spacing:.04em!important;
  text-align:center!important;
  border:1px solid rgba(15,23,42,.08)!important;
}}
.qx-ok {{ background:rgba(220,252,231,.86)!important; color:#166534!important; box-shadow:0 0 0 5px rgba(22,163,74,.08)!important; }}
.qx-off {{ background:rgba(254,226,226,.86)!important; color:#991b1b!important; box-shadow:0 0 0 5px rgba(220,38,38,.06)!important; }}
.qx-strip {{
  display:grid!important;
  grid-template-columns:repeat(4, minmax(0, 1fr))!important;
  gap:.42rem!important;
  margin:.25rem 0 .65rem 0!important;
}}
.qx-strip > div {{
  min-width:0!important;
  border-radius:17px!important;
  padding:9px 10px!important;
  background:rgba(255,255,255,.76)!important;
  border:1px solid rgba(14,116,144,.12)!important;
  box-shadow:0 5px 16px rgba(2,132,199,.055)!important;
}}
.qx-strip b {{
  display:block!important;
  color:#075985!important;
  font-size:9.6px!important;
  font-weight:950!important;
  margin-bottom:2px!important;
}}
.qx-strip span {{
  display:block!important;
  color:#0f172a!important;
  font-size:11px!important;
  font-weight:850!important;
  white-space:nowrap!important;
  overflow:hidden!important;
  text-overflow:ellipsis!important;
}}
.qx-empty {{
  border-radius:18px!important;
  padding:10px 12px!important;
  margin:.25rem 0 .65rem 0!important;
  background:linear-gradient(135deg, rgba(255,255,255,.88), rgba(254,243,199,.62))!important;
  border:1px solid rgba(217,119,6,.20)!important;
  color:#78350f!important;
  box-shadow:0 6px 18px rgba(217,119,6,.06)!important;
}}
.qx-empty b {{ font-weight:950!important; }}
.qx-empty span {{ font-weight:700!important; }}

/* Better visual hierarchy for native Streamlit alerts */
div[data-testid="stAlert"] {{
  border-radius:18px!important;
  border:1px solid rgba(14,116,144,.14)!important;
  box-shadow:0 5px 16px rgba(2,132,199,.055)!important;
}}

/* Form widgets: easier tap targets without giant vertical whitespace */
div[data-baseweb="select"] > div,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea {{
  min-height:36px!important;
}}

/* Tables: compact but readable */
[data-testid="stDataFrame"] {{ box-shadow:0 6px 18px rgba(2,132,199,.055)!important; }}

@media(max-width:760px) {{
  .qx-page-head {{
    display:grid!important;
    grid-template-columns:1fr!important;
    padding:10px!important;
    border-radius:18px!important;
    gap:.45rem!important;
  }}
  .qx-title {{ font-size:1.12rem!important; }}
  .qx-status {{ min-width:0!important; min-height:34px!important; }}
  .qx-strip {{ grid-template-columns:repeat(2, minmax(0, 1fr))!important; gap:.34rem!important; }}
  .qx-strip > div {{ padding:8px!important; border-radius:14px!important; }}
}}

/* 2026-06-01 restored compact animated glass open/close fields */
div[data-testid="stExpander"] {{
  border:1px solid rgba(56,189,248,.16)!important;
  border-radius:14px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.38), rgba(224,242,254,.22))!important;
  backdrop-filter: blur(22px) saturate(180%)!important;
  -webkit-backdrop-filter: blur(22px) saturate(180%)!important;
  box-shadow:0 8px 24px rgba(2,132,199,.055), inset 0 1px 0 rgba(255,255,255,.55)!important;
  overflow:hidden!important;
  margin:.28rem 0!important;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease!important;
  animation: glassPop .22s ease both;
}}
div[data-testid="stExpander"]:hover {{
  transform: translateY(-1px);
  border-color:rgba(14,165,233,.26)!important;
  box-shadow:0 12px 26px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.68)!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:27px!important;
  padding:5px 8px!important;
  font-size:10.5px!important;
  font-weight:850!important;
  color:#075985!important;
  background:rgba(255,255,255,.18)!important;
}}
div[data-testid="stExpander"] details[open] summary {{
  border-bottom:1px solid rgba(56,189,248,.10)!important;
}}
div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] {{
  gap:.28rem!important;
}}
.stButton>button, div[data-testid="metric-container"], .glass-card, .metric-glass, .clean-section {{
  background:linear-gradient(135deg, rgba(255,255,255,.46), rgba(224,242,254,.25))!important;
  backdrop-filter: blur(20px) saturate(175%)!important;
  -webkit-backdrop-filter: blur(20px) saturate(175%)!important;
  border-color:rgba(56,189,248,.16)!important;
  box-shadow:0 7px 18px rgba(2,132,199,.045), inset 0 1px 0 rgba(255,255,255,.55)!important;
}}
.stButton>button {{
  min-height:32px!important;
  padding:4px 7px!important;
}}
div[data-testid="metric-container"] {{
  padding:7px!important;
}}
@keyframes glassPop {{
  from {{ opacity:0; transform:translateY(6px) scale(.992); filter:blur(1px); }}
  to {{ opacity:1; transform:translateY(0) scale(1); filter:blur(0); }}
}}

@media(max-width:430px) {{
  .qx-page-head {{ margin:.18rem 0 .32rem 0!important; padding:8px!important; border-radius:15px!important; }}
  .qx-kicker {{ font-size:8.8px!important; }}
  .qx-title {{ font-size:1.0rem!important; }}
  .qx-subtitle {{ font-size:9.5px!important; }}
  .qx-status {{ font-size:8.8px!important; border-radius:12px!important; min-height:30px!important; padding:6px!important; }}
  .qx-strip {{ grid-template-columns:repeat(2, minmax(0, 1fr))!important; margin:.18rem 0 .44rem 0!important; }}
  .qx-strip b {{ font-size:8.7px!important; }}
  .qx-strip span {{ font-size:9.5px!important; }}
  .qx-empty {{ padding:8px!important; border-radius:14px!important; }}

  /* Force metric cards close to square on phone; avoids long vertical one-by-one feel. */
  div[data-testid="metric-container"] {{
    min-height:78px!important;
    display:flex!important;
    flex-direction:column!important;
    justify-content:space-between!important;
  }}

  /* Streamlit columns in nested panels should still be a grid, but never overflow sideways. */
  div[data-testid="stHorizontalBlock"] {{
    grid-template-columns:repeat(auto-fit, minmax(96px, 1fr))!important;
    gap:.24rem!important;
  }}
}}


/* === 2026 System Relationship + Timing layer === */
.rel-card {{
  background:linear-gradient(135deg, rgba(255,255,255,.90), rgba(224,242,254,.72))!important;
  border:1px solid rgba(14,116,144,.16)!important;
  border-radius:22px!important;
  padding:11px 12px!important;
  margin:.30rem 0 .60rem 0!important;
  box-shadow:0 10px 28px rgba(2,132,199,.08)!important;
  backdrop-filter:blur(20px) saturate(170%)!important;
}}
.rel-title {{
  font-weight:950!important;
  color:#075985!important;
  margin-bottom:8px!important;
}}
.rel-grid {{
  display:grid!important;
  grid-template-columns:repeat(4, minmax(0, 1fr))!important;
  gap:.42rem!important;
}}
.rel-grid > div {{
  min-width:0!important;
  background:rgba(255,255,255,.74)!important;
  border:1px solid rgba(14,116,144,.12)!important;
  border-radius:16px!important;
  padding:8px!important;
  box-shadow:0 5px 14px rgba(2,132,199,.045)!important;
}}
.rel-grid b {{
  display:block!important;
  color:#075985!important;
  font-size:9.5px!important;
  font-weight:950!important;
}}
.rel-grid span {{
  display:block!important;
  color:#334155!important;
  font-size:9.5px!important;
  font-weight:750!important;
  white-space:nowrap!important;
  overflow:hidden!important;
  text-overflow:ellipsis!important;
}}
.rel-badge {{
  display:inline-flex!important;
  align-items:center!important;
  justify-content:center!important;
  margin-top:5px!important;
  padding:3px 7px!important;
  border-radius:999px!important;
  font-size:8.4px!important;
  font-weight:950!important;
  letter-spacing:.03em!important;
}}
.rel-ok {{ background:rgba(220,252,231,.92)!important; color:#166534!important; }}
.rel-warn {{ background:rgba(254,243,199,.92)!important; color:#92400e!important; }}
.rel-bad {{ background:rgba(254,226,226,.92)!important; color:#991b1b!important; }}
.rel-info {{ background:rgba(224,242,254,.92)!important; color:#075985!important; }}
.rel-mini {{
  border-radius:15px!important;
  padding:8px!important;
  margin:.28rem 0!important;
  background:linear-gradient(135deg, rgba(255,255,255,.86), rgba(224,242,254,.66))!important;
  border:1px solid rgba(14,116,144,.13)!important;
  box-shadow:0 5px 13px rgba(2,132,199,.05)!important;
}}
.rel-mini b {{ color:#075985!important; font-weight:950!important; }}
.rel-mini small {{ color:#334155!important; font-weight:750!important; }}
@media(max-width:760px) {{
  .rel-grid {{ grid-template-columns:repeat(2, minmax(0, 1fr))!important; }}
  .rel-card {{ border-radius:18px!important; padding:9px!important; }}
}}
/* 2026-06-01 restored compact animated glass open/close fields */
div[data-testid="stExpander"] {{
  border:1px solid rgba(56,189,248,.16)!important;
  border-radius:14px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.38), rgba(224,242,254,.22))!important;
  backdrop-filter: blur(22px) saturate(180%)!important;
  -webkit-backdrop-filter: blur(22px) saturate(180%)!important;
  box-shadow:0 8px 24px rgba(2,132,199,.055), inset 0 1px 0 rgba(255,255,255,.55)!important;
  overflow:hidden!important;
  margin:.28rem 0!important;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease!important;
  animation: glassPop .22s ease both;
}}
div[data-testid="stExpander"]:hover {{
  transform: translateY(-1px);
  border-color:rgba(14,165,233,.26)!important;
  box-shadow:0 12px 26px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.68)!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:27px!important;
  padding:5px 8px!important;
  font-size:10.5px!important;
  font-weight:850!important;
  color:#075985!important;
  background:rgba(255,255,255,.18)!important;
}}
div[data-testid="stExpander"] details[open] summary {{
  border-bottom:1px solid rgba(56,189,248,.10)!important;
}}
div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] {{
  gap:.28rem!important;
}}
.stButton>button, div[data-testid="metric-container"], .glass-card, .metric-glass, .clean-section {{
  background:linear-gradient(135deg, rgba(255,255,255,.46), rgba(224,242,254,.25))!important;
  backdrop-filter: blur(20px) saturate(175%)!important;
  -webkit-backdrop-filter: blur(20px) saturate(175%)!important;
  border-color:rgba(56,189,248,.16)!important;
  box-shadow:0 7px 18px rgba(2,132,199,.045), inset 0 1px 0 rgba(255,255,255,.55)!important;
}}
.stButton>button {{
  min-height:32px!important;
  padding:4px 7px!important;
}}
div[data-testid="metric-container"] {{
  padding:7px!important;
}}
@keyframes glassPop {{
  from {{ opacity:0; transform:translateY(6px) scale(.992); filter:blur(1px); }}
  to {{ opacity:1; transform:translateY(0) scale(1); filter:blur(0); }}
}}

@media(max-width:430px) {{
  .rel-grid {{ grid-template-columns:repeat(2, minmax(0, 1fr))!important; gap:.28rem!important; }}
  .rel-grid > div {{ min-height:78px!important; border-radius:13px!important; padding:7px!important; }}
  .rel-grid b, .rel-grid span {{ font-size:8.7px!important; }}
  .rel-badge {{ font-size:7.8px!important; padding:3px 6px!important; }}
}}



/* === 2026-06 Telegram glass open/close + popup alert upgrade === */
.qx-choice-label {{
  font-weight:950!important;
  color:#075985!important;
  margin:.35rem 0 .28rem 0!important;
  letter-spacing:.02em!important;
}}
.tg-alert {{
  margin:.45rem 0!important;
  padding:12px 14px!important;
  border-radius:22px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.92), rgba(224,242,254,.76))!important;
  border:1px solid rgba(56,189,248,.28)!important;
  box-shadow:0 16px 38px rgba(2,132,199,.12), inset 0 1px 0 rgba(255,255,255,.82)!important;
  backdrop-filter:blur(24px) saturate(185%)!important;
  animation:tgPop .32s cubic-bezier(.2,1.35,.35,1) both!important;
}}
.tg-alert-title {{ font-weight:950!important; color:#0f172a!important; font-size:1.02rem!important; }}
.tg-alert-msg {{ margin-top:4px!important; color:#334155!important; font-weight:760!important; line-height:1.35!important; }}
.tg-danger {{ border-left:5px solid #dc2626!important; background:linear-gradient(135deg, rgba(255,255,255,.94), rgba(254,226,226,.72))!important; }}
.tg-warning {{ border-left:5px solid #d97706!important; background:linear-gradient(135deg, rgba(255,255,255,.94), rgba(254,243,199,.72))!important; }}
.tg-success {{ border-left:5px solid #16a34a!important; background:linear-gradient(135deg, rgba(255,255,255,.94), rgba(220,252,231,.72))!important; }}
.tg-info {{ border-left:5px solid #0284c7!important; }}
@keyframes tgPop {{
  from {{ opacity:0; transform:translateY(10px) scale(.965); filter:blur(3px); }}
  to {{ opacity:1; transform:translateY(0) scale(1); filter:blur(0); }}
}}

/* Make all native open/close fields feel like Telegram glass cards. */
div[data-testid="stExpander"] {{
  background:linear-gradient(135deg, rgba(255,255,255,.72), rgba(224,242,254,.52))!important;
  border:1px solid rgba(56,189,248,.22)!important;
  border-radius:22px!important;
  box-shadow:0 10px 28px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.72)!important;
  backdrop-filter:blur(22px) saturate(180%)!important;
  animation:fadeUp .24s ease both!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:38px!important;
  padding:8px 10px!important;
  border-radius:18px!important;
  transition:.16s ease!important;
}}
div[data-testid="stExpander"] summary:hover {{
  background:rgba(224,242,254,.50)!important;
  transform:translateY(-1px)!important;
}}

/* Button choices should look like selectable tab chips. */
.stButton>button:has(span) {{
  position:relative!important;
  overflow:hidden!important;
}}
.stButton>button:before {{
  content:"";
  position:absolute;
  inset:0;
  background:linear-gradient(120deg, transparent, rgba(255,255,255,.48), transparent);
  transform:translateX(-120%);
  transition:.45s ease;
}}
.stButton>button:hover:before {{ transform:translateX(120%); }}

/* 2026-06-01 restored compact animated glass open/close fields */
div[data-testid="stExpander"] {{
  border:1px solid rgba(56,189,248,.16)!important;
  border-radius:14px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.38), rgba(224,242,254,.22))!important;
  backdrop-filter: blur(22px) saturate(180%)!important;
  -webkit-backdrop-filter: blur(22px) saturate(180%)!important;
  box-shadow:0 8px 24px rgba(2,132,199,.055), inset 0 1px 0 rgba(255,255,255,.55)!important;
  overflow:hidden!important;
  margin:.28rem 0!important;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease!important;
  animation: glassPop .22s ease both;
}}
div[data-testid="stExpander"]:hover {{
  transform: translateY(-1px);
  border-color:rgba(14,165,233,.26)!important;
  box-shadow:0 12px 26px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.68)!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:27px!important;
  padding:5px 8px!important;
  font-size:10.5px!important;
  font-weight:850!important;
  color:#075985!important;
  background:rgba(255,255,255,.18)!important;
}}
div[data-testid="stExpander"] details[open] summary {{
  border-bottom:1px solid rgba(56,189,248,.10)!important;
}}
div[data-testid="stExpander"] div[data-testid="stVerticalBlock"] {{
  gap:.28rem!important;
}}
.stButton>button, div[data-testid="metric-container"], .glass-card, .metric-glass, .clean-section {{
  background:linear-gradient(135deg, rgba(255,255,255,.46), rgba(224,242,254,.25))!important;
  backdrop-filter: blur(20px) saturate(175%)!important;
  -webkit-backdrop-filter: blur(20px) saturate(175%)!important;
  border-color:rgba(56,189,248,.16)!important;
  box-shadow:0 7px 18px rgba(2,132,199,.045), inset 0 1px 0 rgba(255,255,255,.55)!important;
}}
.stButton>button {{
  min-height:32px!important;
  padding:4px 7px!important;
}}
div[data-testid="metric-container"] {{
  padding:7px!important;
}}
@keyframes glassPop {{
  from {{ opacity:0; transform:translateY(6px) scale(.992); filter:blur(1px); }}
  to {{ opacity:1; transform:translateY(0) scale(1); filter:blur(0); }}
}}

@media(max-width:430px) {{
  .tg-alert {{ border-radius:15px!important; padding:9px!important; }}
  .tg-alert-title {{ font-size:.92rem!important; }}
  div[data-testid="stExpander"] {{ border-radius:15px!important; }}
}}


/* === 2026-06 ultra-compact transparent open/close fields === */
div[data-testid="stExpander"] {{
  background:linear-gradient(135deg, rgba(255,255,255,.34), rgba(224,242,254,.22))!important;
  border:1px solid rgba(56,189,248,.13)!important;
  border-radius:14px!important;
  box-shadow:0 3px 10px rgba(2,132,199,.035), inset 0 1px 0 rgba(255,255,255,.35)!important;
  backdrop-filter:blur(16px) saturate(150%)!important;
  margin:.22rem 0!important;
}}
div[data-testid="stExpander"] summary {{
  min-height:28px!important;
  padding:3px 7px!important;
  border-radius:12px!important;
  color:#075985!important;
  font-weight:800!important;
}}
div[data-testid="stExpander"] details[open] summary,
div[data-testid="stExpander"] summary:hover {{
  background:rgba(224,242,254,.26)!important;
  transform:none!important;
}}
div[data-testid="stExpander"] [data-testid="stExpanderDetails"] {{
  padding:5px 8px 8px 8px!important;
}}
.stCaptionContainer, .stCaptionContainer *,
div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li,
div[data-testid="stMarkdownContainer"] small {{
  font-size:10.2px!important;
  line-height:1.28!important;
}}
.qx-choice-label {{
  font-size:10.6px!important;
  margin:.20rem 0 .18rem 0!important;
}}
.qx-page-head, .qx-strip {{
  transform:scale(.985);
  transform-origin:left top;
}}

/* === 2026-06-01 FULL UI/UX + animation + relationship upgrade === */
.qx-command-bar{{
  position:sticky; top:.18rem; z-index:999;
  display:flex; align-items:center; justify-content:space-between; gap:.5rem; flex-wrap:wrap;
  padding:7px 9px; margin:.10rem 0 .45rem 0;
  border:1px solid rgba(14,116,144,.15); border-radius:18px;
  background:linear-gradient(135deg, rgba(255,255,255,.86), rgba(224,242,254,.72));
  backdrop-filter:blur(22px) saturate(170%);
  box-shadow:0 8px 24px rgba(2,132,199,.08), inset 0 1px 0 rgba(255,255,255,.78);
  animation: qxSlideDown .22s ease both;
}}
.qx-command-left,.qx-command-right{{display:flex; align-items:center; gap:6px; flex-wrap:wrap;}}
.qx-command-bar span{{font-size:10.6px!important; color:#075985; padding:3px 7px; border-radius:999px; background:rgba(255,255,255,.48); border:1px solid rgba(14,116,144,.08);}}
.qx-pill-blue{{background:linear-gradient(135deg,#e0f2fe,#dbeafe)!important; color:#075985!important; font-weight:900!important;}}
.qx-toast{{
  position:fixed; right:18px; top:72px; z-index:99999;
  display:flex; align-items:center; gap:9px; min-width:190px; max-width:310px;
  padding:10px 12px; border-radius:18px;
  background:linear-gradient(135deg, rgba(255,255,255,.96), rgba(224,242,254,.90));
  border:1px solid rgba(56,189,248,.26); box-shadow:0 18px 42px rgba(2,132,199,.18);
  backdrop-filter:blur(24px) saturate(180%); color:#0f172a;
  animation: qxToastPop 2.15s ease both;
}}
.qx-toast span{{color:#075985!important; font-size:10.4px!important;}}
.qx-toast-dot{{width:10px; height:10px; border-radius:999px; background:#38bdf8; box-shadow:0 0 0 6px rgba(56,189,248,.15); animation: qxPulse 1.1s infinite;}}
.qx-relation-footer{{margin:.7rem 0 .25rem; padding:8px 10px; border-radius:16px; background:rgba(255,255,255,.54); border:1px dashed rgba(14,116,144,.22); color:#075985;}}
.qx-relation-footer span{{font-weight:900; color:#166534;}}
.stButton>button{{transition:transform .12s ease, box-shadow .12s ease, border-color .12s ease, background .12s ease!important; position:relative; overflow:hidden;}}
.stButton>button:hover{{transform:translateY(-1px) scale(1.006)!important; box-shadow:0 8px 20px rgba(2,132,199,.13)!important; border-color:rgba(14,116,144,.30)!important;}}
.stButton>button:active{{transform:translateY(1px) scale(.992)!important;}}
.stButton>button:after{{content:""; position:absolute; inset:0; background:radial-gradient(circle, rgba(56,189,248,.23) 0%, transparent 55%); transform:scale(0); opacity:0; transition:transform .28s ease, opacity .28s ease;}}
.stButton>button:active:after{{transform:scale(2.1); opacity:1; transition:0s;}}
div[data-testid="stMetric"]{{border-radius:16px!important; background:linear-gradient(135deg, rgba(255,255,255,.70), rgba(240,249,255,.58))!important; border:1px solid rgba(14,116,144,.12)!important; padding:8px!important; box-shadow:0 5px 18px rgba(2,132,199,.055)!important; animation: qxFadeUp .20s ease both;}}
div[data-testid="stDataFrame"], div[data-testid="stTable"]{{border-radius:16px!important; overflow:hidden!important; border:1px solid rgba(14,116,144,.13)!important; box-shadow:0 6px 18px rgba(2,132,199,.055)!important;}}
@keyframes qxToastPop{{0%{{opacity:0; transform:translateY(-8px) scale(.96);}}12%{{opacity:1; transform:translateY(0) scale(1);}}82%{{opacity:1; transform:translateY(0) scale(1);}}100%{{opacity:0; transform:translateY(-8px) scale(.98); pointer-events:none;}}}}
@keyframes qxPulse{{0%,100%{{transform:scale(1); opacity:1;}}50%{{transform:scale(1.25); opacity:.65;}}}}
@keyframes qxSlideDown{{from{{opacity:0; transform:translateY(-6px);}}to{{opacity:1; transform:translateY(0);}}}}
@keyframes qxFadeUp{{from{{opacity:0; transform:translateY(4px);}}to{{opacity:1; transform:translateY(0);}}}}
@media (max-width: 760px){{
  .qx-command-bar{{position:relative; top:auto; padding:6px; border-radius:15px;}}
  .qx-command-left,.qx-command-right{{gap:4px;}}
  .qx-command-bar span{{font-size:9.6px!important; padding:2px 5px;}}
  .qx-toast{{left:10px; right:10px; top:60px; max-width:none;}}
}}


/* 2026-06-01 Compact transparent glass open/close UI + popup animation */
div[data-testid="stExpander"]{{
  border:1px solid rgba(14,116,144,.12)!important;
  border-radius:14px!important;
  background:rgba(255,255,255,.42)!important;
  backdrop-filter:blur(18px) saturate(165%)!important;
  box-shadow:0 5px 14px rgba(2,132,199,.055)!important;
  overflow:hidden!important;
  margin:.28rem 0!important;
  animation: qxPop .20s ease-out both;
}}
div[data-testid="stExpander"] details > summary{{
  min-height:28px!important;
  padding:4px 8px!important;
  background:linear-gradient(135deg,rgba(255,255,255,.36),rgba(224,242,254,.24))!important;
  border-radius:14px!important;
}}
div[data-testid="stExpander"] details > summary p,
div[data-testid="stExpander"] details > summary span{{
  font-size:10.5px!important;
  font-weight:850!important;
  letter-spacing:.01em!important;
}}
div[data-testid="stExpander"] div[data-testid="stExpanderDetails"]{{
  padding:6px 8px 8px!important;
  background:rgba(255,255,255,.26)!important;
  animation: qxDrop .18s ease-out both;
}}
section[data-testid="stSidebar"] div[data-testid="stExpander"]{{
  background:rgba(255,255,255,.34)!important;
  margin:.20rem 0!important;
}}
section[data-testid="stSidebar"] div[data-testid="stExpander"] details > summary{{
  min-height:25px!important;
  padding:3px 7px!important;
}}
.stTextInput input,.stNumberInput input,.stSelectbox div[data-baseweb="select"],.stTextArea textarea{{
  border-radius:12px!important;
  border:1px solid rgba(14,116,144,.14)!important;
  background:rgba(255,255,255,.46)!important;
  backdrop-filter:blur(14px)!important;
  min-height:30px!important;
  font-size:10.8px!important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.50)!important;
}}
.stButton>button{{
  position:relative!important;
  overflow:hidden!important;
}}
.stButton>button:after{{
  content:"";
  position:absolute;
  inset:0;
  transform:translateX(-120%);
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.70),transparent);
}}
.stButton>button:hover:after{{animation:qxShine .72s ease;}}
.qx-popup,.tg-alert{{
  animation: qxPop .22s cubic-bezier(.2,.9,.2,1) both, qxFloat 2.2s ease-in-out infinite alternate;
}}
@keyframes qxPop{{from{{opacity:0;transform:scale(.975) translateY(5px);}}to{{opacity:1;transform:scale(1) translateY(0);}}}}
@keyframes qxDrop{{from{{opacity:0;transform:translateY(-4px);}}to{{opacity:1;transform:translateY(0);}}}}
@keyframes qxShine{{to{{transform:translateX(120%);}}}}
@keyframes qxFloat{{from{{filter:drop-shadow(0 4px 12px rgba(2,132,199,.08));}}to{{filter:drop-shadow(0 7px 17px rgba(2,132,199,.13));}}}}



/* 2026-06-01 Pro Plus UIUX background + quality HUD */
.stApp::before{{
  content:"";
  position:fixed;
  inset:-18% -12%;
  z-index:-2;
  pointer-events:none;
  background:
    radial-gradient(circle at 15% 20%, rgba(56,189,248,.20), transparent 24%),
    radial-gradient(circle at 78% 12%, rgba(59,130,246,.16), transparent 28%),
    radial-gradient(circle at 55% 86%, rgba(34,197,94,.10), transparent 26%);
  filter:blur(16px);
  animation: oceanDrift 18s ease-in-out infinite alternate;
}}
.stApp::after{{
  content:"";
  position:fixed;
  inset:0;
  z-index:-1;
  pointer-events:none;
  background-image:linear-gradient(rgba(14,116,144,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(14,116,144,.035) 1px, transparent 1px);
  background-size:28px 28px;
  mask-image:linear-gradient(to bottom, rgba(0,0,0,.55), rgba(0,0,0,.08));
}}
.pro-quality-hud{{
  margin:.25rem 0 .55rem 0;
  padding:8px 10px;
  border-radius:16px;
  background:linear-gradient(135deg, rgba(255,255,255,.58), rgba(224,242,254,.30));
  border:1px solid rgba(14,165,233,.16);
  backdrop-filter:blur(22px) saturate(180%);
  -webkit-backdrop-filter:blur(22px) saturate(180%);
  box-shadow:0 8px 22px rgba(2,132,199,.055), inset 0 1px 0 rgba(255,255,255,.62);
  animation: glassPop .22s ease both;
}}
.pro-quality-hud b{{font-weight:950;color:#0f172a!important;}}
.pro-quality-hud span{{font-size:10.2px!important;color:#075985!important;}}
.pro-quality-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:5px;margin-top:5px;}}
.pro-quality-grid span{{padding:4px 7px;border-radius:999px;background:rgba(255,255,255,.48);border:1px solid rgba(14,116,144,.08);}}
@keyframes oceanDrift{{from{{transform:translate3d(-1.5%, -1%, 0) scale(1);}}to{{transform:translate3d(1.5%, 1%, 0) scale(1.035);}}}}
@media(max-width:430px){{.pro-quality-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}.pro-quality-hud{{padding:7px;border-radius:14px;}}.stApp::after{{background-size:20px 20px;}}}}


/* ==========================================================
   2026-06-01 HOME + GLOBAL UIUX PRO PLUS PATCH
   Additive only: animated ocean background, popup motion,
   smaller transparent cards, safer mobile wrapping.
   ========================================================== */
.stApp::before{{
  content:""; position:fixed; inset:-18%; pointer-events:none; z-index:-2;
  background:
    radial-gradient(circle at 12% 18%, rgba(56,189,248,.20), transparent 24%),
    radial-gradient(circle at 82% 14%, rgba(125,211,252,.22), transparent 26%),
    radial-gradient(circle at 70% 84%, rgba(186,230,253,.24), transparent 29%);
  filter: blur(2px); animation: qxOceanFloat 18s ease-in-out infinite alternate;
}}
.stApp::after{{
  content:""; position:fixed; inset:0; pointer-events:none; z-index:-1;
  background-image:
    linear-gradient(rgba(14,116,144,.045) 1px, transparent 1px),
    linear-gradient(90deg, rgba(14,116,144,.045) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: radial-gradient(circle at top, black, transparent 72%);
  animation: qxGridMove 26s linear infinite;
}}
.qx-home-hero{{
  position:relative; overflow:hidden; margin:.25rem 0 .65rem 0; padding:14px 16px;
  border-radius:22px; border:1px solid rgba(14,116,144,.16);
  background:linear-gradient(135deg, rgba(255,255,255,.78), rgba(224,242,254,.56));
  box-shadow:0 14px 34px rgba(2,132,199,.10), inset 0 1px 0 rgba(255,255,255,.82);
  backdrop-filter: blur(24px) saturate(180%); animation: qxHeroEnter .32s ease both;
}}
.qx-home-hero:before{{
  content:""; position:absolute; width:220px; height:220px; right:-70px; top:-110px;
  border-radius:999px; background:radial-gradient(circle, rgba(56,189,248,.24), transparent 68%);
  animation: qxGlowSpin 8s ease-in-out infinite alternate;
}}
.qx-home-hero h2{{margin:0!important; font-weight:950!important; letter-spacing:-.03em!important;}}
.qx-home-hero p{{margin:.25rem 0 0 0!important; color:#075985!important; font-weight:750!important;}}
.qx-launch-grid{{display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:7px; margin:.45rem 0 .55rem 0;}}
.qx-mini-pill{{display:inline-flex; align-items:center; justify-content:center; gap:5px; padding:5px 8px; border-radius:999px; background:rgba(255,255,255,.58); border:1px solid rgba(14,116,144,.12); color:#075985; font-weight:900; font-size:10.5px!important;}}
.qx-snapshot-strip{{display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; margin:.55rem 0;}}
.qx-snapshot-card{{padding:10px; border-radius:18px; background:linear-gradient(135deg,rgba(255,255,255,.78),rgba(240,249,255,.52)); border:1px solid rgba(14,116,144,.13); box-shadow:0 8px 20px rgba(2,132,199,.06); animation: qxCardPop .25s ease both;}}
.qx-snapshot-card b{{font-size:10.5px!important;color:#075985!important;display:block;}}
.qx-snapshot-card span{{font-size:16px!important;font-weight:950!important;color:#0f172a!important;}}
.qx-soft-popup-note{{margin:.35rem 0; padding:8px 10px; border-radius:16px; background:linear-gradient(135deg, rgba(224,242,254,.70), rgba(255,255,255,.55)); border:1px solid rgba(56,189,248,.18); animation: qxPopupIn .24s ease both;}}
.qx-soft-popup-note b{{font-weight:950;color:#0f172a}}.qx-soft-popup-note span{{color:#075985;font-weight:750}}
@keyframes qxOceanFloat{{from{{transform:translate3d(-1.8%,-1.2%,0) scale(1);}}to{{transform:translate3d(1.8%,1.2%,0) scale(1.04);}}}}
@keyframes qxGridMove{{from{{background-position:0 0,0 0;}}to{{background-position:34px 34px,34px 34px;}}}}
@keyframes qxHeroEnter{{from{{opacity:0;transform:translateY(8px) scale(.99);}}to{{opacity:1;transform:translateY(0) scale(1);}}}}
@keyframes qxCardPop{{from{{opacity:0;transform:translateY(6px) scale(.985);}}to{{opacity:1;transform:translateY(0) scale(1);}}}}
@keyframes qxGlowSpin{{from{{transform:rotate(0deg) scale(1);}}to{{transform:rotate(18deg) scale(1.08);}}}}
@media(max-width:760px){{.qx-launch-grid{{grid-template-columns:repeat(2,minmax(0,1fr));}}.qx-snapshot-strip{{grid-template-columns:repeat(2,minmax(0,1fr));}}.qx-home-hero{{padding:10px 11px;border-radius:18px;}}}}
@media(max-width:430px){{.qx-snapshot-card span{{font-size:14px!important}}.qx-mini-pill{{font-size:9.5px!important;padding:4px 6px}}.qx-home-hero p{{font-size:10px!important}}}}

</style>
""",
        unsafe_allow_html=True,
    )


def auto_close_sidebar_script():
    """Mobile-safe helper: force Streamlit sidebar fully closed after any UI click/rerun."""
    import streamlit as st
    st.markdown("""
    <style>
    @media (max-width: 768px){
      /* When Streamlit marks sidebar collapsed, remove the remaining phone sliver completely. */
      section[data-testid="stSidebar"][aria-expanded="false"],
      section[data-testid="stSidebar"][aria-expanded="false"] > div:first-child{
        transform: translateX(-120%) !important;
        visibility: hidden !important;
        pointer-events: none !important;
        min-width: 0 !important;
        width: 0 !important;
        max-width: 0 !important;
        flex-basis: 0 !important;
        opacity: 0 !important;
      }
      div[data-testid="stSidebarOverlay"],
      [data-testid="stSidebarOverlay"]{display:none!important; pointer-events:none!important; opacity:0!important;}
      .stApp{overflow-x:hidden!important;}
      body{overscroll-behavior-x:none!important;}
    }
    </style>
    <script>
    (function(){
      try{
        const doc = window.parent && window.parent.document ? window.parent.document : document;
        const win = window.parent || window;
        win.__qxForceCloseSidebar = function(){
          try{
            const d = win.document;
            const sidebar = d.querySelector('section[data-testid="stSidebar"]');
            const isPhone = win.innerWidth <= 768;
            if(!isPhone || !sidebar) return;
            const expanded = sidebar.getAttribute('aria-expanded') === 'true';
            const buttons = Array.from(d.querySelectorAll('button'));
            const closeBtn = buttons.find(b => {
              const txt = ((b.getAttribute('aria-label')||'') + ' ' + (b.getAttribute('title')||'')).toLowerCase();
              return txt.includes('close sidebar') || (txt.includes('sidebar') && expanded);
            });
            if(expanded && closeBtn){ closeBtn.click(); }
            setTimeout(function(){
              const sb = d.querySelector('section[data-testid="stSidebar"][aria-expanded="false"]');
              if(sb){
                sb.style.transform='translateX(-120%)';
                sb.style.visibility='hidden';
                sb.style.pointerEvents='none';
                sb.style.width='0px';
                sb.style.minWidth='0px';
                sb.style.maxWidth='0px';
                sb.style.opacity='0';
              }
              const ov = d.querySelector('[data-testid="stSidebarOverlay"]');
              if(ov){ ov.style.display='none'; ov.style.pointerEvents='none'; ov.style.opacity='0'; }
            }, 80);
          }catch(e){}
        };
        if(win.innerWidth <= 768){
          setTimeout(win.__qxForceCloseSidebar, 50);
          setTimeout(win.__qxForceCloseSidebar, 220);
          setTimeout(win.__qxForceCloseSidebar, 650);
        }
      }catch(e){}
    })();
    </script>
    """, unsafe_allow_html=True)


def request_close_sidebar():
    """Close sidebar on tab clicks, especially on mobile."""
    return auto_close_sidebar_script()


def status_badge(text, kind="info"):
    kind = str(kind or "info").lower()

    cls = {
        "buy": "badge-buy",
        "sell": "badge-sell",
        "wait": "badge-wait",
        "neutral": "badge-neutral",
        "danger": "badge-danger",
        "warning": "badge-warning",
        "info": "badge-info",
    }.get(kind, "badge-info")

    st.markdown(f'<span class="{cls}">{text}</span>', unsafe_allow_html=True)


def ocean_card(title="", body="", kind="status"):
    cls = {
        "alert": "alert-card",
        "regime": "regime-card",
        "status": "status-card",
    }.get(str(kind or "status").lower(), "status-card")

    st.markdown(
        f"""
        <div class="{cls}">
            <b>{title}</b><br>
            <span>{body}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def load_style(phone_mode: bool = False):
    apply_global_styles(phone_mode=phone_mode)


def apply_style(phone_mode: bool = False):
    apply_global_styles(phone_mode=phone_mode)



# 2026-06-03 V5 screenshot-matched ocean glass UI. Applied after the legacy CSS so it wins safely.
def _apply_v5_ocean_glass_styles():
    st.markdown(
        """
<style>
/* === 2026-06-03 V5 screenshot-matched ocean glass UI === */
.stApp:before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  z-index:-2;
  background:
    linear-gradient(145deg, rgba(255,255,255,.72) 0 16%, transparent 16% 100%),
    linear-gradient(325deg, rgba(255,255,255,.55) 0 22%, transparent 22% 100%),
    radial-gradient(circle at 28% 18%, rgba(125,211,252,.48), transparent 30%),
    radial-gradient(circle at 55% 30%, rgba(187,247,208,.42), transparent 28%),
    radial-gradient(circle at 80% 8%, rgba(240,249,255,.80), transparent 32%),
    linear-gradient(135deg,#eefcff 0%,#e0f7ff 38%,#e9fbff 68%,#f8fdff 100%);
  background-attachment:fixed;
  animation: qxOceanDrift 12s ease-in-out infinite alternate;
}
.stApp:after{
  content:"";
  position:fixed;
  inset:-20%;
  pointer-events:none;
  z-index:-1;
  opacity:.38;
  background:
    radial-gradient(circle at 15% 22%, rgba(255,255,255,.95) 0 1px, transparent 2px),
    radial-gradient(circle at 70% 40%, rgba(255,255,255,.90) 0 1px, transparent 2px),
    radial-gradient(circle at 45% 70%, rgba(14,165,233,.20) 0 1px, transparent 2px);
  background-size:140px 140px, 190px 190px, 230px 230px;
  animation: qxParticleFloat 22s linear infinite;
}
@keyframes qxOceanDrift{from{filter:hue-rotate(0deg) brightness(1)}to{filter:hue-rotate(8deg) brightness(1.035)}}
@keyframes qxParticleFloat{from{transform:translate3d(0,0,0)}to{transform:translate3d(80px,-60px,0)}}

.main .block-container{
  padding-top:.28rem!important;
}
section[data-testid="stSidebar"]{
  background:linear-gradient(145deg, rgba(255,255,255,.48), rgba(221,250,255,.38))!important;
  border-right:1px solid rgba(14,116,144,.13)!important;
  box-shadow:18px 0 45px rgba(2,132,199,.06)!important;
}
/* Hero/cards like uploaded picture */
.qx-command-center,.qx-terminal-hero,.qx-command-lite,.qx-page-head,.rel-card,
.glass-card,.metric-glass,.inner-glass,.ocean-card,.clean-section,.card,
div[data-testid="metric-container"],div[data-testid="stExpander"]{
  background:linear-gradient(135deg, rgba(255,255,255,.56), rgba(232,251,255,.36))!important;
  border:1px solid rgba(125,211,252,.25)!important;
  border-radius:24px!important;
  box-shadow:0 18px 48px rgba(2,132,199,.075), inset 0 1px 0 rgba(255,255,255,.72)!important;
  backdrop-filter:blur(28px) saturate(190%)!important;
  -webkit-backdrop-filter:blur(28px) saturate(190%)!important;
  animation: qxPopFloat .34s cubic-bezier(.2,1.25,.34,1) both!important;
}
@keyframes qxPopFloat{from{opacity:0;transform:translateY(10px) scale(.982);filter:blur(4px)}to{opacity:1;transform:translateY(0) scale(1);filter:blur(0)}}

/* Native metrics become compact rounded tiles */
div[data-testid="metric-container"]{
  min-height:86px!important;
  padding:13px 14px!important;
  display:flex!important;
  flex-direction:column!important;
  justify-content:center!important;
}
div[data-testid="metric-container"] label,
div[data-testid="metric-container"] [data-testid="stMetricLabel"]{
  color:#075985!important;
  font-weight:950!important;
  text-transform:uppercase!important;
  letter-spacing:.035em!important;
}
div[data-testid="metric-container"] [data-testid="stMetricValue"]{
  color:#0f172a!important;
  font-weight:950!important;
}
div[data-testid="metric-container"] [data-testid="stMetricDelta"]{
  border-radius:999px!important;
  padding:3px 8px!important;
  background:rgba(220,252,231,.75)!important;
}

/* Screenshot style status chips/buttons */
.stButton>button{
  border-radius:999px!important;
  min-height:34px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.70), rgba(224,242,254,.52))!important;
  color:#075985!important;
  border:1px solid rgba(14,116,144,.18)!important;
  box-shadow:0 10px 22px rgba(2,132,199,.06), inset 0 1px 0 rgba(255,255,255,.72)!important;
  font-weight:950!important;
}
.stButton>button:hover{
  transform:translateY(-2px) scale(1.01)!important;
  box-shadow:0 16px 32px rgba(2,132,199,.10), inset 0 1px 0 rgba(255,255,255,.82)!important;
}

/* Open/close field requested for metric sections */
div[data-testid="stExpander"]{
  margin:.42rem 0!important;
  overflow:hidden!important;
}
div[data-testid="stExpander"] summary{
  min-height:42px!important;
  padding:10px 13px!important;
  color:#075985!important;
  font-weight:950!important;
  letter-spacing:.02em!important;
  background:linear-gradient(135deg, rgba(255,255,255,.50), rgba(224,242,254,.26))!important;
  border-radius:21px!important;
}
div[data-testid="stExpander"] [data-testid="stExpanderDetails"]{
  padding:10px 12px 14px 12px!important;
}

/* Inner tabs/Home tabs */
.stTabs [data-baseweb="tab-list"]{
  background:linear-gradient(135deg, rgba(255,255,255,.58), rgba(224,242,254,.32))!important;
  border:1px solid rgba(125,211,252,.22)!important;
  border-radius:24px!important;
  padding:7px!important;
  box-shadow:0 12px 28px rgba(2,132,199,.06)!important;
}
.stTabs [data-baseweb="tab"]{
  border-radius:999px!important;
  min-height:34px!important;
  padding:7px 12px!important;
  font-weight:950!important;
  background:rgba(255,255,255,.54)!important;
}
.stTabs [aria-selected="true"]{
  background:linear-gradient(135deg, rgba(186,230,253,.82), rgba(220,252,231,.56))!important;
  box-shadow:0 8px 20px rgba(2,132,199,.10)!important;
}

/* Floating assistant-like compact card support */
.qx-assistant,.qx-mini-assistant,.quant-assistant{
  position:fixed!important;
  right:16px!important;
  bottom:16px!important;
  z-index:9999!important;
  max-width:280px!important;
  border-radius:26px!important;
  background:linear-gradient(135deg, rgba(255,255,255,.58), rgba(224,242,254,.40))!important;
  border:1px solid rgba(125,211,252,.24)!important;
  box-shadow:0 18px 44px rgba(2,132,199,.10), inset 0 1px 0 rgba(255,255,255,.72)!important;
  backdrop-filter:blur(28px) saturate(190%)!important;
  animation: qxPopFloat .38s cubic-bezier(.2,1.25,.34,1) both!important;
}

/* Phone alignment: keep rows in 2-column card grid instead of one long column */
@media(max-width:760px){
  .main .block-container{padding:.30rem!important;max-width:100vw!important;width:100vw!important;}
  div[data-testid="stHorizontalBlock"]{
    display:grid!important;
    grid-template-columns:repeat(2,minmax(0,1fr))!important;
    gap:.35rem!important;
    width:100%!important;
  }
  div[data-testid="stHorizontalBlock"]>div[data-testid="column"]{width:100%!important;min-width:0!important;flex:unset!important;padding:0!important;}
  div[data-testid="metric-container"]{min-height:82px!important;padding:10px!important;border-radius:20px!important;}
  .stTabs [data-baseweb="tab-list"]{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:.32rem!important;}
  .stTabs [data-baseweb="tab"]{justify-content:center!important;padding:6px!important;font-size:9px!important;}
  section[data-testid="stSidebar"]{width:245px!important;min-width:245px!important;}
  .qx-assistant,.qx-mini-assistant,.quant-assistant{right:8px!important;bottom:8px!important;max-width:245px!important;}
}
@media(max-width:390px){
  div[data-testid="stHorizontalBlock"]{grid-template-columns:repeat(2,minmax(0,1fr))!important;gap:.25rem!important;}
  div[data-testid="metric-container"]{min-height:76px!important;padding:8px!important;border-radius:18px!important;}
  div[data-testid="metric-container"] [data-testid="stMetricValue"]{font-size:15px!important;}
}

</style>
        """,
        unsafe_allow_html=True,
    )


_apply_global_styles_original = apply_global_styles

def apply_global_styles(phone_mode: bool = False):
    _apply_global_styles_original(phone_mode=phone_mode)
    _apply_v5_ocean_glass_styles()
