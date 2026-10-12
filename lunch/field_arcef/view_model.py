def build_view_model(context):
    import streamlit as st
    result=st.session_state.get("arcef_sv_result") or {}
    return {"result":result,"snapshot":context.snapshot}
