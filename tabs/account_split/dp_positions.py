# Future-upgrade split module.
# Safe position helper re-exports from unchanged implementation.

try:
    from .implementation import (
        _position_to_dict,
        _guess_pip_size,
        _calc_pips,
        _positions_frame,
        _position_profit_summary,
    )
except Exception:
    import pandas as pd
    import numpy as np

    def _safe_num(v, default=0.0):
        try:
            v = float(v)
            return v if np.isfinite(v) else default
        except Exception:
            return default

    def _position_to_dict(pos):
        if isinstance(pos, dict):
            return pos
        if hasattr(pos, '_asdict'):
            try:
                return pos._asdict()
            except Exception:
                pass
        try:
            return dict(pos)
        except Exception:
            pass
        out = {}
        for key in dir(pos):
            if key.startswith('_'):
                continue
            try:
                value = getattr(pos, key)
                if not callable(value):
                    out[key] = value
            except Exception:
                pass
        return out

    def _guess_pip_size(symbol, price=None):
        symbol = str(symbol or '').upper()
        price = _safe_num(price)
        if 'JPY' in symbol:
            return 0.01
        if 'XAU' in symbol or 'GOLD' in symbol:
            return 0.1
        if 'XAG' in symbol or 'SILVER' in symbol:
            return 0.01
        if 'BTC' in symbol or 'ETH' in symbol:
            return 1.0
        return 0.01 if price >= 100 else 0.0001

    def _calc_pips(row):
        price_open = _safe_num(row.get('price_open'))
        price_current = _safe_num(row.get('price_current'))
        side = str(row.get('side', '')).upper()
        if price_open <= 0 or price_current <= 0:
            return 0.0
        pip = _guess_pip_size(row.get('symbol', ''), price_open)
        return round(((price_open - price_current) if side == 'SELL' else (price_current - price_open)) / pip, 1)

    def _positions_frame(info):
        positions = info.get('positions', []) if isinstance(info, dict) else []
        if not positions:
            return pd.DataFrame()
        df = pd.DataFrame([_position_to_dict(p) for p in positions])
        if df.empty:
            return df
        for c in ['profit', 'volume', 'price_open', 'price_current', 'swap', 'commission']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
        if 'type' in df.columns:
            df['side'] = df['type'].map({0: 'BUY', 1: 'SELL'}).fillna(df['type'].astype(str))
        elif 'side' not in df.columns:
            df['side'] = 'UNKNOWN'
        if 'price_open' in df.columns and 'price_current' in df.columns:
            df['pips'] = df.apply(_calc_pips, axis=1)
        return df

    def _position_profit_summary(info):
        df = _positions_frame(info)
        if df.empty or 'profit' not in df.columns:
            return {'buy_pl': 0.0, 'sell_pl': 0.0, 'net_pl': 0.0, 'profit_count': 0, 'loss_count': 0, 'frame': df}
        side = df.get('side', pd.Series(['UNKNOWN'] * len(df))).astype(str).str.upper()
        profit = pd.to_numeric(df['profit'], errors='coerce').fillna(0)
        return {
            'buy_pl': round(float(profit[side == 'BUY'].sum()), 2),
            'sell_pl': round(float(profit[side == 'SELL'].sum()), 2),
            'net_pl': round(float(profit.sum()), 2),
            'profit_count': int((profit > 0).sum()),
            'loss_count': int((profit < 0).sum()),
            'frame': df,
        }

__all__ = ['_position_to_dict', '_guess_pip_size', '_calc_pips', '_positions_frame', '_position_profit_summary']
