"""Professional and student-friendly product explanation.

This renderer is text-only and read-only.  It does not touch calculations,
connectors, canonical snapshots, or navigation state.
"""
from __future__ import annotations

from typing import Any, Mapping


def render_app_professional_guide(*, expanded: bool = False, context: Mapping[str, Any] | None = None) -> None:
    import streamlit as st

    context = context or {}
    with st.expander("📘 Explain This App — Professional Guide + Student Guide", expanded=expanded):
        st.markdown(
            """
### What this application is

**New7 Galileo Quant** is a quantitative market-research and decision-support platform for a **canonical Top-30 multi-symbol universe** at the selected timeframe. It converts completed market candles, model outputs, regime evidence, news/NLP evidence, and validation records into one synchronized research snapshot. The app is not a promise of profit and it does not replace human risk control. Its purpose is to make a complicated analytical process **traceable, repeatable, and easier to study**.

A simple way to understand it is to imagine a weather station for market conditions. A weather station does not control the weather; it measures temperature, pressure, wind, and uncertainty. In the same way, this app measures direction, pressure, volatility, regime, confidence, disagreement, forecast error, and data quality. It then explains whether the available evidence is strong, mixed, stale, incomplete, or unsuitable for action.

### What the app can do

The platform can:

- load and normalize completed EURUSD H1 candles from the configured source;
- publish one canonical calculation identity shared by Lunch, Dinner, Finder, Power BI, and the AI Assistant;
- compare current evidence with up to 25 broker days of history;
- display production calculations separately from research-only adjustments;
- inspect Alpha, Beta, Delta, regime persistence, transition pressure, uncertainty, and model agreement;
- show prediction paths and their historical error/coverage evidence;
- combine technical, session, regime, data-mining, and NLP evidence without hiding the original source columns;
- apply protective decision labels such as **ALLOWED**, **WAIT FOR PULLBACK**, **HOLD AND PROTECT**, and **NO TRADE**;
- export or copy bounded evidence for reports, presentations, Power BI, or thesis documentation;
- run thesis research modules without overwriting the protected production result.

### The main workflow

1. **Open Settings.** Choose the data source, symbol, timeframe, broker-clock setting, and optional API connections.
2. **Run one calculation from Settings.** The run button refreshes data once, calculates the selected scope, and publishes one completed-candle generation.
3. **Read Lunch first.** Lunch contains the core production evidence: the metric history, prediction path, and three-standard regime history.
4. **Use Dinner for combined and thesis evidence.** Dinner brings published Fields 4, 6, 7, 8, and 9 into one audit-friendly view and separates research conclusions from production truth.
5. **Use Finder to filter by day and hour.** Finder is read-only. It changes the displayed slice, not the underlying calculation.
6. **Use the AI Assistant for explanation.** Ask about the current hour, the last 25 days, disagreement, data quality, prediction paths, or thesis methods. A good answer should cite the field, table, candle, run ID, and generation ID.
7. **Treat missing data honestly.** A blank or unavailable value means the required source was not published or could not be joined safely. It must not be replaced with a guessed number.

### How to read the major concepts

**Production result** is the protected result created by the main Lunch calculation. It is the source of truth for the current generation.

**Research result** is an additional experiment used for study, calibration, comparison, or thesis work. It must never silently replace the production result.

**Alpha** describes directional tendency and strength. Positive Alpha generally supports upward pressure; negative Alpha generally supports downward pressure. The magnitude and stability matter as much as the sign.

**Beta** describes sensitivity: how strongly the result reacts to price, volatility, regime, pressure, news, session, or model disagreement. High Beta can mean the result changes quickly when conditions change.

**Delta** describes change. It measures whether Alpha, Beta, pressure, confidence, uncertainty, or error is accelerating or weakening.

**Regime** describes the market environment, such as trending, ranging, compressing, or transitioning. Lower, Middle, and Higher standards represent different time scales. A one-hour observation may influence the Lower standard, but should not automatically reverse the Middle or Higher standard.

**Reliability and confidence** are not certainty. They summarize how much evidence is available, how consistent it is, and how well similar historical predictions performed.

**Uncertainty and error** describe what the system does not know and how far past predictions differed from observed results. Higher uncertainty should reduce actionability.

**Protective action** is a risk-control interpretation, not a hidden BUY/SELL replacement:

- **ALLOWED** — evidence, coverage, and agreement meet the validated safety conditions;
- **WAIT FOR PULLBACK** — direction may be present, but entry timing or extension risk is unfavorable;
- **HOLD AND PROTECT** — preserve and manage an existing thesis while avoiding unnecessary new exposure;
- **NO TRADE** — conflict, poor data quality, high uncertainty, or insufficient evidence blocks action.

### For students and thesis work

The app can support a computer-science, data-science, financial-engineering, or quantitative-research project because it demonstrates a full pipeline: data collection, timestamp normalization, feature engineering, model comparison, uncertainty estimation, historical validation, database persistence, user-interface design, and evidence-based explanation.

A strong thesis should clearly separate:

- what is implemented in production;
- what is implemented only as a research prototype;
- what assumptions each method makes;
- how training, validation, and final test periods are separated;
- how look-ahead bias and leakage are prevented;
- how performance, memory, and rendering time are measured;
- which results are statistically supported and which remain hypotheses.

The research methods in this project include Matrix Profile concepts, SHAP-style attribution, adaptive conformal prediction, changepoint detection, dynamic model averaging, meta-labeling, selective classification, and duration-aware Hidden Semi-Markov modelling. Each method should be described with its theory, equations, data requirements, validation method, limitations, and exact implementation status. A simplified approximation must be labelled as an approximation.

### Professional use and limitations

Use the app as a structured research and audit tool. Verify the source, completed broker candle, run identity, data freshness, coverage, and uncertainty before interpreting any result. Do not treat a model label as a guarantee, and do not use historical accuracy as proof of future performance. The safest professional workflow is to preserve provenance, freeze thresholds before the final test set, document every change, and keep production and research outputs visibly separate.
            """
        )
        if context:
            st.caption(
                "Current context: "
                f"source={context.get('source', 'not published')} · "
                f"symbol={context.get('symbol', 'EURUSD')} · "
                f"timeframe={context.get('timeframe', 'H1')} · "
                f"run={context.get('run_id', 'not published')} · "
                f"generation={context.get('generation_id', context.get('calculation_generation', 'not published'))}."
            )


__all__ = ["render_app_professional_guide"]
