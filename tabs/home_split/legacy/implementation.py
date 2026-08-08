"""Compatibility loader for split Home module.

Original source was divided into small chunk modules for future CSS/UIUX
and feature upgrades while keeping runtime behavior identical.
"""

from importlib import import_module as _import_module

_PART_MODULES = ['part_01', 'part_02', 'part_03', 'part_04', 'part_05', 'part_06']


def _load_original_source():
    chunks = []
    base = __package__ + ".implementation_parts"
    for name in _PART_MODULES:
        chunks.append(_import_module(base + "." + name).PART)
    return "".join(chunks)


_ORIGINAL_SOURCE = _load_original_source()
exec(compile(_ORIGINAL_SOURCE, __file__, "exec"), globals(), globals())

try:
    __all__
except NameError:
    __all__ = [name for name in globals() if not (name.startswith("__") and name.endswith("__"))]

# ==========================================================
# V25 SAFE COPY OVERRIDE — include Metric, exclude position/history rows
# ==========================================================
try:
    _build_home_copy_payload_v24_original = _build_home_copy_payload
except Exception:
    _build_home_copy_payload_v24_original = None


def _build_home_copy_payload():
    """Build a clean GPT copy export without raw positions/history.

    V25 rules:
    - Include Home quant, Doo deep metrics, and Metric inner-tab export.
    - Exclude raw open positions, deal history, order history, and history tables.
    - Account summary keeps only top-level balance/equity/margin fields.
    """
    df = st.session_state.get("last_df")
    account = st.session_state.get("account_snapshot", {}) or {}
    q = {}
    market = {}
    market_quality = {}
    deep_rows = []
    deep_full = {}

    try:
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            q = _safe_quant_stack(df)
            market, _frame = _calc_market_analytics(df)
            market_quality = {
                "rows_used": len(_frame) if isinstance(_frame, pd.DataFrame) else 0,
                "fat_tail_available": bool((market or {}).get("fat_tail_available", False)),
                "fat_tail_note": (market or {}).get("fat_tail_note", ""),
            }
    except Exception as exc:
        market_quality = {"error": str(exc)}

    try:
        deep = st.session_state.get("doo_deep_results", {}) or {}
        if not deep:
            deep = _build_deep_copy_blocks_from_shared()
        for key, res in (deep or {}).items():
            m = (res or {}).get("market", {}) or {}
            safe_res = dict(res or {})
            for bad_key in ["positions", "position_rows", "history", "deals", "orders", "account_history", "risk_history"]:
                safe_res.pop(bad_key, None)
            deep_full[str(key)] = _json_safe(safe_res)
            deep_rows.append({
                "block": (res or {}).get("label", key),
                "source": (res or {}).get("source", "-"),
                "rows": (res or {}).get("rows", (res or {}).get("rows_used", 0)),
                "partial": (res or {}).get("partial", False),
                "direction": m.get("trend_direction", "WAIT"),
                "regime": m.get("regime", "NO DATA"),
                "dve_pct": m.get("directional_efficiency"),
                "rising_eff_pct": m.get("efficiency_rising"),
                "falling_eff_pct": m.get("efficiency_falling"),
                "fat_tail_z": m.get("fat_tail_z") if m.get("fat_tail_available", False) else "N/A",
                "last_close_delta_pct": m.get("last_close_delta_pct"),
                "effective_return_pct": m.get("effective_return_pct"),
                "trust_pct": m.get("trust"),
            })
    except Exception as exc:
        deep_rows.append({"error": str(exc)})

    tail_rows = []
    try:
        if df is not None and isinstance(df, pd.DataFrame) and not df.empty:
            cols = [c for c in ["time", "open", "high", "low", "close", "volume"] if c in df.columns]
            if cols:
                tail_rows = df[cols].tail(30).copy().to_dict(orient="records")
    except Exception:
        tail_rows = []

    account_safe = {}
    try:
        blocked = {"positions", "deals", "orders", "history", "position_rows", "account_history", "risk_history"}
        account_safe = {str(k): v for k, v in (account or {}).items() if str(k) not in blocked and not isinstance(v, (list, tuple, pd.DataFrame))}
    except Exception:
        account_safe = {}

    payload = {
        "export_time": str(pd.Timestamp.now()),
        "symbol": st.session_state.get("symbol", "XAUUSD"),
        "source": st.session_state.get("source", "DISCONNECTED"),
        "timeframe": st.session_state.get("timeframe", "M1"),
        "connector_mode": st.session_state.get("connector_mode", "fallback"),
        "rows": len(df) if isinstance(df, pd.DataFrame) else 0,
        "home_12h_quant_stack": q,
        "advanced_market_analytics": market,
        "market_data_quality": market_quality,
        "account_summary_no_position_or_history_rows": _json_safe(account_safe),
        "doo_prime_deep_summary": deep_rows,
        "doo_prime_deep_full_metrics": deep_full,
        "metric_inner_tab_export": _json_safe(st.session_state.get("eurusd_h1_matrix_export", {})),
        "reversal_early_warning_engine": _json_safe(st.session_state.get("last_reversal_engine", {})),
        "latest_candles_tail_30": tail_rows,
        "copy_rules": "Metric data included. Raw open positions, order rows, deal rows, and account/risk history rows excluded.",
        "instruction_for_gpt": "Use this data to analyze current symbol risk, trend regime, fat-tail shock risk, DVE, margin danger, Metric score, and 8H/12H hold bias. Do not treat N/A as zero.",
    }
    text = "HOME + METRIC DATA EXPORT FOR GPT\n" + "=" * 40 + "\n"
    try:
        import json
        text += json.dumps(_json_safe(payload), indent=2, ensure_ascii=False, default=str)
    except Exception:
        text += str(_json_safe(payload))
    return text
