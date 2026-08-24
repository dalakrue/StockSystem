"""Compatibility loader for the refactored `tabs/home.py` module.

The original large file was split into `home_parts/part_*.py` chunks so no
active Python source file exceeds 500 lines. The chunks are executed in
this module namespace to preserve all existing imports and runtime behavior.
"""
from importlib import import_module as _import_module

_PARTS_PACKAGE = (__package__ + '.home_parts') if __package__ else 'home_parts'
_PART_COUNT = 6

_SOURCE = ""
for _idx in range(_PART_COUNT):
    _part = _import_module(f"{_PARTS_PACKAGE}.part_{_idx:03d}")
    _SOURCE += _part.SOURCE

exec(compile(_SOURCE, __file__, "exec"), globals(), globals())

del _idx, _part, _SOURCE, _import_module, _PARTS_PACKAGE, _PART_COUNT

# 2026-06-09 compact reliable Data Visualization / copy export patch
try:
    from .home_patch_20260609 import apply as _apply_home_patch_20260609
    _apply_home_patch_20260609(globals())
    del _apply_home_patch_20260609
except Exception as _home_patch_exc_20260609:
    try:
        import streamlit as st
        st.warning(f"Home reliability patch skipped: {_home_patch_exc_20260609}")
    except Exception:
        pass


# 2026-06-11 Finder Alignment Engine upgrade (non-destructive).
try:
    from .finder_alignment_upgrade_20260611 import install as _install_finder_alignment_upgrade_20260611
    _install_finder_alignment_upgrade_20260611(globals())
    del _install_finder_alignment_upgrade_20260611
except Exception as _finder_alignment_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"Finder alignment patch skipped: {_finder_alignment_exc_20260611}")
    except Exception:
        pass

# 2026-06-11 History Control Center + Power BI Visualization Control Center (additive only).
try:
    from .history_visual_controls_20260611 import install as _install_history_visual_controls_20260611
    _install_history_visual_controls_20260611(globals())
    del _install_history_visual_controls_20260611
except Exception as _history_visual_controls_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"History/Visualization control patch skipped: {_history_visual_controls_exc_20260611}")
    except Exception:
        pass
# 2026-06-11 KNN Priority Placement (display priority only; no ML prediction changes).
try:
    from .knn_priority_placement_20260611 import install as _install_knn_priority_placement_20260611
    _install_knn_priority_placement_20260611(globals())
    del _install_knn_priority_placement_20260611
except Exception as _knn_priority_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"KNN priority placement patch skipped: {_knn_priority_exc_20260611}")
    except Exception:
        pass


# 2026-06-11 Full advanced efficiency/reliability command upgrade (additive display layer only).
try:
    from .advanced_efficiency_control_20260611 import install as _install_advanced_efficiency_control_20260611
    _install_advanced_efficiency_control_20260611(globals())
    del _install_advanced_efficiency_control_20260611
except Exception as _advanced_efficiency_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"Advanced efficiency control patch skipped: {_advanced_efficiency_exc_20260611}")
    except Exception:
        pass

# 2026-06-11 Two-section clean Data Visualization final wrapper.
try:
    from .dv_two_section_clean_upgrade_20260611 import install as _install_dv_two_section_clean_upgrade_20260611
    _install_dv_two_section_clean_upgrade_20260611(globals())
    del _install_dv_two_section_clean_upgrade_20260611
except Exception as _dv_two_section_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"Data Visualization two-section clean patch skipped: {_dv_two_section_exc_20260611}")
    except Exception:
        pass
# 2026-06-11 Final priority/history/Data Visualization fix (display-only, non-destructive).
try:
    from .final_priority_history_dv_fix_20260611 import install as _install_final_priority_history_dv_fix_20260611
    _install_final_priority_history_dv_fix_20260611(globals())
    del _install_final_priority_history_dv_fix_20260611
except Exception as _final_priority_history_dv_exc_20260611:
    try:
        import streamlit as st
        st.warning(f"Final priority/history/Data Visualization patch skipped: {_final_priority_history_dv_exc_20260611}")
    except Exception:
        pass
# 2026-06-12 One merged run-gated Lunch section with Unified PowerBI regime sync.
try:
    from .lunch_unified_sync_run_gate_20260612 import install as _install_lunch_unified_sync_run_gate_20260612
    _install_lunch_unified_sync_run_gate_20260612(globals())
    del _install_lunch_unified_sync_run_gate_20260612
except Exception as _lunch_unified_sync_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Lunch unified sync patch skipped: {_lunch_unified_sync_exc_20260612}")
    except Exception:
        pass

# 2026-06-12 Data Visualization News/NLP + KNN/Greedy intelligence section.
try:
    from .dv_news_nlp_intelligence_20260612 import install as _install_dv_news_nlp_intelligence_20260612
    _install_dv_news_nlp_intelligence_20260612(globals())
    del _install_dv_news_nlp_intelligence_20260612
except Exception as _dv_news_nlp_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Data Visualization News/NLP patch skipped: {_dv_news_nlp_exc_20260612}")
    except Exception:
        pass

# 2026-06-12 Data Visualization Quant Structure Intelligence section.
try:
    from .dv_quant_structure_intelligence_20260612 import install as _install_dv_quant_structure_intelligence_20260612
    _install_dv_quant_structure_intelligence_20260612(globals())
    del _install_dv_quant_structure_intelligence_20260612
except Exception as _dv_quant_structure_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Data Visualization Quant Structure patch skipped: {_dv_quant_structure_exc_20260612}")
    except Exception:
        pass

# 2026-06-12 Final merged Data Visualization/Home intelligence + mobile app UI.
try:
    from .dv_home_unified_intelligence_20260612 import install as _install_dv_home_unified_intelligence_20260612
    _install_dv_home_unified_intelligence_20260612(globals())
    del _install_dv_home_unified_intelligence_20260612
except Exception as _dv_home_unified_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Final merged intelligence patch skipped: {_dv_home_unified_exc_20260612}")
    except Exception:
        pass

# 2026-06-12 Data Visualization research alignment: Random Forest + Regime/NLP history.
try:
    from .dv_research_alignment_20260612 import install as _install_dv_research_alignment_20260612
    _install_dv_research_alignment_20260612(globals())
    del _install_dv_research_alignment_20260612
except Exception as _dv_research_alignment_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Data Visualization research alignment patch skipped: {_dv_research_alignment_exc_20260612}")
    except Exception:
        pass


# 2026-06-12 final cleanup: synced PowerBI projection + Research moved into Home + auth copy sync.
try:
    from .final_research_projection_auth_sync_20260612 import install as _install_final_research_projection_auth_sync_20260612
    _install_final_research_projection_auth_sync_20260612(globals())
    del _install_final_research_projection_auth_sync_20260612
except Exception as _final_research_projection_auth_sync_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"Final research/projection/auth sync patch skipped: {_final_research_projection_auth_sync_exc_20260612}")
    except Exception:
        pass

# 2026-06-12 AI Assistant Lite: local NLP + data mining chat inside Home.
try:
    from .ai_assistant_lite_home_patch_20260612 import install as _install_ai_assistant_lite_home_patch_20260612
    _install_ai_assistant_lite_home_patch_20260612(globals())
    del _install_ai_assistant_lite_home_patch_20260612
except Exception as _ai_assistant_lite_home_patch_exc_20260612:
    try:
        import streamlit as st
        st.warning(f"AI Assistant Lite patch skipped: {_ai_assistant_lite_home_patch_exc_20260612}")
    except Exception:
        pass

# 2026-06-14 Regime priority inner tab + Home selector final wrapper.
try:
    from .home_regime_inner_tab_20260614 import install as _install_home_regime_inner_tab_20260614
    _install_home_regime_inner_tab_20260614(globals())
    del _install_home_regime_inner_tab_20260614
except Exception as _home_regime_inner_tab_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Regime inner tab upgrade skipped: {_home_regime_inner_tab_exc_20260614}")
    except Exception:
        pass

# 2026-06-14 Final user-request placement/fix patch:
# AI inside Research, Data Visualization inside Lunch, no-history copy button,
# hidden Lunch-local login panel, dynamic non-constant priority scores.
try:
    from .final_user_request_20260614 import install as _install_final_user_request_20260614
    _install_final_user_request_20260614(globals())
    del _install_final_user_request_20260614
except Exception as _final_user_request_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Final user request patch skipped: {_final_user_request_exc_20260614}")
    except Exception:
        pass

# 2026-06-14 clean UI consolidation: Decision Control Panel,
# System Trust Center, Dynamic Entry Priority Center, and streamlined Regime Intelligence.
try:
    from .clean_decision_regime_ui_20260614 import install as _install_clean_decision_regime_ui_20260614
    _install_clean_decision_regime_ui_20260614(globals())
    del _install_clean_decision_regime_ui_20260614
except Exception as _clean_decision_regime_ui_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Clean decision/regime UI patch skipped: {_clean_decision_regime_ui_exc_20260614}")
    except Exception:
        pass
# 2026-06-14 final three-section Home/Lunch + Regime/AI intelligence wrapper.
try:
    from .final_three_center_upgrade_20260614 import install as _install_final_three_center_upgrade_20260614
    _install_final_three_center_upgrade_20260614(globals())
    del _install_final_three_center_upgrade_20260614
except Exception as _final_three_center_upgrade_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Final three-center wrapper skipped: {_final_three_center_upgrade_exc_20260614}")
    except Exception:
        pass
# 2026-06-14 Dinner/Morning/Data Analysis final reorganization patch.
try:
    from .dinner_morning_data_patch_20260614 import install as _install_dinner_morning_data_patch_20260614
    _install_dinner_morning_data_patch_20260614(globals())
    del _install_dinner_morning_data_patch_20260614
except Exception as _dinner_morning_data_patch_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Dinner/Morning/Data Analysis patch skipped: {_dinner_morning_data_patch_exc_20260614}")
    except Exception:
        pass


# 2026-06-14 Logic Safety Guard + Hidden Danger Engine (additive safety wrapper only).
try:
    from ui.logic_safety_panel import install as _install_logic_safety_panel_20260614
    _install_logic_safety_panel_20260614(globals(), location="Lunch/Home")
    del _install_logic_safety_panel_20260614
except Exception as _logic_safety_panel_exc_20260614:
    try:
        import streamlit as st
        st.warning(f"Logic Safety Guard wrapper skipped: {_logic_safety_panel_exc_20260614}")
    except Exception:
        pass

# 2026-06-15 Central shared calculation sync wrapper.
# Additive only: all original Home/Lunch renderers stay unchanged; this simply
# refreshes one shared result before/after the existing page renders.
try:
    from core.adx_shared_sync_20260615 import ensure_shared_calculation_result as _ensure_shared_calc_20260615
    _original_home_show_20260615 = show
    def show():  # type: ignore[no-redef]
        try:
            _ensure_shared_calc_20260615()
        except Exception:
            pass
        out = _original_home_show_20260615()
        try:
            _ensure_shared_calc_20260615(force=False)
        except Exception:
            pass
        return out
except Exception as _shared_sync_home_exc_20260615:
    try:
        import streamlit as st
        st.warning(f"Central shared sync wrapper skipped: {_shared_sync_home_exc_20260615}")
    except Exception:
        pass

# 2026-06-21 causal selective direction-accuracy evaluation.
# This wraps validation output only; protected forecast paths and trading
# decisions are not changed.
try:
    from .powerbi_direction_accuracy_patch_20260621 import install as _install_powerbi_direction_accuracy_20260621
    _install_powerbi_direction_accuracy_20260621(globals())
    del _install_powerbi_direction_accuracy_20260621
except Exception as _powerbi_direction_accuracy_exc_20260621:
    try:
        import streamlit as st
        st.warning(f"Power BI direction-accuracy patch skipped safely: {_powerbi_direction_accuracy_exc_20260621}")
    except Exception:
        pass
