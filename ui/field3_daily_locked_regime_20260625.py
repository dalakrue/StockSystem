"""Field 3 renderer for broker-day locked 120/600-candle regimes."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping


def render_daily_locked_regime(state: MutableMapping[str, Any], canonical: Mapping[str, Any]) -> None:
    import streamlit as st

    from core.daily_locked_regime_20260625 import ensure_daily_locked_regime

    locked = ensure_daily_locked_regime(state, canonical)
    st.markdown("#### Broker-Day Locked Middle/Higher Regime — 00:00 Review")
    if not locked.get("ok"):
        st.warning(str(locked.get("reason") or "Daily regime lock is unavailable."))
        return
    middle = locked.get("middle") if isinstance(locked.get("middle"), Mapping) else {}
    higher = locked.get("higher") if isinstance(locked.get("higher"), Mapping) else {}
    first = st.columns(4)
    first[0].metric("Middle 5-Day Regime", str(middle.get("regime") or "UNKNOWN"))
    first[1].metric("Middle Reliability", f"{float(middle.get('reliability') or 0):.1f}%", f"{int(middle.get('sample_count') or 0)}/120 H1")
    first[2].metric("Higher 25-Day Regime", str(higher.get("regime") or "UNKNOWN"))
    first[3].metric("Higher Reliability", f"{float(higher.get('reliability') or 0):.1f}%", f"{int(higher.get('sample_count') or 0)}/600 H1")
    second = st.columns(4)
    second[0].metric("Middle Regime Start", str(middle.get("regime_start_broker_time") or "—")[:19])
    second[1].metric("Higher Regime Start", str(higher.get("regime_start_broker_time") or "—")[:19])
    second[2].metric("Next 00:00 Review", str(locked.get("next_review_broker_time") or "—")[:19])
    second[3].metric("Hours Until Review", f"{float(locked.get('hours_until_next_review') or 0):.2f} h")
    third = st.columns(4)
    third[0].metric("Middle Transition Risk", f"{float(middle.get('transition_risk') or 0):.1f}%")
    third[1].metric("Middle Alpha / Delta", f"{float(middle.get('alpha') or 0):.2f} / {float(middle.get('delta') or 0):.2f}")
    third[2].metric("Higher Transition Risk", f"{float(higher.get('transition_risk') or 0):.1f}%")
    third[3].metric("Higher Alpha / Delta", f"{float(higher.get('alpha') or 0):.2f} / {float(higher.get('delta') or 0):.2f}")
    if locked.get("intraday_change_detected"):
        st.info(
            "An intraday candidate differs from the locked Middle/Higher regime. It is shown only as "
            "diagnostic evidence and will not replace the lock before the next broker 00:00 review."
        )
    st.caption(
        "Middle uses the last 120 completed H1 candles; Higher uses the last 600 completed H1 candles. "
        "Both are sampled at broker-day start and remain stable for the next 24 hours. Lower remains rolling. "
        "This is an additive display lock; protected production regime and trading decisions are unchanged."
    )


__all__ = ["render_daily_locked_regime"]
