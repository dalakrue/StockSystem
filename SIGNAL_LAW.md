# SIGNAL LAW — main cycle + main memory

User order, 2026-11-23. This law governs how precheck and check
signals are produced for the live month.

1. The main cycle for the current month in this app, together with
   its main memory, is the only source of precheck and check
   signals.
2. The main memory is the cycle's state walked in order from the
   month start, every check slot stepped — the full way. A memory
   with skipped slots is not the main memory.
3. The memory file (data/walk_ledgers_new8/) must live in this repo,
   so the app never restarts from empty memory.
4. The app must never show a stale chain feed as current. When the
   feed is stale, the app calculates itself (fixed 2026-11-23,
   commit c97d53a1).
5. Muse holds the same cycle + verified memory and gives precheck
   and check signals from it. Each check then needs only that
   check's fresh candles.
