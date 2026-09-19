# ADX Quant Pro — Top-30 Multi-Symbol Decision Package

## 2026-07-27 Top-30 selector and fast Field 3 upgrade

Settings now supports one canonical 30-symbol universe: 10 symbols from each of
three selectors. Selector 3 includes a dedicated Third Best 10 candidate preset
with DXY and the requested target-spread-under-25 note. Load All Selected runs
all three selector workers. Super Quick calculates every successfully loaded
symbol through the compute-only Field 3 path, reuses unchanged results, and
shows Top 5, Last 5, and Higher/Middle regime agreement with color cues.

## 2026-06-21 six-principal-field Lunch upgrade

Lunch now has exactly six genuine lazy principal fields: Full Metric/Decision Histories, cached Power BI Path, Regime Standards, Dinner Combined Intelligence, Grounded AI Assistant, and End-to-End Readiness. The three-dot menu has separate Refresh Data, Run Calculation, and Reduce RAM controls. Copy Short/Copy All/JSON use one generation-bound service. Protected calculation files remain byte-for-byte unchanged. See `DELIVERY_INDEX_20260621_SIX_FIELD.md`.


## 2026-06-21 ten-paper shadow validation addition

This package now includes ten additive, fail-safe research layers for Model-X knockoffs, central online FDR, reject-option decisions, flexible asymmetric loss, lightweight SHAP/contribution explanations, monotonicity validation, exact delta maintenance, bounded provenance, metamorphic testing, and CALM coordination classification. All start in **SHADOW** mode; protected formulas and decisions remain authoritative.

Before the first upgraded run, create a database backup and apply the idempotent schema:

```powershell
py -3.12 tools\migrate_ten_paper_20260621.py --backup
py -3.12 tools\migrate_ten_paper_20260621.py --verify-only
```

Primary reports: `ARCHITECTURE_AUDIT_20260621_TEN_PAPER_SHADOW.md`, `RESEARCH_PAPER_TO_CODE_MAPPING_20260621.md`, `TEST_REPORT_20260621_TEN_PAPER.md`, `PERFORMANCE_REPORT_20260621_TEN_PAPER.md`, and `EVIDENCE_LIMITATIONS_20260621_TEN_PAPER.md`.

## Correct entry file

Run **`app.py`**:

```powershell
streamlit run app.py
```

Streamlit Community Cloud main file path: **`app.py`**. Deployment target: Python 3.12.

## What this package changes

This is the complete original application plus additive history/performance hardening. Existing trading formulas and protected outputs are preserved. Lunch fields are true-lazy, Fields 4–5 share one placement gate but retain separate 4A/4B logic/state, Morning/Research heavy imports are gated, and the existing 35 common-identity evidence tables plus 15 new ten-paper research tables are committed atomically with the canonical generation.

## First local run

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python tools\migrate_history_evidence_20260620.py --backup
py -3.12 tools\migrate_ten_paper_20260621.py --backup
streamlit run app.py
```

## Important reports

- `AUDIT_BASELINE_REPORT_20260620_HISTORY_FIRST.md`
- `ARCHITECTURE_CALL_GRAPH_20260620.md`
- `IMPLEMENTATION_REPORT_20260620_HISTORY_FIRST.md`
- `DATABASE_MIGRATION_REPORT_20260620_HISTORY_EVIDENCE.md`
- `TEN_PAPER_RESEARCH_MAPPING_20260620.md`
- `PERFORMANCE_REPORT_20260620_BEFORE_AFTER.md`
- `TEST_REPORT_20260620_HISTORY_FIRST.md`
- `LIMITATIONS_EVIDENCE_20260620.md`
- `ROLLBACK_INSTRUCTIONS_20260620.md`
- `WINDOWS_AND_STREAMLIT_CLOUD_COMMANDS_20260620.md`
- `MODIFIED_FILES_MANIFEST_20260620.md`

Machine-readable inventories and measurements are included as JSON.

## Safe operating contract

Use Settings → **Run Calculation + Open Lunch** for a manual calculation. Opening/closing fields or switching tabs reads the published generation and does not initiate the complete calculation. Keep API keys in Streamlit Secrets or temporary server-side session inputs; do not commit secret files.
