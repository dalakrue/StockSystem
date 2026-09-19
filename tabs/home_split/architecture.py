"""Home architecture metadata used for diagnostics and future upgrades."""

HOME_ARCHITECTURE_VERSION = "2026-06-02-home-multi-file-split"

HOME_MODULES = {
    "entry": "tabs/home.py",
    "router": "tabs/home_split/home.py",
    "legacy_loader": "tabs/home_split/legacy/implementation.py",
    "legacy_parts": "tabs/home_split/legacy/implementation_parts/",
    "doo_deep_loader": "tabs/home_split/doo_prime_deep.py",
    "doo_deep_parts": "tabs/home_split/doo_prime_deep_parts/",
    "css_hooks": "tabs/home_split/css_hooks.py",
    "uiux_hooks": "tabs/home_split/uiux_hooks.py",
}
