import hashlib
import html
import time
from typing import Iterable, List, Optional

import pandas as pd
import streamlit as st


def _safe_key(text: str) -> str:
    return hashlib.md5(str(text).encode('utf-8', errors='ignore')).hexdigest()[:10]


def _choice_button_callback(key: str, option: str) -> None:
    """Set a button-tab choice before Streamlit starts the next rerun.

    Streamlit executes callbacks before the script body. This lets the app know a
    navigation click happened before global auto-refresh and heavy panels run, so
    inner tabs such as Doo Prime can open immediately instead of waiting behind a
    connector/deep-analysis refresh.
    """
    try:
        st.session_state[key] = option
        st.session_state["ui_navigation_click_ts"] = time.time()
        st.session_state["ui_navigation_target"] = f"{key}:{option}"
        try:
            from core.ui_relationship import mark_navigation
            root = str(key).replace("_lazy_workspace", "").replace("_lazy_section", "").replace("_", " ").title()
            mark_navigation(root, str(option))
        except Exception:
            pass
    except Exception:
        pass


def choice_buttons(label: str, options: Iterable[str], key: str, columns: int = 4, default: Optional[str] = None, help_text: str = "") -> str:
    """Render radio-like choices as persistent fast buttons.

    The selected value is updated by a Streamlit callback, before the next rerun
    begins. This prevents the old slow behavior where a heavy previously-open
    section could render before the new section was entered.
    """
    options = list(options or [])
    if not options:
        return ""
    if key not in st.session_state or st.session_state.get(key) not in options:
        st.session_state[key] = default if default in options else options[0]

    if label:
        st.markdown(f"<div class='qx-choice-label'>{html.escape(str(label))}</div>", unsafe_allow_html=True)
    if help_text:
        st.caption(help_text)

    cols = st.columns(min(max(1, int(columns or 4)), max(1, len(options))))
    for idx, option in enumerate(options):
        active = option == st.session_state.get(key)
        button_label = f"✅ {option}" if active else str(option)
        with cols[idx % len(cols)]:
            st.button(
                button_label,
                use_container_width=True,
                key=f"{key}_btn_{idx}_{_safe_key(option)}",
                on_click=_choice_button_callback,
                args=(key, option),
            )
    return st.session_state.get(key, options[0])


def sound_alert(alert_key: str, title: str, message: str = "", seconds: int = 7, cooldown_seconds: int = 600, severity: str = "warning") -> bool:
    """Play one browser sound/vibration alert with cooldown, then show a Telegram-style popup card."""
    now = time.time()
    state_key = f"sound_alert_last_{alert_key}"
    last = float(st.session_state.get(state_key, 0) or 0)
    can_play = (now - last) >= max(5, int(cooldown_seconds or 600))
    severity = str(severity or "warning").lower()
    if severity not in ["danger", "warning", "success", "info"]:
        severity = "warning"

    import streamlit.components.v1 as components
    safe_title = html.escape(str(title))
    safe_message = html.escape(str(message))
    seconds = max(3, min(12, int(seconds or 7)))

    st.markdown(
        f"""
        <div class="tg-alert tg-{severity}">
            <div class="tg-alert-title">{safe_title}</div>
            <div class="tg-alert-msg">{safe_message}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not can_play:
        return False

    st.session_state[state_key] = now
    components.html(
        f"""
        <script>
        (async function() {{
          const seconds = {seconds};
          const stopAt = Date.now() + seconds * 1000;
          try {{ if (navigator.vibrate) navigator.vibrate([650,160,650,160,900,250,1200]); }} catch(e) {{}}
          try {{
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioCtx();
            async function beep(freq, len) {{
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.type = "sine";
              osc.frequency.value = freq;
              gain.gain.setValueAtTime(0.0001, ctx.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.30, ctx.currentTime + 0.02);
              gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + len / 1000);
              osc.connect(gain); gain.connect(ctx.destination);
              osc.start(); osc.stop(ctx.currentTime + len / 1000 + 0.03);
              await new Promise(r => setTimeout(r, len + 80));
            }}
            while(Date.now() < stopAt) {{ await beep(988, 220); await beep(1480, 220); await beep(784, 260); }}
            setTimeout(() => ctx.close && ctx.close(), 500);
          }} catch(e) {{
            try {{
              const audio = new Audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg");
              audio.loop = true; audio.volume = 1.0; audio.play();
              setTimeout(() => {{ audio.pause(); audio.currentTime = 0; }}, seconds * 1000);
            }} catch(err) {{}}
          }}
        }})();
        </script>
        """,
        height=0,
    )
    return True


def recent_signal_caption(signal_key: str, max_hours: float = 21.0) -> str:
    ts = st.session_state.get(signal_key)
    if not ts:
        return ""
    try:
        t = pd.to_datetime(ts)
        age_h = (pd.Timestamp.now() - t).total_seconds() / 3600.0
        if age_h > float(max_hours):
            return ""
        return f"Last signal: {t.strftime('%Y-%m-%d %H:%M:%S')} ({age_h:.1f}h ago)"
    except Exception:
        return ""


def set_recent_signal(signal_key: str):
    st.session_state[signal_key] = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')


def collapsible_text(title: str, text: str, expanded: bool = False, threshold_words: int = 10):
    words = len(str(text or "").split())
    if words > int(threshold_words or 10):
        with st.expander(title, expanded=expanded):
            st.write(text)
    else:
        st.caption(text)


def sidebar_download_only_notice(kind: str = "data"):
    """Small standard note used where old local download buttons were removed."""
    st.caption(f"⬇️ {kind} export is centralized in the sidebar Download Center. Auto-save/backend stays active.")
