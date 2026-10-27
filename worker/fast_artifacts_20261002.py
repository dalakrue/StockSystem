"""Bounded-memory finalization; all-symbol hourly selection keeps causal state."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
import hashlib
import json
import tempfile
import pandas as pd
import pyarrow.parquet as pq
from core.resumable_build_20260928 import COMPACT_FINDER_COLUMNS, is_raw_ohlc_kind, normalize_symbol, put_dataframe
from core.strategy_audit_20260924 import STRATEGY_ENGINE_VERSION
from core.monthly_strategy_columns import STRATEGY_COLUMNS
from core.monthly_runtime import ROOT
from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection, ENTRY_FILTER_RELAXATION


class ArtifactCorruptionError(RuntimeError):
    def __init__(self, path, symbol, cause):
        super().__init__(f'Cached Parquet is unreadable for {symbol}: {type(cause).__name__}')
        self.path, self.symbol = path, symbol


def fingerprint(job, artifacts, kind):
    spec = {key: job.get(key) for key in ('symbols', 'timeframe', 'start_date', 'end_date', 'version', 'strict_only')}
    spec.update(engine=STRATEGY_ENGINE_VERSION, finalizer_version='split-halves-v1-20261003',kind=kind,
                inputs=[(a.get('path'), a.get('rows'), a.get('bytes')) for a in artifacts])
    return hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()


def _job_gap_ranges(job):
    """Collect documented provider no-data ranges per symbol.

    Gaps are recorded by the worker when Twelve Data explicitly reports no
    data for a chunk range (for example the API plan's historical depth ends
    before the chunk). They are reported, never fabricated.
    """
    progress = job.get("symbols_progress") if isinstance(job.get("symbols_progress"), dict) else {}
    gaps = {}
    for symbol, item in progress.items():
        if not isinstance(item, dict):
            continue
        recorded = item.get("gap_chunks") or {}
        if isinstance(recorded, dict) and recorded:
            gaps[normalize_symbol(symbol)] = [
                {"range": str(info.get("range") or key), "reason": str(info.get("reason") or "")[:220]}
                for key, info in recorded.items() if isinstance(info, dict)
            ]
    return gaps


def _raw_coverage_note(job, expected, seen_symbols, symbol_coverage, short_symbols, gap_ranges):
    """One human-readable line describing what a raw CSV actually contains."""
    bits = [f"{len(seen_symbols)}/{len(expected)} symbols"]
    if symbol_coverage:
        lo = min(lo for lo, hi in symbol_coverage.values())
        hi = max(hi for lo, hi in symbol_coverage.values())
        bits.append(f"{pd.Timestamp(lo):%Y-%m-%d} → {pd.Timestamp(hi):%Y-%m-%d}")
    missing = sorted(expected - set(seen_symbols))
    if missing:
        bits.append("not yet downloaded: " + ", ".join(missing))
    if short_symbols:
        bits.append("provider history shorter than requested: " + ", ".join(sorted(short_symbols)))
    gap_total = sum(len(rows) for rows in gap_ranges.values())
    if gap_total:
        bits.append(f"{gap_total} provider no-data range(s) recorded as gaps")
    return " · ".join(bits)


def finalize(job, store, manifest, *, raw=False, on_progress=None, should_stop=None,
             partial_ok=False, gap_ok=False):
    """Finalize the export CSV.

    ``partial_ok`` (raw-only): export whatever symbols/chunks are durable and
    publish a ``raw_ohlc_partial_csv`` artifact instead of raising on missing
    symbols or short provider history. Used when a 10-year load stalls or is
    stopped part-way so the user can always download the data loaded so far.

    ``gap_ok`` (raw-only): keep the full ``raw_ohlc_csv`` kind, but record a
    short provider history as ``provider_coverage_short`` metadata instead of
    raising TEN_YEAR_HISTORY_UNAVAILABLE. The CSV is published with the gaps
    documented; no candles are fabricated.
    """
    kind = 'raw_ohlc_partial_csv' if (raw and partial_ok) else ('raw_ohlc_csv' if raw else 'middle_ranking_csv')
    sources = [a for a in manifest if a.get('kind') == ('candle_chunk' if raw else 'finder_symbol')]
    if not sources:
        raise RuntimeError('No source artifacts for ' + kind)
    digest = fingerprint(job, sources, kind)
    for artifact in manifest:
        if artifact.get('kind') == kind and artifact.get('fingerprint') == digest and store.object_exists(artifact['path']):
            return artifact
    expected = {normalize_symbol(s) for s in job['symbols']}
    source_symbols = {normalize_symbol(a.get('symbol')) for a in sources}
    # gap_ok (raw-only) also tolerates symbols that are entirely missing when
    # their absence is documented as provider no-data gaps: failing the whole
    # job would strand the other 19 symbols' data again.
    allow_incomplete = raw and (partial_ok or gap_ok)
    if source_symbols != expected and not allow_incomplete:
        raise RuntimeError('ALL_SYMBOL_EXPORT_UNIVERSE_MISMATCH')
    missing_symbols = sorted(expected - source_symbols) if allow_incomplete else []
    start, end = pd.Timestamp(job['start_date']), pd.Timestamp(job['end_date'])
    coverage_state = {}
    exit_state = {}
    total_rows = 0
    seen_symbols = set()
    histogram = {}
    symbol_coverage = {}
    master_parts = []
    with tempfile.TemporaryDirectory(prefix='finder-finalize-') as directory:
        root = Path(directory)
        local = []
        # Each object is fetched once; subsequent range scans are Parquet filters.
        for index, artifact in enumerate(sources):
            filename = store.materialize_object(artifact['path'], root / f'source-{index}.parquet')
            try:
                names = pq.read_schema(filename).names
            except Exception as error:
                raise ArtifactCorruptionError(artifact['path'], artifact.get('symbol'), error) from error
            local.append((artifact, filename, names))
        csv_file = root / 'export.csv'
        split_at=start+(end-start)/2
        half_files={name:root/(name+'.csv') for name in ('first_half','second_half')}
        half_rows={name:0 for name in half_files}
        periods = list(pd.date_range(start.normalize(), end.normalize(), freq='7D'))
        for index, lower in enumerate(periods):
            if should_stop and should_stop():
                raise InterruptedError('Paused during export; saved symbol calculations retained')
            upper = min(lower + pd.Timedelta(days=7), end + pd.Timedelta(hours=1))
            pieces = []
            for artifact, filename, names in local:
                oldest = pd.to_datetime(artifact.get('oldest'), utc=True, errors='coerce')
                newest = pd.to_datetime(artifact.get('newest'), utc=True, errors='coerce')
                if pd.notna(oldest) and oldest >= upper or pd.notna(newest) and newest < lower:
                    continue
                if raw:
                    columns = list(names)
                    time_col = 'open_time'
                else:
                    # Retain all numerical/backtest columns; no lengthy strategy audit strings.
                    columns = [c for c in names if not c.endswith((' Reason', ' Signal')) and not c.startswith('_')]
                    time_col = 'Datetime'
                # Stored Finder timestamps historically have no timezone.
                schema = pq.read_schema(filename)
                aware = getattr(schema.field(time_col).type, 'tz', None)
                lo, hi = max(lower, start), upper
                if not aware:
                    lo, hi = lo.tz_localize(None), hi.tz_localize(None)
                try:
                    frame = pd.read_parquet(filename, columns=columns,
                        filters=[(time_col, '>=', lo.to_pydatetime()), (time_col, '<', hi.to_pydatetime())])
                except Exception as error:
                    raise ArtifactCorruptionError(artifact['path'], artifact.get('symbol'), error) from error
                if frame.empty:
                    continue
                if raw:
                    from core.execution_policy_20261003 import quote_metadata
                    meta=quote_metadata(frame,job['timeframe'])
                    frame=frame.drop(columns=[c for c in meta if c in frame],errors='ignore')
                    frame=pd.concat((frame,meta),axis=1)
                    frame['provider']=frame.get('provider',frame.get('data_source','UNSPECIFIED'))
                    frame.rename(columns={'open_time':'Datetime', 'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'}, inplace=True)
                    frame['Symbol'], frame['Timeframe'] = artifact['symbol'], job['timeframe']
                frame['Datetime'] = pd.to_datetime(frame['Datetime'], utc=True)
                frame = frame.loc[frame['Datetime'].between(start, end)]
                pieces.append(frame)
            if not pieces:
                continue
            frame = pd.concat(pieces, ignore_index=True, sort=False)
            del pieces
            frame = frame.sort_values(['Datetime', 'Symbol'], kind='mergesort').drop_duplicates(['Datetime', 'Symbol'], keep='last').reset_index(drop=True)
            price_cols = ['Open','High','Low','Close'] if raw else ['Open Price','Highest Price','Lowest Price','Close Price']
            if frame[price_cols].isna().any().any():
                raise RuntimeError('Export contains missing OHLC')
            if not raw:
                if 'Candle After Regime Start' in frame:
                    frame['Avg Regime Candle Rank'] = frame.groupby(['Datetime', 'Timeframe'], observed=True)['Candle After Regime Start'].rank(method='min', ascending=True).astype('Int64')
                # Carry exit event/bias across time partitions as well as the
                # selector's cumulative opportunity/selection counters.
                if 'Middle Regime Bias' in frame:
                    if 'Middle Bias Flip At' not in frame:
                        frame['Middle Bias Flip At'] = pd.Series(pd.NaT, index=frame.index, dtype='datetime64[ns, UTC]')
                    for symbol, group in frame.groupby('Symbol', observed=True, sort=False):
                        first = group.index[0]
                        previous = exit_state.get(str(symbol))
                        if previous:
                            old_bias, old_event = previous
                            bias = str(frame.at[first, 'Middle Regime Bias']).upper()
                            event = pd.to_datetime(frame.at[first, 'Middle Bias Flip At'], utc=True)
                            if old_bias in {'BUY','SELL','NEUTRAL'} and bias in {'BUY','SELL','NEUTRAL'} and old_bias != bias:
                                event = frame.at[first, 'Datetime']
                            elif pd.isna(event):
                                event = old_event
                            frame.at[first, 'Middle Bias Flip At'] = event
                frame = attach_hourly_four_selection(frame, coverage_state=coverage_state, copy=False)
                for symbol, group in frame.groupby('Symbol', observed=True, sort=False):
                    last = group.iloc[-1]
                    exit_state[str(symbol)] = (str(last.get('Middle Regime Bias', '')).upper(), last.get('Middle Bias Flip At', pd.NaT))
                frame = frame.sort_values(['Datetime', 'Symbol'], kind='mergesort').reset_index(drop=True)
                frame['Entry Filter Relaxation Percent'] = ENTRY_FILTER_RELAXATION * 100
                score_columns = [f'{c} Score' for c in STRATEGY_COLUMNS if f'{c} Score' in frame]
                if score_columns and 'Best Strategy' not in frame:
                    frame['Best Strategy'] = frame[score_columns].idxmax(axis=1).str.removesuffix(' Score')
                frame['Continuous OHLC Row'] = True
                frame['Finder Export Scope'] = 'ALL_SYMBOLS_ALL_CANDLES'
                n = frame.groupby('Datetime')['Strategy Hit Count'].sum()
                selected = frame.groupby('Datetime')['Hourly 4 Entry'].sum()
                if not selected.eq(n.clip(upper=4)).all():
                    raise RuntimeError('Hourly selection count mismatch')
                master_path = f"finder/{job['id']}/ranked/part-{index:04d}.parquet"
                saved = put_dataframe(store, master_path, frame)
                master_parts.append(dict(saved, kind='ranking_part', strategy_engine=STRATEGY_ENGINE_VERSION, strict_only=bool(job.get("strict_only",False)), oldest=frame['Datetime'].min().isoformat(), newest=frame['Datetime'].max().isoformat()))
            counts = frame.groupby('Datetime')['Symbol'].nunique().value_counts()
            for count, hours in counts.items():
                histogram[str(count)] = histogram.get(str(count), 0) + int(hours)
            seen_symbols.update(frame['Symbol'].astype(str).map(normalize_symbol))
            if raw and is_raw_ohlc_kind(job.get('kind')):
                for symbol, group in frame.groupby('Symbol', sort=False):
                    lo, hi = group['Datetime'].min(), group['Datetime'].max()
                    prior = symbol_coverage.get(symbol, (lo, hi))
                    symbol_coverage[symbol] = (min(prior[0], lo), max(prior[1], hi))
            total_rows += len(frame)
            first = ['Datetime','Symbol','Timeframe'] + price_cols
            columns = first + [c for c in frame if c not in first]
            if not raw:
                for name,mask in [('first_half',frame.Datetime.lt(split_at)),('second_half',frame.Datetime.ge(split_at))]:
                    portion=frame.loc[mask]
                    if not portion.empty:
                        portion.to_csv(half_files[name],columns=columns,index=False,mode='a',header=not half_files[name].exists(),chunksize=2000)
                        half_rows[name]+=len(portion)
            frame.to_csv(csv_file, columns=columns, index=False, mode='a', header=not csv_file.exists(), chunksize=2000,
                         date_format='%Y-%m-%d %H:%M:%S')
            if on_progress:
                on_progress(index + 1, len(periods), total_rows)
            del frame
        if raw and (partial_ok or gap_ok):
            if not seen_symbols or not total_rows:
                raise RuntimeError('Export has no symbols or valid rows')
        elif seen_symbols != expected or not total_rows:
            raise RuntimeError('Export missing requested symbols or valid rows')
        short_symbols: list[str] = []
        if raw and is_raw_ohlc_kind(job.get('kind')):
            # Allow market closures at the endpoints; reject a short provider
            # history being presented as a complete ten-year download.
            tolerance = pd.Timedelta(days=7)
            short_symbols = [s for s, (lo, hi) in symbol_coverage.items()
                             if lo > start + tolerance or hi < end - tolerance]
            if short_symbols and not (partial_ok or gap_ok):
                raise RuntimeError('TEN_YEAR_HISTORY_UNAVAILABLE for ' + ', '.join(sorted(short_symbols))
                                   + ': provider candles do not cover the requested dates. Check historical data access.')
        gap_ranges = _job_gap_ranges(job) if raw else {}
        coverage_note = _raw_coverage_note(job, expected, seen_symbols, symbol_coverage, short_symbols, gap_ranges) if raw else ""
        path = f"finder/{job['id']}/{'raw_ohlc' if raw else 'middle_ranking'}_{job['timeframe']}_{int(job['history_years'])}y{'_partial' if (raw and partial_ok) else ''}.csv"
        store.put_file(path, csv_file, content_type='text/csv')
        half_artifacts=[]
        if not raw:
            if sum(half_rows.values())!=total_rows: raise RuntimeError('HALF_EXPORT_ROW_COUNT_MISMATCH')
            for name,file in half_files.items():
                # Degenerate tiny ranges still produce a readable empty half.
                if not file.exists(): pd.DataFrame(columns=columns).to_csv(file,index=False)
                half_path=f"finder/{job['id']}/middle_ranking_{job['timeframe']}_2y_{name}.csv"
                store.put_file(half_path,file,content_type='text/csv')
                half_artifacts.append(dict(kind='middle_ranking_'+name+'_csv',path=half_path,rows=half_rows[name],bytes=file.stat().st_size,
                    timeframe=job['timeframe'],strategy_engine=STRATEGY_ENGINE_VERSION,strict_only=bool(job.get("strict_only",False)),symbol_count=len(expected),split_at=split_at.isoformat(),fingerprint=digest,export_scope='ALL_SYMBOLS_ALL_CANDLES_HALF'))
        if not raw:
            for name in ('equation_column_map.json','equation_column_map.csv'):
                mapping_path=f"finder/{job['id']}/{name}"
                store.put_object(mapping_path,(ROOT/name).read_bytes(),content_type='application/json' if name.endswith('json') else 'text/csv')
                manifest.append(dict(kind='equation_mapping',path=mapping_path,strategy_engine=STRATEGY_ENGINE_VERSION))
        artifact = dict(kind=kind, path=path, rows=total_rows, bytes=csv_file.stat().st_size,
                        history_years=job['history_years'], timeframe=job['timeframe'], strategy_engine=STRATEGY_ENGINE_VERSION,
                        symbol_count=len(seen_symbols), rows_per_hour=len(expected), hourly_population=histogram,
                        continuous_ohlc=True, export_scope='ALL_SYMBOLS_ALL_CANDLES',
                        entry_filter_relaxation_percent=ENTRY_FILTER_RELAXATION*100, hourly_top_n=4, fingerprint=digest,
                        oldest=job['start_date'], newest=job['end_date'],
                        partial=bool(raw and partial_ok),
                        missing_symbols=list(missing_symbols),
                        provider_coverage_short=bool(short_symbols),
                        short_symbols=sorted(short_symbols),
                        gap_ranges=gap_ranges,
                        coverage_note=coverage_note)
        if symbol_coverage:
            artifact['symbol_coverage'] = {s: {'oldest': lo.isoformat(), 'newest': hi.isoformat()}
                                           for s, (lo, hi) in symbol_coverage.items()}
    drop_kinds = {kind} if raw else {kind, 'ranking_part'}
    if raw and not partial_ok:
        # Publishing the full CSV supersedes any earlier partial export.
        drop_kinds.add('raw_ohlc_partial_csv')
    manifest[:] = [a for a in manifest if a.get('kind') not in drop_kinds]
    if not raw:
        half_kinds={a['kind'] for a in half_artifacts}
        manifest[:]=[a for a in manifest if a.get('kind') not in half_kinds]
        manifest.extend(half_artifacts)
    manifest.extend(master_parts)
    manifest.append(artifact)
    return artifact
