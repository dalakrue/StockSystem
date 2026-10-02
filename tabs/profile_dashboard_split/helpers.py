import streamlit as st
import pandas as pd

from core.database import append_csv, read_csv

try:
    from core.common import log_event
except Exception:
    log_event = None


def _now():
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_df(name):
    """Read an app CSV table safely. Returns an empty DataFrame on any problem."""
    try:
        df = read_csv(name)
        if df is None or not isinstance(df, pd.DataFrame):
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def safe_append(name, row):
    """Append one row safely to the app data folder."""
    try:
        append_csv(name, row)
        return True
    except Exception as e:
        st.warning(f"Could not save {name}: {e}")
        return False


def safe_log(msg):
    try:
        if log_event:
            log_event(msg)
            return
    except Exception:
        pass
    st.session_state.setdefault("activity_log", [])
    if not isinstance(st.session_state.activity_log, list):
        st.session_state.activity_log = []
    st.session_state.activity_log.insert(0, {"time": _now(), "event": str(msg)})
    st.session_state.activity_log = st.session_state.activity_log[:500]


def init_profile_state():
    defaults = {
        "notes": [],
        "activity_log": [],
        "profile_name": "Quant Trader",
        "profile_goal": "12H Hold Strategy",
        "profile_style": "12H Hold",
        "risk_mode": "Balanced",
        "profile_max_risk_pct": 1.0,
        "profile_max_positions": 20,
        "profile_min_margin_level": 150.0,
        "profile_trade_journal_auto_save": True,
        "profile_daily_max_loss": 0.0,
        "profile_today_exit_rule": "Do not close one full side unless margin and directional confirmation agree.",
        "profile_today_invalidation": "If margin level approaches emergency zone, reduce paired BUY+SELL exposure first.",
        "setting_auto_entry": True,
        "setting_exit_alerts": True,
        "setting_risk_active": True,
        "phone_mode": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if not isinstance(st.session_state.get("notes"), list):
        st.session_state.notes = []
    if not isinstance(st.session_state.get("activity_log"), list):
        st.session_state.activity_log = []


def download_button(df, label, filename):
    # All CSV downloads are centralized in the sidebar Download Center to avoid
    # duplicate download buttons across Profile/History/Data Health.
    if isinstance(df, pd.DataFrame) and not df.empty:
        st.caption(f"⬇️ `{filename}` export is available from the sidebar Download Center.")


def filter_df(df, search_text=""):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    out = df.copy()
    text = str(search_text or "").strip().lower()
    if text:
        mask = out.astype(str).apply(lambda col: col.str.lower().str.contains(text, na=False)).any(axis=1)
        out = out[mask]
    return out


def data_health_box(name, df):
    rows = 0 if df is None else len(df)
    cols = 0 if df is None or getattr(df, "empty", True) else len(df.columns)
    if rows == 0:
        status, delta = "EMPTY", "Needs data"
    elif rows < 20:
        status, delta = "LOW DATA", "Collect more"
    else:
        status, delta = "READY", "OK"
    st.metric(name, f"{rows:,} rows", f"{cols} cols / {status} / {delta}")


def get_live_df():
    df = st.session_state.get("last_df")
    return df if isinstance(df, pd.DataFrame) else pd.DataFrame()


def safe_number(value, default=0.0):
    try:
        value = float(value)
        if pd.isna(value):
            return default if default is None else float(default)
        return value
    except Exception:
        return default if default is None else float(default)


def safe_dataframe_summary(df):
    """Return compact dataframe health metrics for Profile dashboards."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return {"rows": 0, "cols": 0, "missing_pct": 0.0, "duplicate_rows": 0, "latest_time": "N/A"}
    out = df.copy()
    rows, cols = out.shape
    missing_pct = float(out.isna().mean().mean() * 100) if rows and cols else 0.0
    duplicate_rows = int(out.duplicated().sum()) if rows else 0
    latest_time = "N/A"
    for col in ["time", "timestamp", "datetime", "date", "Time", "Datetime"]:
        if col in out.columns and not out[col].dropna().empty:
            latest_time = str(out[col].dropna().iloc[-1])
            break
    return {"rows": int(rows), "cols": int(cols), "missing_pct": missing_pct, "duplicate_rows": duplicate_rows, "latest_time": latest_time}


def compact_status(value, good=True):
    icon = "✅" if good else "⚠️"
    return f"{icon} {value}"

# -----------------------------------------------------------------------------
# Profile Pro Plus helpers - additive, backward compatible.
# -----------------------------------------------------------------------------
def profile_snapshot_dict():
    """Build one safe profile snapshot from session state and saved app data."""
    live = get_live_df()
    account = st.session_state.get("account_snapshot", {})
    if not isinstance(account, dict):
        account = {}
    positions = st.session_state.get("doo_positions", [])
    if not isinstance(positions, list):
        positions = []
    summary = safe_dataframe_summary(live)
    return {
        "time": _now(),
        "profile_name": st.session_state.get("profile_name", "Quant Trader"),
        "profile_goal": st.session_state.get("profile_goal", "12H Hold Strategy"),
        "risk_mode": st.session_state.get("risk_mode", "Balanced"),
        "symbol": st.session_state.get("symbol", "XAUUSD"),
        "timeframe": st.session_state.get("timeframe", "M1"),
        "source": st.session_state.get("source", "DISCONNECTED"),
        "connected": bool(st.session_state.get("connected", False)),
        "live_rows": summary.get("rows", 0),
        "live_cols": summary.get("cols", 0),
        "missing_pct": summary.get("missing_pct", 0.0),
        "duplicate_rows": summary.get("duplicate_rows", 0),
        "latest_time": summary.get("latest_time", "N/A"),
        "equity": safe_number(account.get("equity"), 0),
        "balance": safe_number(account.get("balance"), 0),
        "margin_level": safe_number(account.get("margin_level") or account.get("margin_level_pct") or account.get("margin_level_percent"), 0),
        "floating_pl": safe_number(account.get("profit") or account.get("floating_pl") or account.get("floating"), 0),
        "position_count": len(positions),
        "max_positions": int(safe_number(st.session_state.get("profile_max_positions", 20), 20)),
        "min_margin_level": safe_number(st.session_state.get("profile_min_margin_level", 150.0), 150.0),
    }


def profile_readiness_score(snapshot=None):
    """Return a transparent score and rule list; no trading action is executed."""
    s = snapshot or profile_snapshot_dict()
    score = 100
    rules = []

    def add(label, ok, penalty, detail):
        nonlocal score
        if not ok:
            score -= penalty
        rules.append({"check": label, "status": "PASS" if ok else "WARN", "penalty": 0 if ok else penalty, "detail": detail})

    add("Market data loaded", int(s.get("live_rows", 0)) > 0, 25, f"Rows: {int(s.get('live_rows', 0)):,}")
    add("Connected source available", str(s.get("source", "DISCONNECTED")) != "DISCONNECTED", 10, f"Source: {s.get('source')}")
    margin = safe_number(s.get("margin_level"), 0)
    min_margin = safe_number(s.get("min_margin_level"), 150)
    add("Margin above profile minimum", margin >= min_margin if margin else False, 30, f"Margin {margin:.2f}% / minimum {min_margin:.2f}%")
    pos = int(safe_number(s.get("position_count"), 0))
    max_pos = int(safe_number(s.get("max_positions"), 20))
    add("Position count inside plan", pos <= max_pos, 15, f"Positions {pos} / max {max_pos}")
    missing = safe_number(s.get("missing_pct"), 0)
    add("Data missing values acceptable", missing <= 5.0, 10, f"Missing {missing:.2f}%")
    dup = int(safe_number(s.get("duplicate_rows"), 0))
    add("No duplicate live rows", dup == 0, 10, f"Duplicate rows: {dup:,}")
    score = max(0, min(100, int(round(score))))
    state = "READY" if score >= 80 else "CAUTION" if score >= 55 else "DANGER"
    return score, state, rules


def summarize_numeric_table(df):
    """Small numeric summary for Profile performance/history panels."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return pd.DataFrame()
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        return pd.DataFrame()
    out = numeric.describe().T.reset_index().rename(columns={"index": "metric"})
    keep = [c for c in ["metric", "count", "mean", "std", "min", "25%", "50%", "75%", "max"] if c in out.columns]
    return out[keep]
