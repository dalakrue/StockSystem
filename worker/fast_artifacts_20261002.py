"""Bounded-memory finalization; all-symbol hourly selection keeps causal state."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
import hashlib
import json
import tempfile
import pandas as pd
import pyarrow.parquet as pq
from core.resumable_build_20260928 import COMPACT_FINDER_COLUMNS, normalize_symbol, put_dataframe
from core.strategy_audit_20260924 import STRATEGY_ENGINE_VERSION
from core.hourly_four_symbol_selector_20260928 import attach_hourly_four_selection


class ArtifactCorruptionError(RuntimeError):
    def __init__(self, path, symbol, cause):
        super().__init__(f'Cached Parquet is unreadable for {symbol}: {type(cause).__name__}')
        self.path, self.symbol = path, symbol


def fingerprint(job, artifacts, kind):
    spec = {key: job.get(key) for key in ('symbols', 'timeframe', 'start_date', 'end_date', 'version')}
    spec.update(engine=STRATEGY_ENGINE_VERSION, kind=kind,
                inputs=[(a.get('path'), a.get('rows'), a.get('bytes')) for a in artifacts])
    return hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()


def finalize(job, store, manifest, *, raw=False, on_progress=None, should_stop=None):
    kind = 'raw_ohlc_csv' if raw else 'middle_ranking_csv'
    sources = [a for a in manifest if a.get('kind') == ('candle_chunk' if raw else 'finder_symbol')]
    if not sources:
        raise RuntimeError('No source artifacts for ' + kind)
    digest = fingerprint(job, sources, kind)
    for artifact in manifest:
        if artifact.get('kind') == kind and artifact.get('fingerprint') == digest and store.object_exists(artifact['path']):
            return artifact
    expected = {normalize_symbol(s) for s in job['symbols']}
    if {normalize_symbol(a.get('symbol')) for a in sources} != expected:
        raise RuntimeError('ALL_SYMBOL_EXPORT_UNIVERSE_MISMATCH')
    start, end = pd.Timestamp(job['start_date']), pd.Timestamp(job['end_date'])
    coverage_state = {}
    exit_state = {}
    total_rows = 0
    seen_symbols = set()
    histogram = {}
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
                    columns = [c for c in ['open_time', 'open', 'high', 'low', 'close', 'volume'] if c in names]
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
                from core.hourly_four_symbol_selector_20260928 import ENTRY_FILTER_RELAXATION
                frame['Entry Filter Relaxation Percent'] = ENTRY_FILTER_RELAXATION * 100
                score_columns = [f'S{i} Score' for i in range(1, 121) if f'S{i} Score' in frame]
                if score_columns and 'Best Strategy' not in frame:
                    frame['Best Strategy'] = frame[score_columns].idxmax(axis=1).str.removesuffix(' Score')
                frame['Continuous OHLC Row'] = True
                frame['Finder Export Scope'] = 'ALL_SYMBOLS_ALL_CANDLES'
                n = frame.groupby('Datetime')['Symbol'].nunique()
                selected = frame.groupby('Datetime')['Hourly 4 Entry'].sum()
                if not selected.eq(n.clip(upper=4)).all():
                    raise RuntimeError('Hourly selection count mismatch')
                master_path = f"finder/{job['id']}/ranked/part-{index:04d}.parquet"
                saved = put_dataframe(store, master_path, frame)
                master_parts.append(dict(saved, kind='ranking_part', oldest=frame['Datetime'].min().isoformat(), newest=frame['Datetime'].max().isoformat()))
            counts = frame.groupby('Datetime')['Symbol'].nunique().value_counts()
            for count, hours in counts.items():
                histogram[str(count)] = histogram.get(str(count), 0) + int(hours)
            seen_symbols.update(frame['Symbol'].astype(str).map(normalize_symbol))
            total_rows += len(frame)
            first = ['Datetime','Symbol','Timeframe'] + price_cols
            columns = first + [c for c in frame if c not in first]
            frame.to_csv(csv_file, columns=columns, index=False, mode='a', header=not csv_file.exists(), chunksize=2000,
                         date_format='%Y-%m-%d %H:%M:%S')
            if on_progress:
                on_progress(index + 1, len(periods), total_rows)
            del frame
        if seen_symbols != expected or not total_rows:
            raise RuntimeError('Export missing requested symbols or valid rows')
        path = f"finder/{job['id']}/{'raw_ohlc' if raw else 'middle_ranking'}_{job['timeframe']}_2y.csv"
        store.put_file(path, csv_file, content_type='text/csv')
        artifact = dict(kind=kind, path=path, rows=total_rows, bytes=csv_file.stat().st_size,
                        history_years=job['history_years'], timeframe=job['timeframe'], strategy_engine=STRATEGY_ENGINE_VERSION,
                        symbol_count=len(expected), rows_per_hour=len(expected), hourly_population=histogram,
                        continuous_ohlc=True, export_scope='ALL_SYMBOLS_ALL_CANDLES',
                        entry_filter_relaxation_percent=40, hourly_top_n=4, fingerprint=digest,
                        oldest=job['start_date'], newest=job['end_date'])
    manifest[:] = [a for a in manifest if a.get('kind') not in {kind, *([] if raw else ['ranking_part'])}]
    manifest.extend(master_parts)
    manifest.append(artifact)
    return artifact
