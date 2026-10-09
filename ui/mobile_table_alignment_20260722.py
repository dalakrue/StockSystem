"""Global responsive table alignment for laptop and phone surfaces."""
from __future__ import annotations

from typing import Any


def inject_mobile_table_alignment(st: Any, *, phone_mode: bool = False) -> None:
    compact = """
    [data-testid="stDataFrame"] {font-size: 0.72rem !important;}
    [data-testid="stDataFrame"] [role="columnheader"],
    [data-testid="stDataFrame"] [role="gridcell"] {line-height: 1.12 !important;}
    [data-testid="stTable"] table {font-size: 0.72rem !important;}
    """ if phone_mode else ""
    st.markdown(
        f"""
<style id="mobile-table-alignment-20260722">
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
}}
[data-testid="stDataFrame"] > div,
[data-testid="stDataFrame"] [data-testid="stDataFrameResizable"],
[data-testid="stTable"] {{
    max-width: 100% !important;
    overflow-x: auto !important;
    overscroll-behavior-x: contain !important;
    -webkit-overflow-scrolling: touch !important;
}}
[data-testid="stTable"] table {{
    width: max-content !important;
    min-width: 100% !important;
    border-collapse: collapse !important;
}}
[data-testid="stTable"] th, [data-testid="stTable"] td {{
    white-space: nowrap !important;
    vertical-align: middle !important;
}}
@media (max-width: 780px) {{
    .main .block-container {{
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }}
    [data-testid="stDataFrame"], [data-testid="stTable"] {{
        margin-left: 0 !important;
        margin-right: 0 !important;
    }}
    [data-testid="stDataFrame"] canvas {{
        max-width: none !important;
    }}
    [data-testid="stDataFrame"] button {{
        min-width: 30px !important;
        min-height: 30px !important;
    }}
}}
{compact}
</style>
""",
        unsafe_allow_html=True,
    )


__all__ = ["inject_mobile_table_alignment"]
