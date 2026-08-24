"""MFE/MAE summary from settled outcome records."""
from __future__ import annotations
from typing import Any, Iterable, Mapping
from research._utils import number


def evaluate(rows: Iterable[Mapping[str, Any]], horizon: int) -> dict[str, Any]:
    selected = [row for row in rows if int(number(row.get("horizon_hours"), horizon) or horizon) == horizon]
    mfe = [number(row.get("mfe_pips"), None) for row in selected]
    mae = [number(row.get("mae_pips"), None) for row in selected]
    mfe = [value for value in mfe if value is not None]
    mae = [value for value in mae if value is not None]
    return {"horizon_hours": horizon, "median_mfe_pips": sorted(mfe)[len(mfe)//2] if mfe else None, "median_mae_pips": sorted(mae)[len(mae)//2] if mae else None, "sample_size": len(selected), "status": "READY" if len(selected) >= 25 else "INSUFFICIENT EVIDENCE"}
