"""Lightweight persistent login / guest / optional OTP gate for New7 Streamlit app.

This version is designed for low RAM/CPU Streamlit use:
- CSS-only Galileo-style login page.
- No heavy JavaScript, no animation loop, no GPU canvas.
- Accounts are stored outside the code folder by default:
  ~/.new7_quant_app/auth.sqlite3
- Local/Desktop mode can create an account without showing OTP.
- Real Gmail OTP is optional for Streamlit Cloud and requires a Google App Password.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import smtplib
import sqlite3
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Tuple

import streamlit as st

UNIQUE = "20260612_galileo_auth_v2"


# -----------------------------------------------------------------------------
# Persistent storage
# -----------------------------------------------------------------------------
def _db_path() -> Path:
    env = os.environ.get("NEW7_AUTH_DB", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".new7_quant_app" / "auth.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=8)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE IF NOT EXISTS users ("
        "email TEXT PRIMARY KEY, "
        "password_hash TEXT NOT NULL, "
        "salt TEXT NOT NULL, "
        "created_at REAL NOT NULL)"
    )
    con.execute(
        "CREATE TABLE IF NOT EXISTS otps ("
        "email TEXT NOT NULL, "
        "code_hash TEXT NOT NULL, "
        "expires_at REAL NOT NULL, "
        "created_at REAL NOT NULL, "
        "consumed INTEGER DEFAULT 0)"
    )
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    return con


def _hash_password(password: str, salt: bytes | None = None) -> Tuple[str, str]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, 120_000)
    return base64.b64encode(digest).decode("ascii"), base64.b64encode(salt).decode("ascii")


def _verify_password(password: str, digest_b64: str, salt_b64: str) -> bool:
    try:
        calc, _ = _hash_password(password, base64.b64decode(salt_b64.encode("ascii")))
        return secrets.compare_digest(calc, digest_b64)
    except Exception:
        return False


def _set_setting(key: str, value: str) -> None:
    try:
        with _connect() as con:
            con.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
            con.commit()
    except Exception:
        pass


def _get_setting(key: str, default: str = "") -> str:
    try:
        with _connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return str(row[0]) if row else default
    except Exception:
        return default


def _create_user(email: str, password: str) -> None:
    digest, salt = _hash_password(password)
    with _connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO users(email,password_hash,salt,created_at) VALUES(?,?,?,?)",
            (email.lower().strip(), digest, salt, time.time()),
        )
        con.commit()


def _check_user(email: str, password: str) -> bool:
    try:
        with _connect() as con:
            row = con.execute(
                "SELECT password_hash,salt FROM users WHERE email=?",
                (email.lower().strip(),),
            ).fetchone()
        return bool(row and _verify_password(password, str(row[0]), str(row[1])))
    except Exception:
        return False


def _store_otp(email: str, code: str) -> None:
    digest = hashlib.sha256((email.lower().strip() + ":" + str(code).strip()).encode("utf-8")).hexdigest()
    with _connect() as con:
        con.execute("DELETE FROM otps WHERE email=?", (email.lower().strip(),))
        con.execute(
            "INSERT INTO otps(email,code_hash,expires_at,created_at,consumed) VALUES(?,?,?,?,0)",
            (email.lower().strip(), digest, time.time() + 10 * 60, time.time()),
        )
        con.commit()


def _verify_otp(email: str, code: str) -> bool:
    digest = hashlib.sha256((email.lower().strip() + ":" + str(code).strip()).encode("utf-8")).hexdigest()
    with _connect() as con:
        row = con.execute(
            "SELECT rowid,code_hash,expires_at,consumed FROM otps "
            "WHERE email=? ORDER BY created_at DESC LIMIT 1",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return False
        rowid, stored, expires, consumed = row
        ok = (
            not int(consumed or 0)
            and time.time() <= float(expires or 0)
            and secrets.compare_digest(str(stored), digest)
        )
        if ok:
            con.execute("UPDATE otps SET consumed=1 WHERE rowid=?", (rowid,))
            con.commit()
        return bool(ok)


def _login_success(email: str, guest: bool = False) -> None:
    """Set login session state. This fixes the previous NameError."""
    clean = str(email or "Guest").strip() or "Guest"
    st.session_state["new7_auth_logged_in"] = True
    st.session_state["new7_auth_guest"] = bool(guest)
    st.session_state["new7_auth_email"] = "Guest" if guest else clean.lower()
    st.session_state["new7_auth_login_ts"] = time.time()
    st.session_state["auth_mode"] = "guest" if guest else "account"
    # Every fresh login starts in Settings so the user can see connector
    # health, the H4 timeframe, symbol scope and run controls before Lunch.
    st.session_state["active_page"] = "Settings"
    st.session_state["tab_choice"] = "Settings"
    st.session_state["requested_page"] = "Settings"
    st.session_state["requested_subpage"] = ""
    st.session_state["first_settings_route_committed_20260706"] = False
    st.session_state.pop("guest_lunch_route_committed_20260704", None)


# -----------------------------------------------------------------------------
# OTP / SMTP helpers
# -----------------------------------------------------------------------------
def _smtp_cfg_from_env_or_db() -> Dict[str, str]:
    return {
        "host": os.environ.get("NEW7_SMTP_HOST") or _get_setting("smtp_host", "smtp.gmail.com"),
        "port": os.environ.get("NEW7_SMTP_PORT") or _get_setting("smtp_port", "587"),
        "email": os.environ.get("NEW7_SMTP_EMAIL") or _get_setting("smtp_email", ""),
        "password": os.environ.get("NEW7_SMTP_PASSWORD") or _get_setting("smtp_password", ""),
    }


def _otp_required() -> bool:
    """Set NEW7_REQUIRE_OTP=1 on Streamlit Cloud if you want mandatory Gmail OTP."""
    return str(os.environ.get("NEW7_REQUIRE_OTP", "0")).lower() in {"1", "true", "yes", "on"}


def _send_otp_email(to_email: str, code: str) -> Tuple[bool, str]:
    cfg = _smtp_cfg_from_env_or_db()
    sender = cfg.get("email", "").strip()
    password = cfg.get("password", "").strip()
    host = (cfg.get("host") or "smtp.gmail.com").strip()
    try:
        port = int(str(cfg.get("port") or 587).strip() or 587)
    except Exception:
        port = 587

    if not sender or not password:
        return False, "SMTP sender is not configured. Use local account creation or add SMTP settings."

    cleaned_pwd = password.replace(" ", "").strip()
    if "gmail.com" in sender.lower() and "gmail" in host.lower() and len(cleaned_pwd) != 16:
        return False, (
            "Gmail SMTP needs a 16-character Google App Password, not your normal Gmail password. "
            "Enable Google 2-Step Verification, create an App Password, then paste only that 16-character code."
        )

    try:
        msg = EmailMessage()
        msg["From"] = sender
        msg["To"] = to_email
        msg["Subject"] = "Your New7 Quant App OTP"
        msg.set_content(
            f"Your New7 Quant App verification code is: {code}\n\n"
            "This code expires in 10 minutes. If you did not request it, ignore this email."
        )
        with smtplib.SMTP(host, port, timeout=12) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(sender, cleaned_pwd if "gmail.com" in sender.lower() else password)
            smtp.send_message(msg)
        return True, f"OTP sent to {to_email}."
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail rejected SMTP login. Use a fresh 16-character Google App Password."
    except Exception as exc:
        return False, f"Email sending did not complete ({type(exc).__name__})."


# -----------------------------------------------------------------------------
# Lightweight Galileo UI
# -----------------------------------------------------------------------------
def _auth_css() -> None:
    st.markdown(
        """
        <style>
        html, body, [data-testid="stAppViewContainer"]{
            background:
              radial-gradient(circle at 15% 10%, rgba(168,85,247,.26), transparent 25%),
              radial-gradient(circle at 86% 14%, rgba(59,130,246,.24), transparent 22%),
              linear-gradient(135deg,#f7f2ff 0%,#e0f2fe 49%,#f8fbff 100%) !important;
        }
        .block-container{padding-top:1.0rem!important; max-width:1120px!important;}
        header[data-testid="stHeader"]{background:transparent!important;}
        .new7-auth-shell{max-width:1080px;margin:3vh auto 1.2rem auto;padding:16px;border-radius:34px;
            background:linear-gradient(135deg,rgba(124,58,237,.55),rgba(14,165,233,.22),rgba(255,255,255,.32));
            border:1px solid rgba(255,255,255,.58);box-shadow:0 26px 85px rgba(91,33,182,.19);}
        .new7-brand-panel{min-height:485px;border-radius:28px;padding:32px;color:white;position:relative;overflow:hidden;
            background:linear-gradient(145deg,rgba(109,40,217,.38),rgba(14,165,233,.22));
            border:1px solid rgba(255,255,255,.22);}
        .new7-brand-panel:before{content:"";position:absolute;top:-72px;left:-88px;width:270px;height:270px;border-radius:999px;background:rgba(255,255,255,.18);box-shadow:0 0 0 40px rgba(255,255,255,.07);}
        .new7-brand-panel:after{content:"";position:absolute;right:-52px;bottom:-58px;width:250px;height:250px;border-radius:999px;background:rgba(255,255,255,.12);}
        .new7-brand-inner{position:relative;z-index:1;}
        .new7-brand-badge{display:inline-flex;gap:9px;align-items:center;padding:9px 13px;border-radius:999px;background:rgba(255,255,255,.18);font-weight:900;backdrop-filter:blur(8px);}
        .new7-brand-title{font-size:3.2rem;line-height:.96;font-weight:950;letter-spacing:-.06em;margin:76px 0 14px;text-shadow:0 18px 40px rgba(0,0,0,.16);}
        .new7-brand-sub{max-width:455px;font-weight:760;line-height:1.55;color:rgba(255,255,255,.94);}
        .new7-feature-mini{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:28px;}
        .new7-feature-mini div{border-radius:18px;padding:12px;background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.22);font-weight:850;color:white;}
        .new7-card-title{font-size:1.55rem;font-weight:950;color:#312e81;letter-spacing:-.04em;margin:.25rem 0 .15rem;}
        .new7-card-sub{font-weight:740;color:#64748b;margin-bottom:12px;}
        .new7-help-card{border-radius:18px;padding:13px;margin:10px 0;background:linear-gradient(135deg,rgba(238,242,255,.95),rgba(240,253,250,.86));border:1px solid rgba(99,102,241,.18);font-weight:735;color:#334155;}
        .new7-auth-db{font-size:.80rem;color:#64748b;font-weight:700;margin-top:10px;word-break:break-all;}
        div[data-testid="stVerticalBlockBorderWrapper"]{border-radius:28px!important;border:1px solid rgba(255,255,255,.75)!important;background:rgba(255,255,255,.74)!important;box-shadow:0 22px 60px rgba(30,41,59,.12)!important;backdrop-filter:blur(16px)!important;}
        div[data-testid="stTabs"] button{border-radius:999px!important;font-weight:900!important;padding:.45rem .75rem!important;}
        div[data-testid="stTabs"] [aria-selected="true"]{background:linear-gradient(135deg,#7c3aed,#06b6d4)!important;color:white!important;}
        .stTextInput input{border-radius:16px!important;min-height:46px!important;background:rgba(255,255,255,.94)!important;border:1px solid rgba(129,140,248,.22)!important;}
        .stButton>button{border-radius:18px!important;min-height:48px!important;font-weight:950!important;border:0!important;background:linear-gradient(135deg,#7c3aed,#06b6d4)!important;color:white!important;box-shadow:0 14px 32px rgba(79,70,229,.22)!important;transition:transform .12s ease,box-shadow .12s ease!important;}
        .stButton>button:hover{transform:translateY(-1px);box-shadow:0 18px 38px rgba(79,70,229,.30)!important;}
        @media(max-width:820px){
          .block-container{padding-left:.58rem!important;padding-right:.58rem!important;}
          .new7-auth-shell{margin:.2rem auto;padding:10px;border-radius:24px;}
          .new7-brand-panel{min-height:250px;padding:20px;border-radius:22px;}
          .new7-brand-title{font-size:2.05rem;margin:34px 0 10px;}
          .new7-feature-mini{grid-template-columns:1fr;gap:8px;margin-top:16px;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _brand_panel() -> None:
    st.markdown(
        """
        <div class="new7-brand-panel"><div class="new7-brand-inner">
            <div class="new7-brand-badge">◐ New7 Galileo Quant</div>
            <div class="new7-brand-title">Top-30 Multi-Symbol<br/>Decision App</div>
            <div class="new7-brand-sub">Three-selector market loading, fast all-loaded regime ranking, PowerBI-style projection, research NLP, data mining priority and mobile-first copy output for your final-year CS project.</div>
            <div class="new7-feature-mini">
                <div>📊 Projection + actual/error</div>
                <div>🧠 Data Analysis / Mining / NLP</div>
                <div>⚡ All-loaded Super Quick</div>
                <div>📱 iPhone 11 Pro friendly</div>
            </div>
        </div></div>
        """,
        unsafe_allow_html=True,
    )


def _valid_email_password(email: str, password: str) -> Tuple[bool, str]:
    email = str(email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        return False, "Enter a valid email address."
    if len(str(password or "")) < 6:
        return False, "Password must be at least 6 characters."
    return True, "OK"


def _smtp_settings_expander() -> None:
    with st.expander("Open / Close — Optional Gmail SMTP setup for Streamlit Cloud", expanded=False):
        st.info(
            "Real Gmail OTP requires a 16-character Google App Password. "
            "Your normal Gmail password will not work. Local/Desktop account creation does not need this."
        )
        host = st.text_input("SMTP host", value=_get_setting("smtp_host", "smtp.gmail.com"), key=f"smtp_host_{UNIQUE}")
        port = st.text_input("SMTP port", value=_get_setting("smtp_port", "587"), key=f"smtp_port_{UNIQUE}")
        sender = st.text_input("Sender Gmail", value=_get_setting("smtp_email", ""), key=f"smtp_email_{UNIQUE}")
        sender_pwd = st.text_input("16-character Google App Password", type="password", value=_get_setting("smtp_password", ""), key=f"smtp_pwd_{UNIQUE}")
        if st.button("💾 Save SMTP settings", use_container_width=True, key=f"save_smtp_{UNIQUE}"):
            _set_setting("smtp_host", host.strip() or "smtp.gmail.com")
            _set_setting("smtp_port", port.strip() or "587")
            _set_setting("smtp_email", sender.strip())
            _set_setting("smtp_password", sender_pwd.strip())
            st.success("SMTP settings saved in persistent auth database.")


def _render_login_tab() -> None:
    email = st.text_input("Email", key=f"login_email_{UNIQUE}", placeholder="your@gmail.com")
    password = st.text_input("Password", type="password", key=f"login_pwd_{UNIQUE}")
    if st.button("🔐 Login", use_container_width=True, key=f"login_btn_{UNIQUE}"):
        if _check_user(email, password):
            _login_success(email, guest=False)
            st.success("Login successful.")
            st.rerun()
        else:
            st.error("Wrong email/password, or account not created yet.")


def _render_guest_tab() -> None:
    st.markdown('<div class="new7-help-card">Guest mode opens the dashboard immediately. No account is required.</div>', unsafe_allow_html=True)
    if st.button("🚀 Continue as Guest", use_container_width=True, key=f"guest_{UNIQUE}"):
        _login_success("Guest", guest=True)
        st.rerun()


def _render_create_account_tab() -> None:
    email = st.text_input("Gmail / Email", key=f"create_email_{UNIQUE}", placeholder="your@gmail.com")
    password = st.text_input("New password", type="password", key=f"create_pwd_{UNIQUE}")

    if not _otp_required():
        st.markdown(
            '<div class="new7-help-card">Local/Desktop mode: create account directly. No OTP is shown here. For Streamlit Cloud, set NEW7_REQUIRE_OTP=1 and configure Gmail App Password.</div>',
            unsafe_allow_html=True,
        )
        if st.button("✅ Create Account", use_container_width=True, key=f"create_local_{UNIQUE}"):
            ok, msg = _valid_email_password(email, password)
            if not ok:
                st.error(msg)
            else:
                _create_user(email, password)
                _login_success(email, guest=False)
                st.success("Account created and logged in.")
                st.rerun()
        _smtp_settings_expander()
        return

    st.markdown('<div class="new7-help-card">Cloud OTP mode is enabled. Send OTP to verify the account email.</div>', unsafe_allow_html=True)
    _smtp_settings_expander()
    c1, c2 = st.columns(2)
    if c1.button("📨 Send OTP", use_container_width=True, key=f"send_otp_{UNIQUE}"):
        ok, msg = _valid_email_password(email, password)
        if not ok:
            st.error(msg)
        else:
            code = f"{secrets.randbelow(900000) + 100000}"
            _store_otp(email, code)
            sent, send_msg = _send_otp_email(email, code)
            if sent:
                st.success(send_msg)
            else:
                st.warning(send_msg)
                st.caption("For local testing only, the OTP is available below. Do not use this mode for public deployment.")
                st.code(code, language="text")
    otp = c2.text_input("OTP code", key=f"otp_code_{UNIQUE}", max_chars=6)
    if st.button("✅ Verify OTP + Create Account", use_container_width=True, key=f"verify_create_{UNIQUE}"):
        if _verify_otp(email, otp):
            _create_user(email, password)
            _login_success(email, guest=False)
            st.success("Account created and logged in.")
            st.rerun()
        else:
            st.error("OTP invalid or expired. Send a new OTP.")


# -----------------------------------------------------------------------------
# Public render functions
# -----------------------------------------------------------------------------
def _hide_sidebar_on_auth_page() -> None:
    """Completely remove native/sidebar controls while the login gate is active.

    The app shell applies general sidebar styles before authentication.  This
    auth-page rule is intentionally injected afterwards so neither the native
    sidebar nor Streamlit's collapsed-sidebar button can flash on Login, Create
    Account, or Guest screens.  A successful login reruns the app without this
    rule, restoring the normal authenticated navigation.
    """
    st.markdown(
        """
        <style id="new7-auth-no-sidebar-20260617">
        section[data-testid="stSidebar"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"],
        [data-testid="stSidebarCollapsedControl"],
        [data-testid="collapsedControl"],
        button[data-testid="stSidebarCollapsedControl"],
        div[data-testid="stSidebarCollapsedControl"] {
            display:none !important; visibility:hidden !important;
            width:0 !important; min-width:0 !important; max-width:0 !important;
            height:0 !important; overflow:hidden !important; pointer-events:none !important;
        }
        [data-testid="stAppViewContainer"] > .main,
        [data-testid="stAppViewContainer"] .main {
            margin-left:0 !important; width:100% !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_auth_gate() -> bool:
    """Return True when the app should continue, False when login page is shown."""
    if st.session_state.get("new7_auth_logged_in"):
        st.session_state["new7_auth_page_active_20260617"] = False
        return True

    st.session_state["new7_auth_page_active_20260617"] = True
    _connect()
    _auth_css()
    _hide_sidebar_on_auth_page()

    st.markdown('<div class="new7-auth-shell">', unsafe_allow_html=True)
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        _brand_panel()
    with right:
        try:
            card = st.container(border=True)
        except TypeError:
            card = st.container()
        with card:
            st.markdown('<div class="new7-card-title">Welcome back</div>', unsafe_allow_html=True)
            st.markdown('<div class="new7-card-sub">Sign in, create account, or continue as Guest.</div>', unsafe_allow_html=True)
            login_tab, create_tab, guest_tab = st.tabs(["🔐 Login", "📝 Create Account", "🚀 Guest"])
            with login_tab:
                _render_login_tab()
            with create_tab:
                _render_create_account_tab()
            with guest_tab:
                _render_guest_tab()
            st.markdown(f'<div class="new7-auth-db">Account DB: {_db_path()}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    return False


def render_auth_status_sidebar() -> None:
    try:
        user = st.session_state.get("new7_auth_email", "Guest") or "Guest"
        with st.sidebar.expander("👤 Account", expanded=False):
            st.caption(f"Signed in: {user}")
            st.caption("Guest mode" if st.session_state.get("new7_auth_guest") else "Account mode")
            if st.button("🚪 Logout", use_container_width=True, key=f"sidebar_logout_{UNIQUE}"):
                st.session_state["new7_auth_logged_in"] = False
                st.session_state["new7_auth_guest"] = False
                st.session_state["new7_auth_email"] = ""
                st.session_state["auth_mode"] = ""
                st.rerun()
    except Exception:
        pass
