"""Frozen equation mode, lossless downloads, and separate research results."""
from io import BytesIO
import json
import pandas as pd
from core.monthly_runtime import ROOT, MONTHLY_METADATA, ENGINE_VERSION, raw_frame
from core.monthly_strategy_columns import STRATEGY_COLUMNS


def render_monthly_panel(st,state):
    with st.expander('Monthly equations · S1–S240',expanded=False):
        strict=st.checkbox('Strict-only mode (excludes all 240 reused-test equations)',value=bool(state.get('monthly_strict_only',False)),key='monthly_strict_only')
        st.caption('240 fixed symbol/month columns · historical Pip_Check YES · Strict_Valid NO for every equation. Myanmar checks: 08:00, 12:00, 16:00, 18:00, 20:00, 22:00; weekdays. Recovered research Middle Bias differs from the heavy regime display. Stage 2 re-prices Entry/TP/SL from the latest completed H1 close on every refresh (executable bid/ask at the check when supplied; otherwise indicative). Bias is computed from current OHLC. The journal requires executable quotes.')
        st.download_button('Download column/equation mapping CSV',(ROOT/'equation_column_map.csv').read_bytes(),file_name='equation_column_map.csv',mime='text/csv',key='monthly_mapping_download')
        quote_upload=st.file_uploader('Executable broker quotes JSON (optional; actual bid/ask and timestamp)',type=['json'],key='monthly_quote_upload')
        if quote_upload is not None:
            try:
                payload=json.loads(quote_upload.getvalue())
                stamp=pd.Timestamp(payload['check_at'])
                if stamp.tzinfo is None:raise ValueError('check_at must include timezone')
                state['monthly_check_time']=stamp
                state['monthly_executable_quotes']=payload['quotes']
            except Exception as exc:st.error(f'Quote evidence: {exc}')
        held_text=st.text_input('Broker-held symbols (comma separated; journal holdings are also included)',key='monthly_external_held_input')
        state['monthly_held_symbols']=[s.strip().upper().replace('/','') for s in held_text.split(',') if s.strip()]
        if st.button('Record current check in application journal',key='monthly_record_check'):
            try:
                from core.finder_history_store_20260924 import collect_loaded_frames
                from core.monthly_live_book import admit_check,reconcile_completed_exits,journal
                from core.monthly_runtime import latest_check
                frames,_=collect_loaded_frames(state,'H1')
                check=state.get('monthly_check_time') or latest_check()
                quotes=state.get('monthly_executable_quotes') or {}
                reconcile_completed_exits(frames,quotes,check)
                decision=admit_check(frames,check,quotes,external_held=state['monthly_held_symbols'],strict_only=strict)
                state['monthly_journal']=journal()
                st.write(decision['reason'])
                st.caption('Application journal only; no broker order was sent. Executable quote evidence is required. A censored/unresolved live holding remains held until reconciled.')
            except Exception as exc:st.error(f'Check journal: {exc}')
        book=state.get('monthly_journal')
        if book:
            st.dataframe(book['positions'],hide_index=True)
            st.download_button('Download journal check decisions',book['checks'].to_csv(index=False),file_name='live_check_decisions.csv',key='monthly_journal_checks')
            st.download_button('Download journal closed trades',book['trades'].to_csv(index=False),file_name='live_trade_log.csv',key='monthly_journal_trades')
        upload=st.file_uploader('Replay raw H1 CSV (all symbols)',type=['csv'],key='monthly_replay_upload')
        run=st.button('Run frozen equation portfolio replay',key='monthly_run_replay')
        if run:
            try:
                from core.monthly_backtest import replay_portfolio,independent_diagnostics,bundle
                if upload is not None:raw=pd.read_csv(upload,low_memory=False)
                else:
                    from core.finder_history_store_20260924 import collect_loaded_frames
                    frames,_=collect_loaded_frames(state,'H1')
                    if not frames:raise ValueError('Load H1 candles with Twelve Data or import a raw H1 CSV first')
                    raw=pd.concat([raw_frame(f,s) for s,f in frames.items()],ignore_index=True)
                with st.spinner('Calculating frozen equations and replaying the portfolio'):
                    result=replay_portfolio(raw,strict_only=strict)
                    diagnostics=independent_diagnostics(raw,signals=result['signals'],strict_only=strict)
                    state['monthly_replay_result']=result
                    state['monthly_diagnostics']=diagnostics
                    state['monthly_replay_bundle']=bundle(result,diagnostics)
                    state['monthly_result_engine']=ENGINE_VERSION
                    state['monthly_result_strict_only']=strict
            except Exception as exc:st.error(f'Monthly replay failed: {type(exc).__name__}: {exc}')
        result=state.get('monthly_replay_result')
        if result and state.get('monthly_result_engine')==ENGINE_VERSION and state.get('monthly_result_strict_only')==strict:
            m=result['metrics']
            st.write('Combined portfolio backtest — historical research')
            st.dataframe(pd.DataFrame([{k:m[k] for k in ('Trades','Net Pip','Max DD','ROMAD','Censored Trades','Max Concurrent Holdings')}]),hide_index=True)
            st.write('Reused-test results (selected using this period; no fresh unseen validation)')
            st.dataframe(pd.DataFrame([m['Reused-test metrics']]),hide_index=True)
            st.download_button('Download trade log',result['trades'].to_csv(index=False),file_name='monthly_trade_log.csv',mime='text/csv',key='monthly_trade_download')
            st.download_button('Download check decisions',result['checks'].to_csv(index=False),file_name='monthly_check_decisions.csv',mime='text/csv',key='monthly_check_download')
            st.download_button('Download complete replay and mapping ZIP',state['monthly_replay_bundle'],file_name='monthly_replay.zip',mime='application/zip',key='monthly_replay_download')
            parquet=BytesIO();result['signals'].to_parquet(parquet,index=False)
            st.download_button('Download every raw row with S1–S240 (Parquet)',parquet.getvalue(),file_name='monthly_S1_S240.parquet',mime='application/octet-stream',key='monthly_parquet_download')
            st.write('Independent equation diagnostics — separate books, not combined portfolio')
            st.dataframe(state['monthly_diagnostics'],hide_index=True)
        live=state.get('monthly_live_signals')
        if isinstance(live,pd.DataFrame) and not live.empty:
            cols=['Symbol','Strategy Decision']+[c for c in MONTHLY_METADATA if c in live]
            st.dataframe(live[cols],hide_index=True)
            st.download_button('Download current S1–S240 indications',live.to_csv(index=False),file_name='monthly_current_signals.csv',mime='text/csv',key='monthly_live_download')
            with st.expander('Live execution debug table · Stage 2 (current-OHLC reprice)',expanded=False):
                try:
                    from core.finder_history_store_20260924 import collect_loaded_frames
                    from core import live_execution as _lx
                    frames,_=collect_loaded_frames(state,'H1')
                    dbg=_lx.build_debug_table(live,frames)
                    if dbg.empty:
                        st.caption('No strategy hits at this check — nothing to reprice.')
                    else:
                        st.dataframe(dbg,hide_index=True)
                        st.download_button('Download debug table',dbg.to_csv(index=False),file_name='monthly_live_debug.csv',mime='text/csv',key='monthly_debug_download')
                        bad=_lx.validate_live_prices(dbg)
                        if bad.empty:
                            st.success(f'Validation PASS · {len(dbg)} signal(s): every BUY has current price < TP and every SELL has current price > TP. Entry equals current price.')
                        else:
                            st.error(f'Validation FAIL · {len(bad)} row(s) with TP already passed at display time:')
                            st.dataframe(bad,hide_index=True)
                    st.caption('Stage 1 (S1–S240 equation, symbol/month, direction, score, rank) is unchanged. Stage 2 re-prices Entry/TP/SL from the latest completed H1 close on every refresh; bias comes from current OHLC (EMA trend, momentum, ATR volatility, middle standard regime).')
                except Exception as exc:
                    st.error(f'Debug table: {type(exc).__name__}: {exc}')
