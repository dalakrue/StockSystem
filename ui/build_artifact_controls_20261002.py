"""Cheap build progress and deferred downloads of already finalized artifacts."""
from collections.abc import Mapping


def progress_metrics(job):
    items = [item for item in (job.get('symbols_progress') or {}).values() if isinstance(item, Mapping)]
    total = len(job.get('symbols') or [])
    chunks = sum(int(item.get('completed_chunks') or 0) for item in items)
    chunk_total = sum(int(item.get('total_chunks') or 0) for item in items)
    loaded = sum(item.get('status') == 'COMPLETE' for item in items)
    calculated = sum(item.get('finder_status') == 'COMPLETE' for item in items)
    return dict(loading=min(chunks / max(chunk_total, 1), 1), calculating=calculated / max(total, 1),
                loaded=loaded, calculated=calculated, total=total,
                candle_rows=sum(int(item.get('actual_candle_rows') or item.get('downloaded_candle_rows') or 0) for item in items),
                strategy_rows=sum(int(item.get('finder_rows') or 0) for item in items),
                failed_chunks=sum(len(item.get('failed_chunks') or []) for item in items))


def render_build_artifacts(st, store, job):
    if not job:
        return
    metrics = progress_metrics(job)
    st.progress(metrics['loading'], text=f"Loading OHLC · {100 * metrics['loading']:.1f}% · {metrics['loaded']}/{metrics['total']} symbols")
    st.progress(metrics['calculating'], text=f"Calculating S1–S120 · {100 * metrics['calculating']:.1f}% · {metrics['calculated']}/{metrics['total']} symbols")
    st.caption(f"Loaded candles: {metrics['candle_rows']:,} · Strategy rows: {metrics['strategy_rows']:,} · Failed chunks: {metrics['failed_chunks']}")
    st.caption(f"Requested UTC coverage: {job.get('start_date', '—')} → {job.get('end_date', '—')}")
    if not job.get('fast_build_mode'):
        return
    artifacts = {a.get('kind'): a for a in job.get('result_manifest') or []}
    for kind, label, filename in (
        ('raw_ohlc_csv', '📥 Download 2-Year Raw OHLC CSV — All Symbols', 'raw_ohlc_all_symbols_H1_2_years.csv'),
        ('middle_ranking_csv', '📥 Download 2-Year Continuous Backtest CSV — All Symbols', 'backtest_all_symbols_H1_2_years.csv'),
    ):
        artifact = artifacts.get(kind)
        if not artifact:
            if kind == 'raw_ohlc_csv':
                st.caption('Raw OHLC download becomes available after loading finishes, before strategy calculation finishes.')
            else:
                st.caption('Full backtest download becomes available after calculations, hourly ranking and CSV finalization finish.')
            continue
        # No OHLC/strategy work and no large CSV deserialization during reruns.
        # Streamlit executes this callback only when Download is clicked.
        path = artifact['path']
        st.download_button(label, data=lambda path=path: store.get_object(path),
                           file_name=filename, mime='text/csv', on_click='ignore',
                           key=f"download_{kind}_{job['id']}", use_container_width=True,
                           help=f"{artifact.get('symbol_count', metrics['total'])} symbols · {artifact.get('rows', 0):,} rows · all available completed H1 candles")
        if kind == 'raw_ohlc_csv':
            st.caption('Raw OHLC is ready. You can download it while S1–S120 calculations continue.')
