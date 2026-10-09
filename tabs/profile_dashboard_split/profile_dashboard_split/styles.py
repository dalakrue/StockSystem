import streamlit as st


def profile_css():
    st.markdown(
        """
        <style>
        .profile-card {
            background: linear-gradient(135deg, rgba(235,247,255,.92), rgba(245,248,252,.88));
            border: 1px solid rgba(120,170,210,.35);
            border-radius: 22px;
            padding: 18px;
            box-shadow: 0 10px 30px rgba(30, 90, 130, .12);
            margin-bottom: 16px;
        }
        .mini-title {
            font-size: 14px;
            opacity: .72;
            font-weight: 700;
            margin-bottom: 4px;
        }
        .big-value {
            font-size: 26px;
            font-weight: 900;
        }
        .status-good {
            color: #087f5b;
            font-weight: 800;
        }
        .status-warn {
            color: #b7791f;
            font-weight: 800;
        }
        .status-bad {
            color: #c92a2a;
            font-weight: 800;
        }
        @media (max-width: 768px) {
            .profile-card {
                padding: 10px;
                border-radius: 14px;
                font-size: 12px;
            }
            .big-value {
                font-size: 18px;
            }
            div[data-testid="stMetricValue"] {
                font-size: 18px;
            }
            div[data-testid="stMetricLabel"] {
                font-size: 11px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
