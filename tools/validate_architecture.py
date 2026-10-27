"""Lightweight architecture validator.

Run locally from the project root:
    python tools/validate_architecture.py

This checks source compilation and verifies the expected modular folders exist.
It does not require MT5 or API keys.
"""

from __future__ import annotations

import compileall
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PATHS = [
    "app.py",
    "main.py",
    "adx_dashpoard.py",
    "core/app/runner.py",
    "core/app/routes.py",
    "core/app/registry.py",
    "core/app/imports.py",
    "core/config/defaults.py",
    "core/state/session_state.py",
    "core/utils/numeric.py",
    "core/utils/timer.py",
    "core/utils/symbols.py",
    "core/data/synthetic.py",
    "core/connectors/data_connectors.py",
    "core/storage/database.py",
    "core/models/quant_models.py",
    "core/ui/styles.py",
    "tabs/home.py",
    "tabs/home_split/home.py",
    "tabs/home_split/legacy/implementation.py",
    "tabs/engine.py",
    "tabs/train_data.py",
    "tabs/train/train_data_legacy.py",
    "tabs/pre_original.py",
    "tabs/database_tab.py",
    "tabs/profile.py",
]


def main() -> int:
    missing = [p for p in REQUIRED_PATHS if not (ROOT / p).exists()]
    if missing:
        print("Missing required architecture files:")
        for p in missing:
            print(" -", p)
        return 1

    ok = compileall.compile_dir(ROOT, quiet=1, maxlevels=10)
    if not ok:
        print("Python compilation failed. Check the first error above.")
        return 2

    print("Architecture validation passed.")
    print("Run app with: streamlit run app.py  (main.py also remains compatible)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
