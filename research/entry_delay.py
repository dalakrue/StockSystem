"""Entry-delay outcome comparison; H1 remains the directional source."""
from __future__ import annotations
from collections import Counter
from statistics import median
from typing import Any, Iterable, Mapping

from research._utils import number

DELAYS = ("Immediate entry", "M15 confirmation", "M30 confirmation", "Next H1 candle", "Skip")


def _mode(values: list[str]) -> str | None:
    return Counter(values).most_common(1)[0][0] if values else None


def evaluate(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [dict(row) for row in rows if isinstance(row, Mapping)]
    has_delay_labels = any(str(row.get("entry_delay") or "").strip() for row in records)
    output: list[dict[str, Any]] = []
    for delay in DELAYS:
        if has_delay_labels:
            subset = [row for row in records if str(row.get("entry_delay") or "").casefold() == delay.casefold()]
        elif delay == "Immediate entry":
            subset = records
        else:
            subset = []
        wins = [number(row.get("direction_correct"), None) for row in subset]
        wins = [value for value in wins if value is not None]
        realized = [number(row.get("realized_pips"), None) for row in subset]
        realized = [value for value in realized if value is not None]
        costs = [number(row.get("estimated_cost"), 0.0) or 0.0 for row in subset]
        maes = [number(row.get("mae_pips"), None) for row in subset]
        maes = [value for value in maes if value is not None]
        missed = [number(row.get("missed_trade"), None) for row in subset]
        missed = [value for value in missed if value is not None]
        sessions = [str(row.get("session")) for row in subset if row.get("session")]
        regimes = [str(row.get("regime")) for row in subset if row.get("regime")]
        count = len(subset)
        output.append({
            "delay_name": delay,
            "win_rate": round(sum(wins) / len(wins) * 100.0, 3) if wins else None,
            "net_ev": round(sum(realized) / len(realized) - (sum(costs) / len(costs) if costs else 0.0), 4) if realized else None,
            "mae": round(median(maes), 4) if maes else None,
            "missed_trade_rate": round(sum(missed) / len(missed) * 100.0, 3) if missed else None,
            "best_session": _mode(sessions),
            "best_regime": _mode(regimes),
            "evidence_count": count,
            "status": "RESEARCH READY" if count >= 25 else "INSUFFICIENT EVIDENCE",
        })
    return output
