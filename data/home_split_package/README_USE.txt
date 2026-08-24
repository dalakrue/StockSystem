HOW TO USE

Put these into your project:

tabs/
  home.py
  home_split/
    __init__.py
    home.py
    implementation.py
    helpers.py
    connectors.py
    risk_status.py
    positions.py
    account_panel.py
    risk_panel.py
    doo_prime_panel.py

Your existing app should keep importing:
from tabs.home import show

This split does not change original behavior.
The full original code is preserved in home_split/implementation.py.
Other split files re-export functions so future upgrades are easier.
