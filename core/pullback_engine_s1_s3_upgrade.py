"""Independent HMM-confirmed pullback models.

S1 statistical mean-reversion, S2 volatility cooling, and S3 trend exhaustion
share a small, dependency-free Gaussian HMM.  The HMM is fitted causally on
the supplied candle history (returns and absolute returns), so no future bars
are used.  S4/RAS are deliberately outside this module and remain unchanged.
"""
import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timezone

_SIGNAL_HISTORY = defaultdict(deque)


def _safe_close(df):
    if df is None or not hasattr(df, "columns") or "close" not in df:
        return None
    return np.asarray(df["close"], dtype=float)


def _hmm_regime(df, lookback=160):
    """Return causal 2-state Gaussian HMM probabilities and transition risk.

    State 0 is lower-volatility/trend continuation; state 1 is higher-volatility
    or reversal risk.  EM is intentionally lightweight and deterministic.
    """
    close = _safe_close(df)
    if close is None or len(close) < 35:
        return {"ready": False, "trend_prob": 0.0, "high_vol_prob": 0.0, "transition_prob": 1.0, "cooling": False}
    x = close[-lookback:]
    ret = np.diff(np.log(np.maximum(x, 1e-12)))
    if len(ret) < 30 or not np.isfinite(ret).all():
        return {"ready": False, "trend_prob": 0.0, "high_vol_prob": 0.0, "transition_prob": 1.0, "cooling": False}
    feat = np.column_stack((ret, np.abs(ret)))
    mu = np.array([feat[:len(feat)//2].mean(0), feat[len(feat)//2:].mean(0)], float)
    var = np.array([feat[:len(feat)//2].var(0), feat[len(feat)//2:].var(0)], float) + 1e-12
    # A few EM iterations with fixed, persistent transition prior.
    trans = np.array([[0.92, 0.08], [0.18, 0.82]], float)
    pi = np.array([0.65, 0.35], float)
    for _ in range(8):
        ll = np.empty((len(feat), 2))
        for s in range(2):
            ll[:, s] = -0.5 * np.sum(np.log(2*np.pi*var[s]) + (feat-mu[s])**2/var[s], axis=1)
        a = np.zeros_like(ll); a[0] = np.log(pi) + ll[0]
        for t in range(1, len(feat)):
            a[t] = ll[t] + np.logaddexp.reduce(a[t-1][:, None] + np.log(trans), axis=0)
        b = np.zeros_like(ll)
        for t in range(len(feat)-2, -1, -1):
            b[t] = np.logaddexp.reduce(np.log(trans) + ll[t+1][None, :] + b[t+1][None, :], axis=1)
        g = np.exp(a + b - np.logaddexp.reduce(a[-1]))
        g /= np.maximum(g.sum(1, keepdims=True), 1e-12)
        w = g.sum(0)
        mu = (g.T @ feat) / np.maximum(w[:, None], 1e-12)
        var = np.array([(g[:,s,None]*(feat-mu[s])**2).sum(0)/max(w[s],1e-12) for s in range(2)]) + 1e-12
    # State labels are normalized by volatility, not initialization.
    vol_order = np.argsort(var[:,1]); low, high = int(vol_order[0]), int(vol_order[1])
    last = float(g[-1, low]); high_p = float(g[-1, high])
    prev_high = float(g[-2, high])
    trans_risk = float(np.clip(high_p * trans[high, low] + last * trans[low, high], 0, 1))
    return {"ready": True, "trend_prob": last, "high_vol_prob": high_p, "transition_prob": trans_risk, "cooling": high_p < prev_high}


def _hourly_limit(symbol, signals, minimum=2, maximum=8):
    now = datetime.now(timezone.utc); allowed = []
    for sig in signals:
        label = sig.split()[-1] if sig else "UNKNOWN"; key = (symbol or "UNKNOWN", now.strftime("%Y-%m-%d-%H"), label)
        q = _SIGNAL_HISTORY[key]
        while q and (now-q[0]).total_seconds() > 3600: q.popleft()
        if len(q) < maximum: allowed.append(sig); q.append(now)
    return allowed


def statistical_pullback(df, higher_bias, window=50, z_threshold=1.5):
    close = _safe_close(df)
    if close is None or len(close) < window: return "WAIT"
    mean, std = np.mean(close[-window:]), np.std(close[-window:], ddof=1)
    if not np.isfinite(std) or std <= 0: return "WAIT"
    z = (close[-1]-mean)/std; h = _hmm_regime(df)
    if not h["ready"] or h["transition_prob"] > 0.45: return "WAIT"
    if higher_bias == "BUY" and z <= -z_threshold and h["trend_prob"] >= 0.55: return "BUY S1"
    if higher_bias == "SELL" and z >= z_threshold and h["trend_prob"] >= 0.55: return "SELL S1"
    return "WAIT"


def volatility_pullback(df, higher_bias, period=20, atr_mult=1.15):
    close = _safe_close(df)
    if close is None or len(close) < period + 8: return "WAIT"
    tr = np.abs(np.diff(close)); atr = np.convolve(tr, np.ones(period)/period, mode="valid")
    baseline = atr[-1] if len(atr) else 0; shock = close[-1]-close[-2]
    h = _hmm_regime(df)
    if baseline <= 0 or not h["ready"] or not h["cooling"] or h["transition_prob"] > 0.60: return "WAIT"
    if abs(shock)/baseline < atr_mult: return "WAIT"
    if higher_bias == "BUY" and shock < 0 and h["trend_prob"] >= 0.45: return "BUY S2"
    if higher_bias == "SELL" and shock > 0 and h["trend_prob"] >= 0.45: return "SELL S2"
    return "WAIT"


def momentum_pullback(df, higher_bias, fast=8, slow=21, recovery=3):
    close = _safe_close(df)
    if close is None or len(close) < slow + recovery + 5: return "WAIT"
    f = np.convolve(close, np.ones(fast)/fast, mode="valid"); s = np.convolve(close, np.ones(slow)/slow, mode="valid")
    n = min(len(f), len(s)); mom = f[-n:] - s[-n:]; h = _hmm_regime(df)
    if not h["ready"]: return "WAIT"
    weakening = h["transition_prob"] >= 0.30 or h["trend_prob"] < 0.55
    if higher_bias == "BUY" and weakening and mom[-1] > mom[-recovery] and mom[-recovery] <= 0: return "BUY S3"
    if higher_bias == "SELL" and weakening and mom[-1] < mom[-recovery] and mom[-recovery] >= 0: return "SELL S3"
    return "WAIT"

exhaustion_pullback = momentum_pullback



# ---------------------------------------------------------------------------
# Ranked static pullback scores (display layer)
# ---------------------------------------------------------------------------

def _clip_score(value):
    return int(np.clip(round(float(value)), 0, 100))


def ranked_pullback_scores(df, higher_bias):
    """Return static 0-100 pullback quality values.

    Unlike the execution signals above, these values never return WAIT.
    They are ranking scores used by Field 3 to show the strongest pullback
    opportunities while keeping the system pullback-focused.
    """
    close = _safe_close(df)
    if close is None or len(close) < 25:
        return {"S1": 0, "S2": 0, "S3": 0, "S4": 0, "S5": 0, "S6": 0}

    ret = np.diff(close)
    vol = np.std(ret[-20:]) or 1e-9
    mean = np.mean(close[-50:])
    z = abs((close[-1] - mean) / (np.std(close[-50:]) or 1e-9))
    h = _hmm_regime(df)

    direction_ok = 1
    if higher_bias in {"BUY", "SELL"}:
        direction_ok = 1

    # S1-S4 are the original pullback engines converted into continuous scores.
    # S5-S6 are additional middle-standard-bias pullback opportunity scores.
    s1 = 100 - z * 25                 # statistical pullback
    s2 = 100 - abs(ret[-1]) / vol * 20 # volatility pullback
    s3 = h["trend_prob"] * 100         # exhaustion / momentum recovery
    s4 = (1 - h["transition_prob"]) * 100  # RAS / regime stability
    middle_bias = h["trend_prob"] * (1 - h["transition_prob"]) * 100
    s5 = (middle_bias * .60) + (100 - min(100, abs(np.mean(ret[-5:])) / vol * 25)) * .40
    s6 = (s1 * .25 + s2 * .20 + s3 * .20 + s4 * .15 + middle_bias * .20)

    return {
        "S1": _clip_score(s1 * direction_ok),
        "S2": _clip_score(s2),
        "S3": _clip_score(s3),
        "S4": _clip_score(s4),
        "S5": _clip_score(s5),
        "S6": _clip_score(s6),
    }


def ranked_entry_priority(scores, minimum=2, maximum=8):
    """Return top ranked pullback strategies meeting the 2-8 rule."""
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    active = [x for x in ranked if x[1] > 0]
    return active[:max(minimum, min(maximum, len(active)))]


def run_pullback_models(df, higher_bias, symbol="UNKNOWN"):
    results = [fn(df, higher_bias) for fn in (statistical_pullback, volatility_pullback, exhaustion_pullback)]
    results = _hourly_limit(symbol, [x for x in results if x != "WAIT"])
    return " | ".join(results) if results else "WAIT"
