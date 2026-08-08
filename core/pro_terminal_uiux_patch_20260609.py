"""Light button-state patch: prevents washed-out white clicked buttons."""
from __future__ import annotations


def apply(ns: dict) -> None:
    import html
    import json
    import re
    import streamlit as st
    import streamlit.components.v1 as components

    old_css = ns.get("apply_pro_terminal_css")

    def apply_pro_terminal_css_v2() -> None:
        if callable(old_css):
            old_css()
        st.markdown(
            """
<style>
.stButton>button,.stDownloadButton>button,section[data-testid="stSidebar"] .stButton>button{
  background:linear-gradient(135deg,rgba(14,116,144,.82),rgba(8,145,178,.78) 52%,rgba(13,148,136,.78))!important;
  color:#f8fafc!important;
  border:1px solid rgba(125,211,252,.28)!important;
  box-shadow:0 8px 18px rgba(2,132,199,.14), inset 0 1px 0 rgba(255,255,255,.28)!important;
  text-shadow:0 1px 1px rgba(15,23,42,.25)!important;
}
.stButton>button:hover,.stDownloadButton>button:hover,section[data-testid="stSidebar"] .stButton>button:hover{
  background:linear-gradient(135deg,rgba(14,116,144,.90),rgba(8,145,178,.84) 52%,rgba(13,148,136,.84))!important;
  color:#ffffff!important;
  filter:none!important;
}
.stButton>button:active,.stDownloadButton>button:active,section[data-testid="stSidebar"] .stButton>button:active,
.stButton>button:focus,.stDownloadButton>button:focus,section[data-testid="stSidebar"] .stButton>button:focus{
  background:linear-gradient(135deg,rgba(12,74,110,.92),rgba(14,116,144,.88),rgba(15,118,110,.88))!important;
  color:#ffffff!important;
  outline:2px solid rgba(125,211,252,.32)!important;
}
</style>
""",
            unsafe_allow_html=True,
        )

    def render_mobile_copy_button_v2(label: str, text: str, key: str) -> None:
        safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", str(key or "copy"))
        safe_label = html.escape(str(label or "Copy"))
        text_json = json.dumps(str(text or ""))
        components.html(
            f"""
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;}}
.qx-copy-mobile-btn{{width:100%;min-height:52px;border-radius:20px;border:1px solid rgba(125,211,252,.34);cursor:pointer;font-weight:950;color:#f8fafc;font-size:14px;background:linear-gradient(135deg,rgba(14,116,144,.86),rgba(8,145,178,.80) 54%,rgba(13,148,136,.80));box-shadow:0 10px 22px rgba(2,132,199,.16),inset 0 1px 0 rgba(255,255,255,.28);text-shadow:0 1px 1px rgba(15,23,42,.25);touch-action:manipulation;-webkit-tap-highlight-color:transparent;}}
.qx-copy-mobile-btn:hover{{background:linear-gradient(135deg,rgba(14,116,144,.92),rgba(8,145,178,.86),rgba(13,148,136,.86));color:#fff;}}
.qx-copy-mobile-btn:active,.qx-copy-mobile-btn:focus{{background:linear-gradient(135deg,rgba(12,74,110,.94),rgba(14,116,144,.90),rgba(15,118,110,.90));color:#fff;outline:2px solid rgba(125,211,252,.30);}}
.qx-copy-status{{min-height:18px;text-align:center;color:#075985;margin-top:6px;font-size:12px;font-weight:900;}}
@media(max-width:520px){{.qx-copy-mobile-btn{{min-height:56px;font-size:13.5px;padding:10px 8px;}}}}
</style>
<button class="qx-copy-mobile-btn" id="qx_copy_{safe_key}" type="button">📋 {safe_label}</button>
<textarea id="qx_copy_text_{safe_key}" readonly style="position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;opacity:.01;"></textarea>
<div class="qx-copy-status" id="qx_copy_status_{safe_key}">Ready</div>
<script>(function(){{
 const btn=document.getElementById('qx_copy_{safe_key}'); const ta=document.getElementById('qx_copy_text_{safe_key}'); const status=document.getElementById('qx_copy_status_{safe_key}'); const txt={text_json}; ta.value=txt; let busy=false;
 async function copyNow(e){{ if(e){{e.preventDefault();e.stopPropagation();}} if(busy)return; busy=true; let ok=false; try{{ if(navigator.clipboard && window.isSecureContext){{ await navigator.clipboard.writeText(txt); ok=true; }} }}catch(err){{ok=false;}}
 if(!ok){{ try{{ ta.style.left='0px';ta.style.top='0px';ta.style.width='2px';ta.style.height='2px';ta.focus();ta.select();ta.setSelectionRange(0,ta.value.length);ok=document.execCommand('copy');ta.blur();ta.style.left='-9999px';ta.style.top='-9999px'; }}catch(err){{ok=false;}} }}
 status.textContent=ok?'Copied ✅ Paste now.':'Copy blocked — use fallback text below.'; if(ok){{btn.textContent='✅ Copied'; setTimeout(function(){{btn.textContent='📋 {safe_label}';}},1300);}} setTimeout(function(){{busy=false;}},350); }}
 btn.addEventListener('pointerup',copyNow,{{passive:false}}); btn.addEventListener('click',copyNow,{{passive:false}}); btn.addEventListener('touchend',copyNow,{{passive:false}});
}})();</script>
""",
            height=92,
        )

    ns["apply_pro_terminal_css"] = apply_pro_terminal_css_v2
    ns["render_mobile_copy_button"] = render_mobile_copy_button_v2
