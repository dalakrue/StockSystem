"""Central copy/download engine for the 2026-06-15 UI stability upgrade.

Every visible copy button should route here.  The clipboard action uses a
self-contained Streamlit component and does not depend on the app/sidebar DOM.
A download fallback is always rendered so phone/browser clipboard blocking never
looks like a fake successful copy.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from typing import Any

import streamlit as st


def _safe_key(key: str) -> str:
    raw = str(key or "copy")
    return re.sub(r"[^A-Za-z0-9_-]", "_", raw)[:80] or "copy"


def _file_name(label: str, key: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_-]+", "_", str(label or key or "copy")).strip("_")[:42]
    if not base:
        base = "copy_payload"
    digest = hashlib.sha1(str(key).encode("utf-8", "ignore")).hexdigest()[:7]
    return f"{base}_{digest}.txt"



def sanitize_copy_payload(text: Any, *, full: bool = False, max_chars: int = 120_000) -> str:
    """Return current, useful, deduplicated copy text without altering calculations.

    The filter is presentation-only: it removes unavailable/placeholder rows, repeated
    lines, and obvious history-table sections from menu copy payloads.
    """
    raw = str(text or "").replace("\x00", "").replace("\r\n", "\n")
    blocked = ("data unavailable", "unavailable", "not available", "n/a", "nan",
               "none", "placeholder", "run calculation first", "no data")
    history_headers = ("history", "last 25 day", "last 25 broker", "historical")
    out, seen = [], set()
    skip_history = False
    for source_line in raw.splitlines():
        line = source_line.strip()
        low = line.lower()
        if any(h in low for h in history_headers) and ("=" in line or line.endswith(":")):
            skip_history = True
            continue
        if skip_history and (not line or (line.isupper() and len(line) < 90)):
            if line and not any(h in low for h in history_headers):
                skip_history = False
            else:
                continue
        if skip_history:
            continue
        if not line or any(token in low for token in blocked):
            continue
        norm = re.sub(r"\s+", " ", low)
        if norm in seen:
            continue
        seen.add(norm)
        out.append(line)
    payload = "\n".join(out).strip()
    if len(payload) > max_chars:
        payload = payload[:max_chars].rsplit("\n", 1)[0] + "\n[Copy payload trimmed for mobile stability]"
    return payload or "No current available Lunch data to copy."

def central_copy_button(label: str, text: Any, key: str, *, height: int = 92, show_fallback: bool = True) -> None:
    """Render one real clipboard action with an in-component manual fallback.

    Only the click event is bound. Older pointer/touch duplication could fire the
    handler twice on phones and make a successful copy appear dead.
    """
    import streamlit.components.v1 as components

    safe_key = _safe_key(key)
    safe_label = html.escape(str(label or "Copy"))
    payload = sanitize_copy_payload(text, full="full" in str(label).lower())
    text_json = json.dumps(payload)
    st.session_state[f"central_copy_payload_digest_{safe_key}"] = hashlib.sha1(payload.encode("utf-8", "ignore")).hexdigest()
    # Explicit parent-level iframe rules prevent broad app CSS or floating
    # navigation layers from intercepting taps on the clipboard component.
    st.markdown(
        """<style>
        div[data-testid="stCustomComponentV1"] iframe,
        iframe[title="st.iframe"] {
            pointer-events: auto !important;
            position: relative !important;
            z-index: 2147482000 !important;
            touch-action: manipulation !important;
        }
        div[data-testid="stCustomComponentV1"] {
            position: relative !important;
            z-index: 2147482000 !important;
            isolation: isolate !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    components.html(
        f"""
<style>
*{{box-sizing:border-box}}body{{margin:0;background:transparent;font-family:Inter,ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;}}
.new7-copy-wrap{{width:100%;padding:1px 0 0;position:relative;z-index:2147483000;pointer-events:auto!important}}
.new7-copy-btn{{width:100%;min-height:50px;border-radius:18px;border:1px solid rgba(14,116,144,.22);cursor:pointer;font-weight:950;color:#fff;font-size:14px;line-height:1.12;background:radial-gradient(circle at 12% 8%,rgba(255,255,255,.42),transparent 24%),linear-gradient(135deg,#0284c7,#06b6d4 54%,#14b8a6);box-shadow:0 14px 30px rgba(2,132,199,.20),inset 0 1px 0 rgba(255,255,255,.42);touch-action:manipulation;-webkit-tap-highlight-color:transparent;user-select:none;position:relative;z-index:2147483001;pointer-events:auto!important;-webkit-user-select:none;}}
.new7-copy-btn:active{{transform:scale(.985)}}.new7-copy-status{{min-height:18px;text-align:center;color:#075985;margin-top:5px;font-size:12px;font-weight:900}}
.new7-copy-manual{{display:none;width:100%;height:44px;margin-top:4px;border-radius:10px;border:1px solid #38bdf8;padding:5px;font-size:10px;}}
@media(max-width:520px){{.new7-copy-btn{{min-height:54px;font-size:13px;padding:8px 6px}}.new7-copy-status{{font-size:11px}}}}
</style>
<div class="new7-copy-wrap">
  <button class="new7-copy-btn" id="new7_copy_{safe_key}" type="button" tabindex="0" aria-label="Copy payload to clipboard">📋 {safe_label}</button>
  <textarea id="new7_copy_text_{safe_key}" class="new7-copy-manual" readonly aria-label="Manual copy fallback"></textarea>
  <div class="new7-copy-status" id="new7_copy_status_{safe_key}">Ready • tap once</div>
</div>
<script>(function(){{
 const btn=document.getElementById('new7_copy_{safe_key}');
 const ta=document.getElementById('new7_copy_text_{safe_key}');
 const status=document.getElementById('new7_copy_status_{safe_key}');
 const txt={text_json}; ta.value=txt; let busy=false; btn.style.pointerEvents='auto';
 async function copyNow(e){{
   if(e){{e.preventDefault();e.stopPropagation();}}
   if(busy) return;
   busy=true; btn.disabled=true; status.textContent='Copying…';
   let ok=false;
   try{{
     if(navigator.clipboard && window.isSecureContext){{
       await navigator.clipboard.writeText(txt); ok=true;
     }}
   }}catch(err){{ok=false;}}
   if(!ok){{
     try{{
       if(window.parent && window.parent.navigator && window.parent.navigator.clipboard && window.parent.isSecureContext){{
         await window.parent.navigator.clipboard.writeText(txt); ok=true;
       }}
     }}catch(err){{ok=false;}}
   }}
   if(!ok){{
     try{{
       ta.style.display='block'; ta.focus(); ta.select(); ta.setSelectionRange(0,ta.value.length);
       ok=!!document.execCommand('copy');
     }}catch(err){{ok=false;}}
   }}
   if(ok){{
     status.textContent='Copied Successfully ✅ Paste now.';
     ta.style.display='none';
     const old=btn.textContent; btn.textContent='✅ Copied';
     setTimeout(function(){{btn.textContent=old;}},1200);
   }}else{{
     ta.style.display='block'; ta.focus(); ta.select(); ta.setSelectionRange(0,ta.value.length);
     status.textContent='Clipboard blocked. Text is selected — press Ctrl+C / long-press Copy.';
   }}
   btn.disabled=false; busy=false;
 }}
 btn.addEventListener('click', copyNow, {{passive:false}});
 btn.addEventListener('keydown', function(e){{ if(e.key==='Enter'||e.key===' ') copyNow(e); }});
}})();</script>
        """,
        height=max(int(height), 104),
        scrolling=False,
    )
    if show_fallback:
        dl_cols = st.columns([1, 1])
        with dl_cols[0]:
            st.download_button(
                "⬇️ Download fallback",
                data=payload,
                file_name=_file_name(label, safe_key),
                mime="text/plain",
                key=f"download_fallback_{safe_key}",
                use_container_width=True,
            )
        with dl_cols[1]:
            with st.expander("Manual text fallback", expanded=False):
                st.text_area("Long-press / select all if browser copy is blocked", payload, height=160, key=f"textarea_fallback_{safe_key}")


def central_copy_result(text: Any, key: str, *, height: int = 102) -> None:
    """Render the actual clipboard action after a server-side payload is prepared.

    Kept separate from the trigger button so expensive full serialization remains
    lazy, while the resulting clipboard control is phone-safe and has fallbacks.
    """
    central_copy_button("Copy prepared payload", text, key, height=height, show_fallback=True)


def copy_fallback_script(text: str, key: str = "copy_fallback") -> None:
    central_copy_button("Copy", text, key, show_fallback=True)
