# Future-upgrade split module.
# Safe metric/risk re-exports from unchanged implementation.

try:
    from .implementation import _risk_status, _metric_status
except Exception:
    def _risk_status(label, value):
        try:
            v = float(value or 0)
        except Exception:
            v = 0.0
        label = str(label or '').lower()
        if label == 'margin_level':
            if v <= 0: return 'UNKNOWN', 'No margin level yet'
            if v >= 500: return 'VERY GOOD', 'Large margin buffer'
            if v >= 250: return 'GOOD', 'Healthy margin buffer'
            if v >= 150: return 'BAD', 'Margin getting tight'
            return 'DANGEROUS', 'Margin call danger zone'
        if label == 'drawdown':
            if v <= 3: return 'VERY GOOD', 'Very low drawdown'
            if v <= 8: return 'GOOD', 'Normal drawdown'
            if v <= 15: return 'BAD', 'Reduce risk'
            return 'DANGEROUS', 'High drawdown'
        if label == 'floating_pl':
            return ('GOOD', 'Floating profit') if v >= 0 else ('BAD', 'Floating loss')
        return 'GOOD', 'Normal'

    def _metric_status(col, label, value, status_key=None):
        status, note = _risk_status(status_key or str(label).lower(), value)
        col.metric(label, value)
        col.caption(f'{status}: {note}')


def _risk_badge_text(label, value):
    status, note = _risk_status(label, value)
    return f'{status}: {note}'

__all__ = ['_risk_status', '_metric_status', '_risk_badge_text']
