"""Fast deployment preflight for Streamlit Cloud.

Run from the project root:
    python tools/streamlit_cloud_preflight.py
"""
from __future__ import annotations

import compileall
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_FILES = (
    "app.py",
    "runtime.txt",
    "requirements.txt",
    ".streamlit/config.toml",
    "core/ui/legacy_impl/styles_impl.py",
    "tabs/antd_page_router_20260615.py",
)


def main() -> int:
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        print("FAIL missing files:", ", ".join(missing))
        return 1

    if "python-3.12" not in (ROOT / "runtime.txt").read_text(encoding="utf-8"):
        print("FAIL runtime.txt must request Python 3.12")
        return 1

    if "MetaTrader5" in (ROOT / "requirements.txt").read_text(encoding="utf-8"):
        print("FAIL MetaTrader5 must stay out of Linux/Streamlit Cloud requirements.txt")
        return 1

    if not compileall.compile_dir(ROOT, quiet=1, force=True):
        print("FAIL Python compilation")
        return 1

    for module_name in (
        "core.ui.styles",
        "core.styles",
        "tabs.antd_page_router_20260615",
        "app",
    ):
        importlib.import_module(module_name)
        print("OK import", module_name)

    from core.ui.styles import apply_global_styles
    if not callable(apply_global_styles):
        print("FAIL global style function is unavailable")
        return 1

    print("PASS Streamlit Cloud preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
