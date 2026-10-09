import time
import streamlit as st

from core.common import DEFAULT_TABS, log_event
from core.styles import request_close_sidebar
from core.ui_relationship import mark_navigation, sync_shared_connection_signature
from core.ui.effects import queue_ui_popup
from core.data_connectors import manual_connect
from core.websocket_feed import render_websocket_panel, websocket_status
from core.system_upgrade import sidebar_health_card, add_snapshot_button
from core.system_contract import render_sidebar_mini_contract, record_system_event
from core.system_relations import render_system_relation_hub
from core.global_upgrade import render_sidebar_upgrade_panel, render_sidebar_pro_header, data_quality, get_live_df
from core.ui.compact import render_metric_cards

try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    def st_autorefresh(*args, **kwargs):
        return None




def _safe_log_event(message: str):
    """Crash-proof event logger for sidebar/timer actions.

    Fixes NameError when the timer Start/Reset button calls logging before
    other helper modules are loaded. Keeps original log_event behavior when
    available and silently continues when logging fails.
    """
    try:
        log_event(str(message))
    except Exception:
        try:
            record_system_event("sidebar_timer", str(message))
        except Exception:
            pass

def _safe_rerun():
    try:
        st.rerun()
    except Exception:
        try:
            st.experimental_rerun()
        except Exception:
            pass

def _fmt_timer(seconds):
    try:
        seconds = max(0, int(seconds))
    except Exception:
        seconds = 0
    h = seconds // 3600
    m = (seconds % 3600) // 60
    sec = seconds % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"

def _timer_alarm_html(duration_seconds: int = 8):
    """Play a longer browser-side timer alarm.

    Streamlit reruns only once when the timer finishes, so a single short audio tag
    is easy to miss. This component uses Web Audio beeps for about 8 seconds and
    also asks the phone/browser to vibrate when supported.
    """
    try:
        duration_seconds = int(max(5, min(duration_seconds, 10)))
    except Exception:
        duration_seconds = 8

    import streamlit.components.v1 as components

    components.html(
        f"""
        <div style="font-family:Arial,sans-serif;padding:10px;border-radius:14px;background:#fff7ed;border:1px solid #fed7aa;color:#9a3412;font-weight:800;text-align:center;">
          ⏰ TIME UP — alarm playing for {duration_seconds} seconds
        </div>
        <script>
        (async function() {{
          const seconds = {duration_seconds};
          const stopAt = Date.now() + seconds * 1000;
          try {{
            if (navigator.vibrate) {{
              navigator.vibrate([700,220,700,220,700,220,1000,300,1000,300,1400]);
            }}
          }} catch(e) {{}}

          try {{
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            const ctx = new AudioCtx();
            async function oneBeep(freq, lengthMs) {{
              const osc = ctx.createOscillator();
              const gain = ctx.createGain();
              osc.type = "square";
              osc.frequency.value = freq;
              gain.gain.setValueAtTime(0.0001, ctx.currentTime);
              gain.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + 0.02);
              gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + lengthMs / 1000);
              osc.connect(gain);
              gain.connect(ctx.destination);
              osc.start();
              osc.stop(ctx.currentTime + lengthMs / 1000 + 0.03);
              await new Promise(r => setTimeout(r, lengthMs + 110));
            }}
            while (Date.now() < stopAt) {{
              await oneBeep(880, 260);
              await oneBeep(1320, 260);
            }}
            setTimeout(() => ctx.close && ctx.close(), 600);
          }} catch(e) {{
            try {{
              const audio = new Audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg");
              audio.loop = true;
              audio.volume = 1.0;
              audio.play();
              setTimeout(() => {{ audio.pause(); audio.currentTime = 0; }}, seconds * 1000);
            }} catch(err) {{}}
          }}
        }})();
        </script>
        """,
        height=58,
    )

def _sidebar_timer_panel():
    """Fast sidebar timer with browser-side countdown + alarm.

    The old timer only changed when Streamlit reran, so it could look frozen on
    some desktops/phones. This version still uses st_autorefresh when available,
    but the visible countdown and final alarm are driven in the browser too.
    """
    import streamlit.components.v1 as components

    st.session_state.setdefault("sidebar_timer_minutes", int(st.session_state.get("timer_minutes", 120) or 120))
    st.session_state.setdefault("sidebar_timer_end", 0.0)
    st.session_state.setdefault("sidebar_timer_alerted", False)

    with st.expander("⏱ Trade Timer / Sound Alert", expanded=bool(st.session_state.get("sidebar_timer_end", 0))):
        mins = st.number_input(
            "Timer minutes",
            min_value=1,
            max_value=1440,
            value=int(st.session_state.get("sidebar_timer_minutes", 120) or 120),
            step=5,
            key="sidebar_timer_minutes_input",
        )
        st.session_state.sidebar_timer_minutes = int(mins)

        # Streamlit Cloud/mobile browsers can block alarm audio until the user
        # unlocks sound once. This tiny component stores that permission after
        # a tap/click, so the timer alarm has a much higher chance to play.
        components.html(
            """
            <button id="unlockTimerSound" style="width:100%;min-height:36px;border-radius:999px;border:1px solid #93c5fd;background:#eff6ff;font-weight:800;cursor:pointer;">🔊 Enable Cloud Timer Sound</button>
            <div id="unlockTimerStatus" style="font-size:11px;text-align:center;margin-top:4px;color:#075985;">Tap once after opening the app, especially on Streamlit Cloud or phone.</div>
            <script>
            (function(){
              const btn = document.getElementById('unlockTimerSound');
              const status = document.getElementById('unlockTimerStatus');
              async function unlock(){
                try {
                  const AudioCtx = window.AudioContext || window.webkitAudioContext;
                  const ctx = new AudioCtx();
                  const osc = ctx.createOscillator();
                  const gain = ctx.createGain();
                  osc.frequency.value = 660; gain.gain.value = 0.001;
                  osc.connect(gain); gain.connect(ctx.destination);
                  osc.start(); osc.stop(ctx.currentTime + 0.04);
                  localStorage.setItem('m1_adx_timer_sound_unlocked','yes');
                  status.textContent = 'Sound unlocked. Timer alarm can play on this browser.';
                  setTimeout(() => ctx.close && ctx.close(), 120);
                } catch(e) { status.textContent = 'Browser blocked sound. Keep this page active and tap Start timer again.'; }
              }
              btn.addEventListener('click', unlock);
              btn.addEventListener('touchend', function(e){ e.preventDefault(); unlock(); }, {passive:false});
            })();
            </script>
            """,
            height=76,
        )

        t1, t2 = st.columns(2)
        with t1:
            if st.button("▶ Start", use_container_width=True, key="sidebar_timer_start"):
                st.session_state.sidebar_timer_end = time.time() + int(mins) * 60
                st.session_state.sidebar_timer_alerted = False
                _safe_log_event(f"Sidebar timer started: {int(mins)} minutes")
        with t2:
            if st.button("■ Reset", use_container_width=True, key="sidebar_timer_reset"):
                st.session_state.sidebar_timer_end = 0.0
                st.session_state.sidebar_timer_alerted = False
                _safe_log_event("Sidebar timer reset")

        end = float(st.session_state.get("sidebar_timer_end", 0) or 0)
        now = time.time()
        active = end > now
        remaining = max(0, int(end - now)) if end else 0
        alarm_id = f"sidebar_trade_timer_alarm_{int(end)}" if end else "sidebar_trade_timer_alarm_none"

        status = "RUNNING" if active else ("TIME UP" if end else "STOPPED")
        st.markdown(
            f"""
            <div class="sidebar-timer-card">
                <div><b>Status:</b> {status}</div>
                <div class="sidebar-timer-big" id="server_timer_fallback">{_fmt_timer(remaining)}</div>
                <small>Browser countdown updates every second. Time-up alarm plays 8 seconds + phone vibration when supported.</small>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if end:
            components.html(
                f"""
                <div style="font-family:Arial,sans-serif;padding:8px 10px;border-radius:14px;background:#eef6ff;border:1px solid #bfdbfe;color:#0f172a;text-align:center;">
                  <div style="font-size:12px;font-weight:800;letter-spacing:.04em;">LIVE TIMER</div>
                  <div id="liveTimer" style="font-size:24px;font-weight:900;margin-top:3px;">--:--:--</div>
                  <div id="liveTimerStatus" style="font-size:12px;margin-top:2px;">syncing...</div>
                </div>
                <script>
                (function() {{
                  const endMs = {float(end) * 1000:.0f};
                  const alarmKey = "{alarm_id}";
                  const timerEl = document.getElementById("liveTimer");
                  const statusEl = document.getElementById("liveTimerStatus");
                  function pad(n) {{ return String(n).padStart(2, "0"); }}
                  function fmt(sec) {{
                    sec = Math.max(0, Math.floor(sec));
                    const h = Math.floor(sec / 3600);
                    const m = Math.floor((sec % 3600) / 60);
                    const s = sec % 60;
                    return pad(h) + ":" + pad(m) + ":" + pad(s);
                  }}
                  async function playAlarm() {{
                    if (localStorage.getItem(alarmKey) === "played") return;
                    localStorage.setItem(alarmKey, "played");
                    statusEl.textContent = "TIME UP — alarm playing";
                    try {{ if (navigator.vibrate) navigator.vibrate([700,220,700,220,1000,300,1200,300,1400]); }} catch(e) {{}}
                    const stopAt = Date.now() + 8000;
                    try {{
                      const AudioCtx = window.AudioContext || window.webkitAudioContext;
                      const ctx = new AudioCtx();
                      async function beep(freq, len) {{
                        const osc = ctx.createOscillator();
                        const gain = ctx.createGain();
                        osc.type = "square"; osc.frequency.value = freq;
                        gain.gain.setValueAtTime(0.0001, ctx.currentTime);
                        gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + 0.02);
                        gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + len / 1000);
                        osc.connect(gain); gain.connect(ctx.destination);
                        osc.start(); osc.stop(ctx.currentTime + len / 1000 + 0.03);
                        await new Promise(r => setTimeout(r, len + 100));
                      }}
                      while (Date.now() < stopAt) {{ await beep(880, 250); await beep(1320, 250); }}
                      setTimeout(() => ctx.close && ctx.close(), 500);
                    }} catch(e) {{}}
                  }}
                  async function playNearEndBeep(rem) {{
                    const slot = Math.floor(rem / 5);
                    const key = alarmKey + ":warn:" + slot;
                    if (localStorage.getItem(key) === "played") return;
                    localStorage.setItem(key, "played");
                    try {{ if (navigator.vibrate) navigator.vibrate([120,80,120]); }} catch(e) {{}}
                    try {{
                      const AudioCtx = window.AudioContext || window.webkitAudioContext;
                      const ctx = new AudioCtx();
                      const osc = ctx.createOscillator();
                      const gain = ctx.createGain();
                      osc.type = "sine"; osc.frequency.value = 1040;
                      gain.gain.setValueAtTime(0.0001, ctx.currentTime);
                      gain.gain.exponentialRampToValueAtTime(0.18, ctx.currentTime + 0.015);
                      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + 0.18);
                      osc.connect(gain); gain.connect(ctx.destination);
                      osc.start(); osc.stop(ctx.currentTime + 0.21);
                      setTimeout(() => ctx.close && ctx.close(), 350);
                    }} catch(e) {{}}
                  }}
                  function tick() {{
                    const rem = (endMs - Date.now()) / 1000;
                    timerEl.textContent = fmt(rem);
                    if (rem <= 0) {{
                      statusEl.textContent = "TIME UP";
                      playAlarm();
                    }} else if (rem <= 60) {{
                      statusEl.textContent = "FINAL 1 MIN — beep every 5 seconds";
                      if (Math.floor(rem) % 5 === 0) playNearEndBeep(rem);
                    }} else {{
                      statusEl.textContent = "running";
                    }}
                  }}
                  tick();
                  setInterval(tick, 1000);
                }})();
                </script>
                """,
                height=96,
            )

    end = float(st.session_state.get("sidebar_timer_end", 0) or 0)
    now = time.time()
    if end and end > now:
        try:
            st_autorefresh(interval=1000, key="sidebar_trade_timer_tick")
        except Exception:
            pass
    elif end and end <= now and not bool(st.session_state.get("sidebar_timer_alerted", False)):
        st.session_state.sidebar_timer_alerted = True
        st.warning("⏱ Timer reached 0. Check your trade / exit plan now.")

