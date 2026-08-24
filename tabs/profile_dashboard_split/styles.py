import streamlit as st


def profile_css():
    st.markdown(
        """
        <style>
        .profile-card {
            background: linear-gradient(135deg, rgba(235,247,255,.97), rgba(247,250,253,.95));
            border: 1px solid rgba(95,155,205,.32);
            border-radius: 22px;
            padding: 16px;
            box-shadow: 0 10px 28px rgba(30, 90, 130, .10);
            margin-bottom: 14px;
            color: #102033;
        }
        .profile-title {font-size: 1.05rem; font-weight: 900; margin-bottom: .35rem;}
        .profile-muted {opacity: .74; font-size: .9rem;}
        .profile-score-good {color:#066e38;font-weight:900;}
        .profile-score-warn {color:#a36a00;font-weight:900;}
        .profile-score-danger {color:#b42318;font-weight:900;}
        .profile-pill {
            display: inline-block; padding: 5px 10px; margin: 3px 5px 3px 0;
            border-radius: 999px; background: rgba(39, 128, 227, .10);
            border: 1px solid rgba(39, 128, 227, .18); font-weight: 800;
        }
        div.stButton > button {border-radius: 14px; font-weight: 850; min-height: 42px;}
        button[data-baseweb="tab"] {font-weight: 850; padding: 8px 12px;}
        div[data-testid="stMetric"] {
            background: rgba(255,255,255,.70); border: 1px solid rgba(120,170,210,.22);
            border-radius: 16px; padding: 10px;
        }
        div[data-testid="stDataFrame"] {border-radius: 14px; overflow: hidden;}
        @media (max-width: 768px) {
            .block-container {padding-left: .65rem !important; padding-right: .65rem !important; padding-top: .65rem !important;}
            .profile-card {padding: 11px; border-radius: 16px; margin-bottom: 10px;}
            button[data-baseweb="tab"] {font-size: 12px; padding: 6px 8px;}
            div.stButton > button {min-height: 40px; font-size: 13px;}
            div[data-testid="column"] {min-width: 0 !important;}
            div[data-testid="stMetricValue"] {font-size: 18px;}
            input, textarea {font-size: 14px !important;}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
