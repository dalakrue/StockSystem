"""Cheap build progress and deferred downloads of already finalized artifacts."""
from collections.abc import Mapping
from core.resumable_build_20260928 import chunk_key_date_range, is_raw_ohlc_kind
from core.monthly_runtime import ENGINE_VERSION, ROOT


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
                failed_chunks=sum(len(item.get('failed_chunks') or []) for item in items),
                provider_gaps=sum(len(item.get('gap_chunks') or []) for item in items))


def _unfinished_range_lines(job, limit=6):
    """Human-readable list of failed chunks and provider no-data gaps."""
    lines = []
    for symbol in job.get('symbols') or []:
        item = (job.get('symbols_progress') or {}).get(symbol) or {}
        gaps = item.get('gap_chunks') or {}
        if isinstance(gaps, Mapping):
            for key, info in gaps.items():
                text = info.get('range') if isinstance(info, Mapping) and info.get('range') else chunk_key_date_range(key)
                lines.append(f"{symbol}: {text} — provider has no data (recorded as gap)")
        for key in item.get('failed_chunks') or []:
            lines.append(f"{symbol}: {chunk_key_date_range(key)} — failed, retried on Resume")
    return lines[:limit], max(0, len(lines) - limit)


def raw_download_label(job, is_partial):
    """Range-aware (2026-10-07 split) button label + filename for raw downloads.

    Split-range jobs (2020-01-01 → Latest, 2015-01-01 → 2020-01-01) get their
    own label/filename; legacy 10-year jobs keep the original wording.
    """
    job = job if isinstance(job, Mapping) else {}
    range_label = str(job.get("range_label") or "").strip()
    raw_range = str(job.get("raw_range") or "").strip()
    years = int(job.get("history_years") or 2)
    if range_label and raw_range:
        slug = raw_range.lower()
        if is_partial:
            return (f"\U0001f4e5 Download Partial Raw OHLC CSV ({range_label}) — data loaded so far",
                    f"raw_ohlc_all_symbols_H1_{slug}_partial.csv")
        return (f"\U0001f4e5 Download Raw OHLC CSV ({range_label}) — All Symbols",
                f"raw_ohlc_all_symbols_H1_{slug}.csv")
    if is_partial:
        return ("📥 Download Partial 10-Year Raw OHLC CSV — data loaded so far",
                f"raw_ohlc_all_symbols_H1_{years}_years_partial.csv")
    return (f"📥 Download {years}-Year Raw OHLC CSV — All Symbols",
            f"raw_ohlc_all_symbols_H1_{years}_years.csv")


def _render_raw_download(st, store, job, artifacts, metrics, years):
    """Full or partial 10-year raw OHLC download for raw-only jobs."""
    full = artifacts.get('raw_ohlc_csv')
    partial = artifacts.get('raw_ohlc_partial_csv')
    chosen = full or partial
    if chosen is None:
        range_label = str((job.get("range_label") if isinstance(job, Mapping) else "") or "10-Year")
        st.caption(f'Download {range_label} Raw OHLC CSV appears after the worker checkpoints. '
                   'If the load stalls, Stop the build — a partial CSV of the data downloaded so far is then prepared, '
                   'and Resume retries the missing ranges (provider no-data ranges are recorded as gaps so the load can finish).')
        return
    is_partial = chosen is partial
    label, filename = raw_download_label(job, is_partial)
    path = chosen['path']
    # No OHLC work and no large CSV deserialization during reruns.
    # Streamlit executes this callback only when Download is clicked.
    st.download_button(label, data=lambda path=path: store.get_object(path),
                       file_name=filename, mime='text/csv', on_click='ignore',
                       key=f"download_{chosen['kind']}_{job['id']}", use_container_width=True,
                       help=f"{chosen.get('symbol_count', metrics['total'])} symbols · {chosen.get('rows', 0):,} rows · all available completed H1 candles")
    note = chosen.get('coverage_note')
    if note:
        st.caption(('Partial CSV coverage — ' if is_partial else 'CSV coverage — ') + note)
    if is_partial:
        st.caption('Resume the build to keep downloading the missing ranges; this partial file stays available meanwhile.')
    else:
        _rl = str(job.get("range_label") or "10-Year") if isinstance(job, Mapping) else "10-Year"
        st.caption(f'{_rl} raw OHLC CSV is ready for download.')
    if chosen.get('provider_coverage_short'):
        st.warning('Twelve Data has no data for some requested ranges (see coverage note above) — recorded as gaps, never fabricated.')


def render_build_artifacts(st, store, job):
    if not job:
        return
    metrics = progress_metrics(job)
    raw_only = is_raw_ohlc_kind(job.get('kind'))
    st.progress(metrics['loading'], text=f"Loading OHLC · {100 * metrics['loading']:.1f}% · {metrics['loaded']}/{metrics['total']} symbols")
    if not raw_only:
        st.progress(metrics['calculating'], text=f"Calculating S1–S240 · {100 * metrics['calculating']:.1f}% · {metrics['calculated']}/{metrics['total']} symbols")
    if raw_only:
        st.caption(f"Loaded candles: {metrics['candle_rows']:,} · Failed chunks: {metrics['failed_chunks']} · Provider no-data gaps: {metrics['provider_gaps']}")
    else:
        st.caption(f"Loaded candles: {metrics['candle_rows']:,} · Strategy rows: {metrics['strategy_rows']:,} · Failed chunks: {metrics['failed_chunks']}")
    st.caption(f"Requested UTC coverage: {job.get('start_date', '—')} → {job.get('end_date', '—')}")
    if raw_only:
        lines, extra = _unfinished_range_lines(job)
        if lines:
            st.caption("Unfinished ranges: " + "; ".join(lines) + (f" (+{extra} more)" if extra else ""))
    if not job.get('fast_build_mode') and not raw_only:
        return
    artifacts = {a.get('kind'): a for a in job.get('result_manifest') or []}
    years = int(job.get('history_years') or 2)
    if raw_only:
        _render_raw_download(st, store, job, artifacts, metrics, years)
        return
    downloads = [
        ('raw_ohlc_csv', f'📥 Download {years}-Year Raw OHLC CSV — All Symbols', f'raw_ohlc_all_symbols_H1_{years}_years.csv'),
        ('middle_ranking_first_half_csv','📥 Download First Half CSV — All Symbols','backtest_all_symbols_H1_first_half.csv'),
        ('middle_ranking_second_half_csv','📥 Download Second Half CSV — All Symbols','backtest_all_symbols_H1_second_half.csv'),
        ('middle_ranking_csv', f'📥 Download Full {years}-Year Continuous Backtest CSV — All Symbols', f'backtest_all_symbols_H1_{years}_years.csv'),
    ]
    for kind, label, filename in downloads:
        artifact = artifacts.get(kind)
        if not artifact:
            if kind == 'raw_ohlc_csv':
                st.caption('Raw OHLC download becomes available after loading finishes, before strategy calculation finishes.')
            elif kind == 'middle_ranking_csv':
                st.caption('Full backtest download becomes available after calculations, hourly ranking and CSV finalization finish.')
            continue
        # No OHLC/strategy work and no large CSV deserialization during reruns.
        # Streamlit executes this callback only when Download is clicked.
        if kind != "raw_ohlc_csv" and artifact.get("strategy_engine") != ENGINE_VERSION:
            st.caption("Rebuild strategy history: obsolete strategy cache")
            continue
        path = artifact['path']
        st.download_button(label, data=lambda path=path: store.get_object(path),
                           file_name=filename, mime='text/csv', on_click='ignore',
                           key=f"download_{kind}_{job['id']}", use_container_width=True,
                           help=f"{artifact.get('symbol_count', metrics['total'])} symbols · {artifact.get('rows', 0):,} rows · all available completed H1 candles")
        if kind == 'raw_ohlc_csv':
            st.caption('10-Year raw OHLC CSV is ready for download.' if raw_only else
                       'Raw OHLC is ready. You can download it while S1–S240 calculations continue.')

    if not raw_only:
        st.download_button("Download S1–S240 equation mapping",(ROOT/"equation_column_map.csv").read_bytes(),file_name="equation_column_map.csv",mime="text/csv",key=f"mapping_{job['id']}")
