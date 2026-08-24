"""Compact provider/quota health panel; never exposes credentials."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, MutableMapping
import sqlite3

import streamlit as st

from core.data.candle_repository import CandleRepository
from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema
from core.runtime_selection_20260705 import latest_completed_candle, normalize_symbols, normalize_timeframe


def _rows(db_path: Path, table: str) -> list[dict[str, Any]]:
    try:
        with sqlite3.connect(str(db_path), timeout=5) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(f"SELECT * FROM {table}").fetchall()]
    except Exception:
        return []


def render_provider_health_panel(state: MutableMapping[str, Any] | Mapping[str, Any] | None = None) -> None:
    state = state if isinstance(state, Mapping) else st.session_state
    migrate_deployment_schema(DEFAULT_DB_PATH)
    from core.twelve_data_key_pool import TwelveDataKeyPool
    key_pool_status = TwelveDataKeyPool.from_state(state).status_snapshot()
    connections = {row.get("provider"): row for row in _rows(DEFAULT_DB_PATH, "api_connection_state")}
    health = {row.get("provider"): row for row in _rows(DEFAULT_DB_PATH, "provider_health")}
    selected = normalize_symbols(state.get("multi_symbol_selected_20260701"), default_top10=True)
    timeframe = normalize_timeframe(state.get("timeframe") or "H1")
    expected = latest_completed_candle(timeframe=timeframe)
    repository = CandleRepository(DEFAULT_DB_PATH)
    current = 0
    needing = 0
    for symbol in selected:
        if repository.missing_from(symbol, timeframe, expected):
            needing += 1
        else:
            current += 1

    with st.expander("Open / Close — Provider Health, Quota and Canonical Run", expanded=False):
        st.caption("Provider priority: validated local cache → Twelve Data key pool → Finnhub candle fallback → last-known valid cache. Each Twelve key has its own minute counter/cooldown. Credentials are never displayed.")
        key1 = key_pool_status.get("TWELVE_KEY_1", {})
        key2 = key_pool_status.get("TWELVE_KEY_2", {})
        cards = st.columns(4)
        cards[0].metric("Twelve Key 1", "CONNECTED" if key1.get("connected") else ("CONFIGURED" if key1.get("configured") else "NOT CONFIGURED"))
        cards[1].metric("Key 1 Remaining", str(key1.get("remaining_credits", 0)))
        cards[2].metric("Twelve Key 2", "CONNECTED" if key2.get("connected") else ("CONFIGURED" if key2.get("configured") else "NOT CONFIGURED"))
        cards[3].metric("Key 2 Remaining", str(key2.get("remaining_credits", 0)))
        cards = st.columns(4)
        cards[0].metric("Preferred Provider", "TWELVE_DATA_KEY_POOL")
        cards[1].metric("Actual Candle Provider", str(state.get("actual_market_provider_used_20260708") or "NOT LOADED"))
        cards[2].metric("Finnhub Fallback", str(health.get("FINNHUB", {}).get("status") or "NOT CHECKED"))
        cards[3].metric("Fallback Reason", str(state.get("market_provider_fallback_reason_20260708") or "—")[:28])
        cards = st.columns(4)
        cards[0].metric("Local Candles", repository.count())
        cards[1].metric("Symbols Current", current)
        cards[2].metric("Need Updates", needing)
        cards[3].metric("Timeframe", timeframe)
        cards = st.columns(4)
        cards[0].metric("Latest Run ID", str(state.get("canonical_run_id_20260617") or state.get("quota_safe_run_id_20260705") or "—")[:24])
        cards[1].metric("Latest Broker Candle", str(state.get("latest_completed_candle_for_run_20260705") or expected.isoformat())[:22])
        news = state.get("shared_news_sentiment_20260705") if isinstance(state.get("shared_news_sentiment_20260705"), Mapping) else {}
        cards[2].metric("News / GDELT", str(news.get("status") or "NOT CHECKED"))
        sentiment = news.get("sentiment") if isinstance(news.get("sentiment"), Mapping) else {}
        cards[3].metric("NLP Model", "LOCAL READY" if sentiment else "CACHE / WAITING")
        try:
            from core.data.symbol_level_provider_registry_20260708 import SymbolLevelProviderRegistry
            board = SymbolLevelProviderRegistry(DEFAULT_DB_PATH).provider_board()
            if board:
                st.markdown("#### Symbol-Level Provider Health Board")
                st.dataframe(board, use_container_width=True, hide_index=True, height=220)
        except Exception as registry_exc:
            st.caption(f"Symbol-level health board unavailable: {type(registry_exc).__name__}")
        limited = [alias for alias, info in key_pool_status.items() if info.get("cooldown_reset_time")]
        if limited:
            st.warning("Twelve Data key cooldown active: " + ", ".join(limited))
        elif needing:
            st.info(f"{needing} symbol(s) need the {timeframe} completed candle. The next Settings run will use the Twelve key pool safely and then fallback if necessary.")


__all__ = ["render_provider_health_panel"]
