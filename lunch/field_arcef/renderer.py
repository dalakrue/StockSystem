def render(vm):
    import streamlit as st, pandas as pd
    r=vm.get("result") or {}
    with st.expander("Quant Research and Thesis Engine — ARCEF-SV", expanded=False):
        if not r: st.info("Run Settings → Run Calculation + Open Lunch to publish ARCEF-SV."); return
        st.subheader("Current thesis result")
        st.json({k:r.get(k) for k in ("master_decision","direction_score","master_strength","reliability","uncertainty","entry_quality","algorithm_version","run_id")})
        sections=(("Equation parameters",r.get("equation_parameters")),("Proper-scoring diagnostics",r.get("proper_scoring_diagnostics")),("Calibration table",r.get("calibration_table")),("Conditional reliability matrix",r.get("conditional_reliability_matrix")),("Dynamic model weights",r.get("model_contribution_ledger")),("Model-confidence set",r.get("model_confidence_set")),("Validation tests",r.get("validation_tests")),("PBO result",r.get("pbo_result")),("Walk-forward result",r.get("walk_forward_result")),("Ablation study",r.get("ablation_study")),("Version history",r.get("version_history")))
        for title,data in sections:
            st.markdown(f"#### {title}")
            if isinstance(data,list): st.dataframe(pd.DataFrame(data),use_container_width=True,hide_index=True)
            elif isinstance(data,dict): st.json(data)
            else: st.write(data)
