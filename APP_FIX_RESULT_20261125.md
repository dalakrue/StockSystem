# App fix result — 2026-11-25 ~20:25 MMT (user order in side chat, screenshot 20:15)

## What was broken — root causes found in code
1. **Sidebar open/close dead on phone:** `core/mobile_lite_mode_20260628.py` extreme-mobile CSS had
   `section[data-testid="stSidebar"]{display:none!important;}` — on a phone (mobile lite auto-detected)
   the sidebar could never show, whatever button was tapped. Also the ☰ reopen button was placed
   top-right (`right:464px` / `right:14px` on phone), underneath the floating control bar.
2. **Auto load + calculate on open dead:** `_c22_data_loaded()` in the Field 3 panel still demanded a
   Twelve Data key or a pre-loaded symbol set, but the signal path has fetched from Dukascopy (keyless)
   since 2026-11-16. On a fresh open neither condition held, so every evaluation was blocked before it
   tried — page stuck at 0/28. Also `maybe_auto_load_field3` set its attempted flag BEFORE checking the
   key pool, so one early failure blocked auto-load for the whole session. And month panels only
   evaluated inside the live check window, never on open.
3. **Floating section huge, no close:** 440px wide, up to 74vh, reminders open by default, no close button.
4. **REAL vs TEST confusion:** long paragraph captions, no colour/line separation.

## Fixes (7 files, no cycle maths, no registry, no check times, no sizing changed)
- `core/mobile_lite_mode_20260628.py` — sidebar `display:none` removed; overlay width instead.
- `ui/sidebar_hard_lock.py` — ☰ reopen button back to TOP-LEFT (dark chip, z 1000003); in-sidebar
  collapse button made dark/large/visible.
- `tabs/antd_page_router_20260615.py` — sidebar top now says how to close/open it, in plain words.
- `ui/field3_multisymbol_regime_summary_20260722.py` —
  * `_c22_data_loaded()` now returns True (fetch itself reports failures honestly as DATA INCOMPLETE).
  * Combined panels: AUTO-CALCULATE ON OPEN — latest check evaluated once per session per window on
    open, even outside the live window; live-window rule unchanged after that.
  * Floating bar: 300px / max 52vh, ✕ close button → collapses to one small "⚙ Controls — tap to open"
    button; Reminders OFF by default; TEST buttons separated under an orange "TEST only" label.
  * Sections: 🟢 GREEN = REAL CHECK, 🔵 BLUE = REAL PRECHECK, 🟧 ORANGE dashed = TEST ONLY (with an
    END OF TEST line), ⚪ GREY = History; thick lines (8px) between sections; colour legend at the top;
    long captions cut to one short line each.
- `core/auto_load_startup_20261019.py` — attempted flag only set when a real load is about to run.
- `core/app/runner.py` — auto-load outcome stored in session state instead of swallowed silently.
- `core/canonical_feed.py` — History gets the grey section header; caption shortened.

## Verification
- py_compile: all 7 files OK.
- Unit checks: gate returns True; float CSS 300px, 440px gone; sidebar CSS left:14px; mobile CSS has no sidebar display:none.
- Isolated fake-Streamlit test of `_render_floating_controls`: open state renders ✕ + Refresh + Reminders +
  Test + Precheck Test; closed state renders only "⚙ Controls — tap to open". PASS.
- Full AppTest: timed out at 90s in this VM — the new on-open evaluation now actually runs a real
  Dukascopy evaluation on a fresh session (previously the gate blocked it, so AppTest was fast and empty).
  Not counted as a pass; live verification is by opening the live app once after the push.
- Honest limit: CSS sidebar behaviour cannot be proven by AppTest (it does not apply CSS) — the user
  confirms with one tap on his phone: ☰ top-left opens, ✕/« at the sidebar top closes.

## Push warning
Pushing redeploys the Streamlit app and wipes any Twelve key pasted in-app (session only).
Durable fix remains: Streamlit Secrets `[api_keys] second_api`. The signal path itself is Dukascopy
(keyless), so signals/auto-calc do not depend on that key.
