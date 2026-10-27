"""Cached FRED macro provider and normalized USD/EURUSD pressure summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import json
import sqlite3

import pandas as pd
import requests

from core.data.deployment_migrations_20260705 import DEFAULT_DB_PATH, migrate_deployment_schema

DEFAULT_SERIES: dict[str, str] = {
    "FED_FUNDS": "FEDFUNDS",
    "CPI": "CPIAUCSL",
    "CORE_CPI": "CPILFESL",
    "PCE": "PCEPI",
    "CORE_PCE": "PCEPILFE",
    "UNEMPLOYMENT": "UNRATE",
    "JOBLESS_CLAIMS": "ICSA",
    "TREASURY_2Y": "DGS2",
    "TREASURY_10Y": "DGS10",
    "FINANCIAL_STRESS": "STLFSI4",
    "INDUSTRIAL_ACTIVITY": "INDPRO",
    "GDP": "GDPC1",
    "INFLATION_EXPECTATIONS": "T10YIE",
}


class FredMacroProvider:
    def __init__(self, db_path: str | Path | None = None, *, session: requests.Session | None = None) -> None:
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        migrate_deployment_schema(self.db_path)
        self.session = session or requests.Session()

    @staticmethod
    def _key(state: Mapping[str, Any]) -> str:
        try:
            from core.secure_api_startup_20260619 import resolve_api_key
            return str(resolve_api_key("fred", state) or "").strip()
        except Exception:
            return str(state.get("fred_api_key") or "").strip()

    def _latest_fetched(self, series_id: str) -> datetime | None:
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            row = conn.execute(
                "SELECT MAX(fetched_at) FROM macro_observations WHERE provider='FRED' AND series_id=?",
                (series_id,),
            ).fetchone()
        if not row or not row[0]:
            return None
        try:
            value = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def load_series(self, series_id: str, *, limit: int = 60) -> pd.DataFrame:
        with sqlite3.connect(str(self.db_path), timeout=10) as conn:
            frame = pd.read_sql_query(
                """SELECT observation_date,value,release_at,fetched_at,freshness_status
                   FROM macro_observations WHERE provider='FRED' AND series_id=?
                   ORDER BY observation_date DESC LIMIT ?""",
                conn, params=(series_id, int(limit)),
            )
        return frame.sort_values("observation_date").reset_index(drop=True) if not frame.empty else frame

    def fetch_series(
        self,
        series_id: str,
        *,
        state: Mapping[str, Any] | None = None,
        force: bool = False,
        ttl_hours: int = 12,
        observation_start: str | None = None,
    ) -> dict[str, Any]:
        state = state if isinstance(state, Mapping) else {}
        last = self._latest_fetched(series_id)
        if not force and last and datetime.now(timezone.utc) - last.astimezone(timezone.utc) < timedelta(hours=ttl_hours):
            frame = self.load_series(series_id)
            return {"ok": not frame.empty, "status": "CACHED_VALID", "series_id": series_id, "frame": frame}
        key = self._key(state)
        if not key:
            frame = self.load_series(series_id)
            return {"ok": not frame.empty, "status": "CACHED_VALID" if not frame.empty else "INSUFFICIENT", "series_id": series_id, "frame": frame, "message": "FRED key is not configured."}
        params = {
            "series_id": series_id, "api_key": key, "file_type": "json",
            "sort_order": "desc", "limit": 120,
        }
        if observation_start:
            params["observation_start"] = observation_start
        response = self.session.get("https://api.stlouisfed.org/fred/series/observations", params=params, timeout=25)
        response.raise_for_status()
        payload = response.json()
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for observation in payload.get("observations", []) or []:
            raw = observation.get("value")
            try:
                value = float(raw)
            except Exception:
                value = None
            rows.append((
                "FRED", series_id, str(observation.get("date") or ""), value,
                str(observation.get("realtime_start") or ""), now, "CURRENT", json.dumps(observation),
            ))
        with sqlite3.connect(str(self.db_path), timeout=20) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.executemany(
                """INSERT INTO macro_observations(provider,series_id,observation_date,value,release_at,fetched_at,freshness_status,payload_json)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(provider,series_id,observation_date) DO UPDATE SET
                   value=excluded.value,release_at=excluded.release_at,fetched_at=excluded.fetched_at,
                   freshness_status=excluded.freshness_status,payload_json=excluded.payload_json""",
                rows,
            )
            conn.commit()
        frame = self.load_series(series_id)
        return {"ok": not frame.empty, "status": "LIVE_PRIMARY" if rows else "INSUFFICIENT", "series_id": series_id, "frame": frame, "rows": len(rows)}

    @staticmethod
    def _z_direction(frame: pd.DataFrame, *, positive_usd: bool = True) -> tuple[float | None, float]:
        if frame.empty:
            return None, 0.0
        values = pd.to_numeric(frame["value"], errors="coerce").dropna()
        if len(values) < 2:
            return None, 20.0
        change = float(values.iloc[-1] - values.iloc[-2])
        scale = float(values.tail(min(12, len(values))).std()) or max(abs(float(values.iloc[-1])), 1.0) * 0.01
        score = max(-100.0, min(100.0, 35.0 * change / scale))
        return (score if positive_usd else -score), min(100.0, 40.0 + len(values))

    def collect(
        self,
        state: Mapping[str, Any] | None = None,
        *,
        force: bool = False,
        series: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        definitions = dict(series or DEFAULT_SERIES)
        reports: dict[str, Any] = {}
        frames: dict[str, pd.DataFrame] = {}
        for name, series_id in definitions.items():
            report = self.fetch_series(series_id, state=state, force=force)
            reports[name] = {k: v for k, v in report.items() if k != "frame"}
            frames[name] = report.get("frame") if isinstance(report.get("frame"), pd.DataFrame) else pd.DataFrame()
        components: dict[str, float] = {}
        reliabilities: list[float] = []
        mapping = {
            "FED_FUNDS": True, "CPI": True, "CORE_CPI": True, "PCE": True, "CORE_PCE": True,
            "UNEMPLOYMENT": False, "JOBLESS_CLAIMS": False, "TREASURY_2Y": True, "TREASURY_10Y": True,
            "FINANCIAL_STRESS": False, "INDUSTRIAL_ACTIVITY": True, "GDP": True, "INFLATION_EXPECTATIONS": True,
        }
        for name, positive_usd in mapping.items():
            score, reliability = self._z_direction(frames.get(name, pd.DataFrame()), positive_usd=positive_usd)
            if score is not None:
                components[name] = score
                reliabilities.append(reliability)
        usd_pressure = sum(components.values()) / len(components) if components else None
        # USD-positive pressure is EURUSD-negative. European pressure remains
        # sourced from the project's existing cached ECB/Eurostat inputs.
        eur_pressure = state.get("eur_macro_pressure") if isinstance(state, Mapping) else None
        try:
            eur_pressure = float(eur_pressure) if eur_pressure is not None else 0.0
        except Exception:
            eur_pressure = 0.0
        net = (eur_pressure - usd_pressure) if usd_pressure is not None else None
        return {
            "status": "VALID" if components else "INSUFFICIENT",
            "provider": "FRED",
            "series": reports,
            "components": components,
            "eur_macro_pressure": eur_pressure if components else None,
            "usd_macro_pressure": usd_pressure,
            "rate_differential_pressure": components.get("FED_FUNDS") or components.get("TREASURY_2Y"),
            "inflation_pressure": self._average(components, ("CPI", "CORE_CPI", "PCE", "CORE_PCE", "INFLATION_EXPECTATIONS")),
            "labor_pressure": self._average(components, ("UNEMPLOYMENT", "JOBLESS_CLAIMS")),
            "growth_pressure": self._average(components, ("GDP", "INDUSTRIAL_ACTIVITY")),
            "risk_off_pressure": components.get("FINANCIAL_STRESS"),
            "net_eurusd_macro_bias": net,
            "macro_uncertainty": max(0.0, 100.0 - (sum(reliabilities) / len(reliabilities) if reliabilities else 0.0)),
            "macro_reliability": sum(reliabilities) / len(reliabilities) if reliabilities else 0.0,
        }

    @staticmethod
    def _average(values: Mapping[str, float], names: Sequence[str]) -> float | None:
        selected = [float(values[name]) for name in names if name in values]
        return sum(selected) / len(selected) if selected else None


__all__ = ["DEFAULT_SERIES", "FredMacroProvider"]
