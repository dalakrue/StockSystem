"""Future extension namespace for safe add/remove modules.

Keep future upgrades in this package or in ui/core standalone files, then import
with try/except from the app shell.  This prevents one optional feature from
breaking the trading app.
"""
