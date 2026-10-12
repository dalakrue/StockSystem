from pathlib import Path
root=Path('/mnt/data/work_upgrade')
# increase candle defaults and hard caps
for p in [root/'core/config/defaults.py', root/'core/secure_api_startup_20260619.py', root/'core/calculation/run_orchestrator.py', root/'core/connectors/data_parts/session.py', root/'core/connectors/websocket_feed.py', root/'core/app/refresh.py', root/'core/data/market_data_orchestrator.py', root/'core/data/multi_symbol_scheduler.py', root/'core/multi_symbol_api_runtime_20260702.py']:
    if p.exists():
        s=p.read_text(errors='ignore')
        s=s.replace('60000', '250000')
        p.write_text(s)

# finder last year/2 years and robust preset
p=root/'ui/field3_multisymbol_regime_summary_20260722.py'
s=p.read_text()
s=s.replace('["Custom", "Last 7 Days", "Last 30 Days", "Last 365 Days", "All Loaded History"]', '["Custom", "Last 7 Days", "Last 30 Days", "Last 365 Days", "Last 2 Years", "All Loaded History"]')
s=s.replace('"Last 365 Days": 365,', '"Last 365 Days": 365,\n            "Last 2 Years": 730,')
s=s.replace('preset_days = {"Last 7 Days": 7, "Last 30 Days": 30, "Last 365 Days": 365}', 'preset_days = {"Last 7 Days": 7, "Last 30 Days": 30, "Last 365 Days": 365, "Last 2 Years": 730}')
p.write_text(s)

# remove possible stale pyc to avoid old code
for pyc in root.rglob('*.pyc'):
    try: pyc.unlink()
    except: pass
