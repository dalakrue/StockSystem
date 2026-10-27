"""Focused acceptance checks for Finnhub, NLP, Research and Lunch restoration."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def validate_static_contracts() -> None:
    assert (ROOT / "app.py").is_file()
    assert (ROOT / "adx_dashpoard.py").is_file()
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "from adx_dashpoard import main" in app

    runtime = (ROOT / "runtime.txt").read_text(encoding="utf-8").strip()
    assert runtime == "python-3.12", runtime

    runner = (ROOT / "core/app/runner.py").read_text(encoding="utf-8")
    assert 'initial_sidebar_state="collapsed"' in runner

    sidebar = (ROOT / "ui/sidebar_hard_lock.py").read_text(encoding="utf-8")
    for required in ("11.25rem", "13.75rem", "78vw", "display:none!important", "width:0!important"):
        assert required in sidebar, required
    sticky = (ROOT / "ui/home_master_control_bar_20260615.py").read_text(encoding="utf-8")
    assert "position:fixed!important" in sticky and "z-index" in sticky

    finnhub = (ROOT / "core/finnhub_connector.py").read_text(encoding="utf-8")
    assert 'st.text_input("Finnhub API key", type="password"' in finnhub
    assert "DEFAULT_TIMEOUT" in finnhub and "MAX_RETRIES" in finnhub
    assert "request_params[\"token\"] = key" in finnhub
    assert "joblib" not in finnhub
    # One canonical input renderer; status mirrors do not duplicate the secret input.
    assert finnhub.count('st.text_input("Finnhub API key"') == 1

    drawer = (ROOT / "ui/sidebar_fallback_panel.py").read_text(encoding="utf-8")
    assert "NLP / LLM API key" not in drawer
    assert "Connect Market + NLP Together" not in drawer
    assert "Finnhub Connection Status" in drawer

    research = (ROOT / "tabs/research.py").read_text(encoding="utf-8")
    assert 'key="research_inner_tab"' in research
    assert research.count('key="research_inner_tab"') == 1
    assert "st.tabs([\"Data Analysis\", \"Data Mining\", \"NLP\"" not in research
    assert "FMP API backup" not in research

    router = (ROOT / "tabs/antd_page_router_20260615.py").read_text(encoding="utf-8")
    lunch = (ROOT / "ui/lunch_restored.py").read_text(encoding="utf-8")
    quick = (ROOT / "tabs/final_lunch_upgrade_20260617.py").read_text(encoding="utf-8")
    assert "render_restored_lunch_bottom" in router
    assert "Original Lunch Analysis" in lunch
    for label in (
        "Original Lunch Analysis — Auto Loaded",
        "Power BI Price Prediction Projection",
        "Full Metric Details",
        "Full Metric History",
        "Original Lunch Copy and Export Controls",
    ):
        assert label in lunch, label
    assert "Load Original Lunch Renderer" not in lunch
    assert "settings_run_orchestrator_20260617" in router
    assert 'render_finnhub_connector(location="settings")' in router
    assert '== "Lunch"' in quick and '== "Lunch"' in lunch


def validate_finnhub_secret_lifecycle() -> None:
    mod = importlib.import_module("core.finnhub_connector")

    class FakeStreamlit:
        def __init__(self):
            self.session_state = {}

    fake = FakeStreamlit()
    old_st = mod.st
    old_validate = mod.validate_connection
    mod.st = fake
    try:
        mod.initialize_finnhub_state()
        previous_value = "test_previous_" + ("x" * 12)
        candidate_value = "test_candidate_" + ("y" * 12)
        fake.session_state[mod.KEY_STATE] = previous_value
        fake.session_state[mod.CONNECTED_STATE] = True
        mod.validate_connection = lambda key: {
            "ok": False,
            "message": f"request token={key} failed",
            "availability": "UNAVAILABLE",
        }
        result = mod.connect(candidate_value)
        assert result["ok"] is False
        assert fake.session_state[mod.KEY_STATE] == ""
        assert fake.session_state[mod.CONNECTED_STATE] is False
        assert candidate_value not in fake.session_state[mod.ERROR_STATE]
        assert "[REDACTED]" in fake.session_state[mod.ERROR_STATE]
        mod.disconnect()
        assert fake.session_state[mod.KEY_STATE] == ""
        assert fake.session_state[mod.NEWS_STATE] == []
    finally:
        mod.st = old_st
        mod.validate_connection = old_validate


def validate_nlp_logic() -> None:
    from core.nlp_pipeline import NLPConfig, build_article_intelligence
    from core.nlp_event_response import calculate_nlp_reliability, compare_with_shared_outputs

    now = int(pd.Timestamp.now(tz="UTC").timestamp())
    cfg = NLPConfig(buy_threshold=5.0, sell_threshold=-5.0)
    articles = [
        {
            "headline": "Federal Reserve hawkish as US CPI beats forecasts",
            "summary": "The dollar gains as the Fed signals higher interest rates and strong growth.",
            "source": "Source A",
            "datetime": now,
        },
        {
            "headline": "ECB hawkish as Eurozone PMI beats forecasts",
            "summary": "The euro gains as the ECB signals higher interest rates and resilient growth.",
            "source": "Source B",
            "publishedDate": pd.Timestamp.now(tz="UTC").isoformat(),
        },
        {
            "headline": "Federal Reserve hawkish as US CPI beats forecasts",
            "summary": "The dollar gains as the Fed signals higher interest rates and strong growth.",
            "source": "Older copy",
            "datetime": now - 60,
        },
    ]
    df = build_article_intelligence(articles, cfg)
    assert len(df) == 3
    usd = df[df["source"] == "Source A"].iloc[0]
    eur = df[df["source"] == "Source B"].iloc[0]
    duplicate = df[df["source"] == "Older copy"].iloc[0]
    assert float(usd["nlp_direction_score"]) < 0 and usd["nlp_direction"] == "SELL"
    assert float(eur["nlp_direction_score"]) > 0 and eur["nlp_direction"] == "BUY"
    assert pd.notna(eur["timestamp"]), "publishedDate was not normalized"
    assert duplicate["duplicate_status"] == "DUPLICATE"
    assert duplicate["nlp_direction"] == "WAIT"
    assert abs(float(duplicate["nlp_direction_score"])) < abs(float(usd["nlp_direction_score"]))

    article = {
        **usd.to_dict(),
        "svm_confidence": 0.80,
        "topic_probability": 75.0,
        "nlp_source_reliability": 80.0,
    }
    agreeing = compare_with_shared_outputs(article, {
        "regime": {"direction": "SELL"},
        "decision": {"direction": "SELL"},
        "powerbi": {"direction": "SELL", "price_confirmation": "SELL"},
    })
    conflicting = compare_with_shared_outputs(article, {
        "regime": {"direction": "BUY"},
        "decision": {"direction": "BUY"},
        "powerbi": {"direction": "BUY", "price_confirmation": "BUY"},
    })
    high_sample = calculate_nlp_reliability(article, agreeing, historical_sample_size=60, historical_accuracy=70)
    small_sample = calculate_nlp_reliability(article, agreeing, historical_sample_size=2, historical_accuracy=90)
    conflict = calculate_nlp_reliability(article, conflicting, historical_sample_size=60, historical_accuracy=70)
    assert high_sample["nlp_reliability_score"] > small_sample["nlp_reliability_score"]
    assert high_sample["nlp_reliability_score"] > conflict["nlp_reliability_score"]
    assert conflicting["less_risky_nlp_decision"] == "WAIT"


def validate_time_split_svm() -> None:
    from core import nlp_models

    labels = ["BUY", "SELL", "WAIT"] * 70
    phrases = {
        "BUY": "ecb hawkish euro growth beats forecast",
        "SELL": "fed hawkish dollar cpi beats forecast",
        "WAIT": "mixed market commentary no clear currency signal",
    }
    df = pd.DataFrame({
        "timestamp": pd.date_range("2025-01-01", periods=len(labels), freq="h", tz="UTC"),
        "model_text": [f"{phrases[label]} sample {i % 7}" for i, label in enumerate(labels)],
        "direction_label": labels,
    })
    artifact = "_validation_svm_20260617"
    model_path, meta_path = nlp_models._artifact_paths(artifact)
    try:
        result = nlp_models.train_linear_svm(df, min_df=1, artifact_name=artifact, calibrate=True)
        assert result.get("ok") is True, result
        metrics = result["metrics"]
        assert metrics.get("time_split") is True
        assert metrics.get("calibration_time_split") is True
        assert metrics.get("test_rows", 0) > 0
        pred = nlp_models.predict_linear_svm([
            "ecb hawkish euro growth",
            "fed hawkish dollar inflation",
            "mixed unclear market commentary",
        ], artifact_name=artifact)
        assert len(pred) == 3 and "svm_label" in pred.columns
        if metrics.get("calibrated"):
            assert pred["svm_confidence"].notna().all()
    finally:
        for path in (model_path, meta_path):
            path.unlink(missing_ok=True)
        try:
            nlp_models.load_artifact.clear()
        except Exception:
            pass


if __name__ == "__main__":
    validate_static_contracts()
    validate_finnhub_secret_lifecycle()
    validate_nlp_logic()
    validate_time_split_svm()
    print("Finnhub/NLP/Lunch/Research validation passed.")
