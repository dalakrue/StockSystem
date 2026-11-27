"""GitHub save-back of walk-ledger state files.

Streamlit Cloud's disk is ephemeral: every restart / redeploy wipes
whatever the app saved locally, including the cycles' walked state
under ``data/walk_ledgers_new8/<system>.json``. That state IS the
systems' memory (processed checks, fill state, delivered picks), so
losing it makes the app restart from an old repo snapshot.

This module closes the loop: after a live evaluation step (the hook
sits in ``core.signal_mode._evaluate_and_select_for``), it scans the
walk-ledger directory and pushes every file whose content changed
back into the GitHub repo via the Contents API — free and automatic,
so the repo copy is never more than one check behind the app's live
memory.

Dormant by default: it does nothing unless a token is configured in
the app's Streamlit secrets, either as::

    [github_saveback]
    token = "..."

or as a top-level ``GITHUB_TOKEN`` secret. The token must be a
fine-grained personal access token with Contents read/write on this
repo only.

Safety contract (the signal path depends on it):
- NEVER raises. Every failure is swallowed and reported as False.
- One attempt per request, short timeouts, no retries. A failed push
  is not marked as pushed, so the next evaluation tries again.
- The HTTP work runs on daemon threads; callers never wait on the
  network. Only the (tiny) local file reads + hashing are synchronous.
- Scope: ``data/walk_ledgers_new8/*.json`` only — never the candle
  cache, never the canonical feed.

History extension (user order 2026-11-27): the app's recorded
HISTORY — the precheck day log (``data/precheck_day_log.json``,
behind "Today's precheck signals") and the signal evaluation
history DB (``data/signal_eval_history.sqlite3``, behind the
"Last 24 hours" tables and the month signals history) — is
persisted and restored the same way: pushed when it changes
(saveback_history_files, called from the history write points),
and restored on boot when the local copy is missing
(restore_history_files_async, called once from the Field 3
render), so after any code push / redeploy the history shows
exactly as before. Still never the candle cache, never the
canonical feed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
import urllib.error
import urllib.request

_OWNER = "dalakrue"
_REPO = "StockSystem"
_BRANCH = "main"
_API_ROOT = "https://api.github.com"
_LEDGER_DIR_PARTS = ("data", "walk_ledgers_new8")
_TIMEOUT_S = 8.0

_LOCK = threading.Lock()
# repo-relative path -> sha256 hex of the content the repo is known to
# hold because of us (pushed, or confirmed identical on a GET).
_PUSHED: dict[str, str] = {}
# repo-relative paths with a push thread currently running.
_INFLIGHT: set[str] = set()


def _repo_root() -> str:
    """App/repo root: this file lives at <root>/core/data/."""
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def _secret_token():
    """Save-back token from Streamlit secrets, else None.

    Returns None outside Streamlit, with no secrets configured, or on
    any secrets error — save-back is simply off in all those cases."""
    try:
        import streamlit as st
        secrets = st.secrets
    except Exception:
        return None
    try:
        section = secrets["github_saveback"]
        if isinstance(section, dict):
            tok = section.get("token")
            if tok and str(tok).strip():
                return str(tok).strip()
        elif isinstance(section, str) and section.strip():
            return section.strip()
    except Exception:
        pass
    try:
        tok = secrets["GITHUB_TOKEN"]
        if tok and str(tok).strip():
            return str(tok).strip()
    except Exception:
        pass
    return None


def _http_json(method, url, token, payload=None):
    """One HTTP attempt against the GitHub API.

    Returns (status, parsed_json_or_None) for every HTTP response,
    including error statuses. Raises only on transport failure;
    callers swallow. Kept as a module-level function so tests can
    monkeypatch the whole HTTP layer here."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "stocksystem-saveback/1.0",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
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


def _contents_url(repo_rel):
    return f"{_API_ROOT}/repos/{_OWNER}/{_REPO}/contents/{repo_rel}"


def _describe(repo_rel, raw):
    """(cycle_name, latest_slot_or_None) for the commit message.

    Best effort from the state JSON itself: the cycles' ``_Form``
    files carry ``processed`` (walked check stamps, in order);
    ``MergedWalkState`` files carry pick rows with ``check`` fields.
    Never raises."""
    name = os.path.basename(repo_rel)
    if name.endswith(".json"):
        name = name[:-len(".json")]
    latest = None
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = None
    if isinstance(data, dict):
        if data.get("system"):
            name = str(data["system"])
        proc = data.get("processed")
        if isinstance(proc, list) and proc:
            latest = str(proc[-1])
        else:
            checks = []
            for key in ("delivered", "accepted", "incumbent_picks"):
                rows = data.get(key)
                if isinstance(rows, list):
                    for row in rows:
                        if isinstance(row, dict) and row.get("check"):
                            checks.append(str(row["check"]))
            if checks:
                latest = max(checks)
    return name, latest


def _push_bytes(repo_rel, raw, token):
    """Make the repo hold exactly ``raw`` at ``repo_rel``.

    GETs the current repo copy first: if it is already identical,
    records that and returns True without a commit (keeps cold boots
    from creating spurious commits). Otherwise PUTs with the current
    blob sha (omitted when the file does not exist yet). Returns True
    iff the repo now holds ``raw``; updates _PUSHED only then. Never
    raises."""
    digest = hashlib.sha256(raw).hexdigest()
    try:
        status, meta = _http_json(
            "GET", _contents_url(repo_rel) + f"?ref={_BRANCH}", token)
        sha = None
        if status == 200 and isinstance(meta, dict):
            sha = meta.get("sha")
            content = meta.get("content")
            if isinstance(content, str) \
                    and meta.get("encoding") == "base64":
                try:
                    remote = base64.b64decode(content)
                except Exception:
                    remote = None
                if remote is not None and \
                        hashlib.sha256(remote).hexdigest() == digest:
                    with _LOCK:
                        _PUSHED[repo_rel] = digest
                    return True
        elif status != 404:
            # 401/403/5xx/... — do not PUT blind; the next
            # evaluation retries the whole thing.
            return False
        name, latest = _describe(repo_rel, raw)
        message = f"save-back: {name} state"
        if latest:
            message += f" @ {latest}"
        payload = {
            "message": message,
            "content": base64.b64encode(raw).decode("ascii"),
            "branch": _BRANCH,
        }
        if sha:
            payload["sha"] = sha
        status, _ = _http_json("PUT", _contents_url(repo_rel),
                               token, payload)
        if status in (200, 201):
            with _LOCK:
                _PUSHED[repo_rel] = digest
            return True
        return False
    except Exception:
        return False


def saveback_file(local_path, repo_rel=None, token=None):
    """Synchronously push one state file if its content changed
    since the last successful push in this process (or since a GET
    confirmed the repo copy identical). Returns True iff the repo
    holds the current content because of this call or already did.
    Never raises."""
    try:
        if token is None:
            token = _secret_token()
        if not token:
            return False
        with open(local_path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return False
        if repo_rel is None:
            repo_rel = os.path.relpath(
                os.path.abspath(local_path),
                _repo_root()).replace(os.sep, "/")
        digest = hashlib.sha256(raw).hexdigest()
        with _LOCK:
            if _PUSHED.get(repo_rel) == digest:
                return False
        return _push_bytes(repo_rel, raw, token)
    except Exception:
        return False


def _push_thread(repo_rel, raw, token):
    try:
        _push_bytes(repo_rel, raw, token)
    except Exception:
        pass
    finally:
        with _LOCK:
            _INFLIGHT.discard(repo_rel)


def saveback_walk_ledgers(root=None, token=None):
    """Scan the walk-ledger dir and push every changed state file.

    The scan (listdir + read + sha256 of small JSONs) is synchronous
    and cheap; each actual push runs on a daemon thread so the signal
    path never waits on the network. Returns the repo-relative paths
    scheduled for pushing (possibly empty). Never raises."""
    scheduled = []
    try:
        if token is None:
            token = _secret_token()
        if not token:
            return scheduled
        base = root or _repo_root()
        ledger_dir = os.path.join(base, *_LEDGER_DIR_PARTS)
        if not os.path.isdir(ledger_dir):
            return scheduled
        for fname in sorted(os.listdir(ledger_dir)):
            if not fname.endswith(".json"):
                continue
            local = os.path.join(ledger_dir, fname)
            repo_rel = "/".join(_LEDGER_DIR_PARTS + (fname,))
            try:
                with open(local, "rb") as fh:
                    raw = fh.read()
            except Exception:
                continue
            if not raw:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            with _LOCK:
                if _PUSHED.get(repo_rel) == digest \
                        or repo_rel in _INFLIGHT:
                    continue
                _INFLIGHT.add(repo_rel)
            thread = threading.Thread(
                target=_push_thread, args=(repo_rel, raw, token),
                daemon=True, name=f"saveback-{fname}")
            thread.start()
            scheduled.append(repo_rel)
    except Exception:
        pass
    return scheduled


# ----------------------------------------------------------------
# History save-back (user order 2026-11-27) — see the module
# docstring. Same safety contract as the ledger path above.
_HISTORY_RELS = (
    "data/precheck_day_log.json",
    "data/signal_eval_history.sqlite3",
)
_RESTORE_STARTED = False


def saveback_history_files(root=None, token=None):
    """Push the history files whose content changed, on daemon
    threads like saveback_walk_ledgers. Returns the
    repo-relative paths scheduled (possibly empty). Never
    raises."""
    scheduled = []
    try:
        if token is None:
            token = _secret_token()
        if not token:
            return scheduled
        base = root or _repo_root()
        for repo_rel in _HISTORY_RELS:
            local = os.path.join(base, *repo_rel.split("/"))
            try:
                with open(local, "rb") as fh:
                    raw = fh.read()
            except Exception:
                continue
            if not raw:
                continue
            digest = hashlib.sha256(raw).hexdigest()
            with _LOCK:
                if _PUSHED.get(repo_rel) == digest \
                        or repo_rel in _INFLIGHT:
                    continue
                _INFLIGHT.add(repo_rel)
            thread = threading.Thread(
                target=_push_thread, args=(repo_rel, raw, token),
                daemon=True,
                name=f"saveback-{os.path.basename(repo_rel)}")
            thread.start()
            scheduled.append(repo_rel)
    except Exception:
        pass
    return scheduled


def _fetch_bytes(repo_rel, token):
    """The repo copy of one file via the Contents API, or
    None. Raises only on transport failure; callers swallow."""
    status, meta = _http_json(
        "GET", _contents_url(repo_rel) + f"?ref={_BRANCH}", token)
    if status != 200 or not isinstance(meta, dict):
        return None
    content = meta.get("content")
    if isinstance(content, str) \
            and meta.get("encoding") == "base64":
        try:
            return base64.b64decode(content)
        except Exception:
            return None
    return None


def restore_history_files(root=None, token=None):
    """Boot restore: for each history file MISSING locally (or
    zero bytes), write the repo copy back, so the history
    displays read the restored store. A local file that exists
    is never overwritten — it is this deployment's own newest
    record. Returns the repo-relative paths restored. Never
    raises."""
    restored = []
    try:
        if token is None:
            token = _secret_token()
        if not token:
            return restored
        base = root or _repo_root()
        for repo_rel in _HISTORY_RELS:
            local = os.path.join(base, *repo_rel.split("/"))
            try:
                if os.path.isfile(local) \
                        and os.path.getsize(local) > 0:
                    continue
            except Exception:
                continue
            try:
                raw = _fetch_bytes(repo_rel, token)
            except Exception:
                raw = None
            if not raw:
                continue
            try:
                os.makedirs(os.path.dirname(local),
                            exist_ok=True)
                tmp = local + ".restore-tmp"
                with open(tmp, "wb") as fh:
                    fh.write(raw)
                os.replace(tmp, local)
                restored.append(repo_rel)
            except Exception:
                continue
    except Exception:
        pass
    return restored


def restore_history_files_async():
    """Once-per-process boot restore on a daemon thread, so
    the first render never waits on the network; later renders
    read the restored files from disk. Returns True iff the
    restore thread was started by this call. Never raises."""
    global _RESTORE_STARTED
    try:
        with _LOCK:
            if _RESTORE_STARTED:
                return False
            _RESTORE_STARTED = True
        thread = threading.Thread(
            target=restore_history_files, daemon=True,
            name="saveback-restore-history")
        thread.start()
        return True
    except Exception:
        return False
