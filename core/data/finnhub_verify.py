"""Finnhub cross-check of the Twelve Data gate bars (user
order 2026-11-28: the three-API combine — Twelve = data,
Finnhub = verification + context, OpenRouter = words).

For a manual CHECK Calculate, the signal (H1) bar that the
Twelve calculation used for each symbol is fetched again from
Finnhub's forex candle endpoint and the closes are compared.
Two independent feeds agreeing on the gate bar is the stamp
that the data behind the signal is real; a disagreement names
the worst symbols so the user can see exactly where the feeds
part.

Dormant by default: it does nothing unless a key is configured
in the app's Streamlit secrets as::

    [finnhub]
    api_key = "..."

Safety contract (same as the save-back): NEVER raises, one
attempt per symbol, short timeout, no retries. Any failure —
no key, transport error, a plan refusal, a "no_data" answer —
degrades to a status the UI can show ("not configured" /
"unavailable"); it never blocks or alters the signal.

NOTE: whether Finnhub's free plan serves forex candles at all
must be verified live by the user; the code treats a refusal
exactly like any other unavailability.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

_API_ROOT = "https://finnhub.io/api/v1"
_TIMEOUT_S = 8.0
# Two retail feeds' H1 closes for the same bar normally agree
# to a few pips (spread differences). 0.10% is ~10 pips on a
# 1.0000 pair — far above spread noise, far below any real
# data fault (a shifted or wrong bar differs by much more).
_TOLERANCE = 0.0010


def _api_key():
    """Finnhub key from Streamlit secrets, else None. Never
    raises; None outside Streamlit or with nothing configured."""
    try:
        import streamlit as st
        secrets = st.secrets
    except Exception:
        return None
    try:
        section = secrets["finnhub"]
        if isinstance(section, dict):
            for field in ("api_key", "token", "key"):
                val = section.get(field)
                if val and str(val).strip():
                    return str(val).strip()
        elif isinstance(section, str) and section.strip():
            return section.strip()
    except Exception:
        pass
    try:
        val = secrets["FINNHUB_API_KEY"]
        if val and str(val).strip():
            return str(val).strip()
    except Exception:
        pass
    return None


def is_configured():
    return _api_key() is not None


def _http_get(url):
    """One GET attempt; returns (status, parsed_json_or_None)
    for every HTTP response. Raises only on transport failure;
    callers swallow. Module-level so tests can monkeypatch the
    whole HTTP layer here."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "stocksystem-verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
            parsed = json.loads(body) if body else None
        except Exception:
            parsed = None
        return e.code, parsed


def _finnhub_symbol(sym):
    """App symbol (EURUSD) -> Finnhub forex symbol
    (OANDA:EUR_USD)."""
    s = str(sym).strip().upper()
    if len(s) == 6 and s.isalpha():
        return f"OANDA:{s[:3]}_{s[3:]}"
    return f"OANDA:{s}"


def _unix(ts):
    """Unix seconds for a timestamp, treating naive as UTC."""
    import datetime as _dt
    import pandas as pd
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return int(t.timestamp())


def _finnhub_close(sym, sig_ts, token):
    """Finnhub's close for the H1 bar opening at sig_ts, or
    None when Finnhub has no usable bar (no data, refusal,
    transport). Never raises."""
    try:
        frm = _unix(sig_ts)
        params = urllib.parse.urlencode({
            "symbol": _finnhub_symbol(sym),
            "resolution": "60",
            "from": frm,
            "to": frm + 3600,
            "token": token,
        })
        status, payload = _http_get(
            f"{_API_ROOT}/forex/candle?{params}")
        if status != 200 or not isinstance(payload, dict):
            return None
        if payload.get("s") != "ok":
            return None
        closes = payload.get("c") or []
        stamps = payload.get("t") or []
        for t, c in zip(stamps, closes):
            if int(t) == frm:
                return float(c)
        if closes:
            return float(closes[0])
        return None
    except Exception:
        return None


def verify_gate_bars(symbols, sig_ts, twelve_closes, token=None):
    """Compare Finnhub's signal-bar closes against the Twelve
    closes the calculation used.

    symbols: the cycle's symbol list; sig_ts: the H1 signal
    bar's open stamp (UTC); twelve_closes: {symbol: close}.
    Returns a verdict dict:
      {"status": "not configured"}
      {"status": "unavailable", "text": ...}
      {"status": "AGREE"|"DISAGREE", "text": ...,
       "compared": n, "worst": [(sym, rel_diff), ...]}
    Never raises."""
    try:
        if token is None:
            token = _api_key()
        if not token:
            return {"status": "not configured"}
        diffs = []
        missing = []
        for sym in symbols:
            t_close = (twelve_closes or {}).get(sym)
            if t_close is None:
                continue
            f_close = _finnhub_close(sym, sig_ts, token)
            if f_close is None:
                missing.append(sym)
                continue
            try:
                rel = abs(f_close - float(t_close)) \
                    / abs(float(t_close))
            except Exception:
                continue
            diffs.append((sym, rel))
        if not diffs:
            return {"status": "unavailable",
                    "text": ("Finnhub verification unavailable "
                             "— it returned no forex candle "
                             "data for the signal bar.")}
        diffs.sort(key=lambda kv: kv[1], reverse=True)
        worst = diffs[:3]
        over = [kv for kv in diffs if kv[1] > _TOLERANCE]
        if over:
            names = ", ".join(
                f"{s} ({100 * d:.2f}%)" for s, d in worst)
            return {"status": "DISAGREE",
                    "compared": len(diffs),
                    "missing": missing,
                    "worst": worst,
                    "text": (f"Finnhub cross-check: DISAGREE — "
                             f"{len(over)} of {len(diffs)} "
                             f"signal-bar closes differ from "
                             f"Twelve by more than "
                             f"{100 * _TOLERANCE:.2f}%. Worst: "
                             f"{names}.")}
        return {"status": "AGREE",
                "compared": len(diffs),
                "missing": missing,
                "worst": worst,
                "text": (f"Finnhub cross-check: AGREE — all "
                         f"{len(diffs)} signal-bar closes "
                         f"within {100 * _TOLERANCE:.2f}% of "
                         f"Twelve.")}
    except Exception:
        return {"status": "unavailable",
                "text": ("Finnhub verification unavailable "
                         "— the cross-check could not run.")}


def verdict_text(verdict):
    """The plain one-line stamp for a verdict dict (the
    fallback text when narration is not configured)."""
    if not isinstance(verdict, dict):
        return ""
    return str(verdict.get("text") or "")
