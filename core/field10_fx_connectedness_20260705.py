"""Currency-leg-aware copula and asymmetric/frequency connectedness evidence."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations
from typing import Any
import math

import numpy as np
import pandas as pd

from core.field10_research_common_20260705 import MAX_SYMBOL_UNIVERSE, direction_sign, finite

VERSION = "field10-fx-connectedness-20260705-v1"
FREQUENCY_MAPPING_VERSION = "field10-bk-frequency-map-20260705-v1"
FREQUENCY_BANDS = {
    # Hourly observations have a Nyquist limit of 2 hours. The short band is
    # therefore an explicit approximately-2H-to-6H adaptation of the requested
    # 1H-6H economic horizon.
    "short": {"minimum_period_hours": 2.0, "maximum_period_hours": 6.0},
    "medium": {"minimum_period_hours": 6.0, "maximum_period_hours": 24.0},
    "persistent": {"minimum_period_hours": 24.0, "maximum_period_hours": 120.0},
}


def fx_currency_legs(symbol: str, bias: str) -> dict[str, float]:
    text = str(symbol or "").upper().replace("/", "").strip()
    sign = direction_sign(bias)
    if len(text) != 6 or not text.isalpha() or sign == 0:
        return {}
    base, quote = text[:3], text[3:]
    return {base: float(sign), quote: float(-sign)}


def duplicate_currency_exposure(symbol_a: str, bias_a: str, symbol_b: str, bias_b: str) -> dict[str, Any]:
    a, b = fx_currency_legs(symbol_a, bias_a), fx_currency_legs(symbol_b, bias_b)
    currencies = sorted(set(a) | set(b))
    if not a or not b:
        return {"cosine": None, "shared_currency_count": 0, "duplicate_directional_exposure": None, "legs_a": a, "legs_b": b}
    va = np.array([a.get(c, 0.0) for c in currencies], dtype=float)
    vb = np.array([b.get(c, 0.0) for c in currencies], dtype=float)
    denominator = float(np.linalg.norm(va) * np.linalg.norm(vb))
    cosine = None if denominator <= 0 else float(np.dot(va, vb) / denominator)
    shared = len(set(a) & set(b))
    return {
        "cosine": cosine, "shared_currency_count": shared,
        "duplicate_directional_exposure": None if cosine is None else max(0.0, cosine),
        "legs_a": a, "legs_b": b,
    }


def aligned_return_panel(frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    series: list[pd.Series] = []
    for symbol in sorted(frames)[:MAX_SYMBOL_UNIVERSE]:
        frame = frames[symbol]
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            continue
        close = pd.to_numeric(frame["close"], errors="coerce")
        time = pd.to_datetime(frame["time"], errors="coerce", utc=True)
        ret = pd.Series(np.log(close / close.shift(1)).to_numpy(), index=time, name=symbol)
        series.append(ret[~ret.index.duplicated(keep="last")])
    if not series:
        return pd.DataFrame()
    panel = pd.concat(series, axis=1, join="inner").replace([np.inf, -np.inf], np.nan).dropna()
    return panel.tail(600)


def _ewma_correlation(a: np.ndarray, b: np.ndarray, decay: float = 0.97) -> float | None:
    if len(a) < 30 or len(a) != len(b):
        return None
    weights = np.power(decay, np.arange(len(a) - 1, -1, -1, dtype=float))
    weights /= weights.sum()
    ma, mb = float(np.sum(weights * a)), float(np.sum(weights * b))
    da, db = a - ma, b - mb
    covariance = float(np.sum(weights * da * db))
    variance = float(np.sum(weights * da * da) * np.sum(weights * db * db))
    return None if variance <= 1e-18 else float(np.clip(covariance / math.sqrt(variance), -0.999, 0.999))


def conditional_copula_evidence(panel: pd.DataFrame, biases: Mapping[str, str]) -> dict[str, Any]:
    if not isinstance(panel, pd.DataFrame) or panel.shape[0] < 80 or panel.shape[1] < 2:
        return {"status": "INSUFFICIENT_ALIGNED_RETURNS", "version": VERSION, "pairs": [], "symbols": {}}
    symbols = sorted(panel.columns)[:MAX_SYMBOL_UNIVERSE]
    pair_rows: list[dict[str, Any]] = []
    for a, b in combinations(symbols, 2):
        sample = panel[[a, b]].dropna().tail(360)
        xa, xb = sample[a].to_numpy(float), sample[b].to_numpy(float)
        ordinary = _ewma_correlation(xa, xb)
        qa_low, qb_low = np.quantile(xa, 0.10), np.quantile(xb, 0.10)
        qa_high, qb_high = np.quantile(xa, 0.90), np.quantile(xb, 0.90)
        lower_joint = float(np.mean((xa <= qa_low) & (xb <= qb_low)))
        upper_joint = float(np.mean((xa >= qa_high) & (xb >= qb_high)))
        lower_tail = float(np.clip(lower_joint / 0.10, 0.0, 1.0))
        upper_tail = float(np.clip(upper_joint / 0.10, 0.0, 1.0))
        sign_a, sign_b = direction_sign(biases.get(a)), direction_sign(biases.get(b))
        strategy_a, strategy_b = sign_a * xa, sign_b * xb
        adverse = float(np.mean((strategy_a < 0) & (strategy_b < 0))) if sign_a and sign_b else None
        favorable = float(np.mean((strategy_a > 0) & (strategy_b > 0))) if sign_a and sign_b else None
        first = _ewma_correlation(xa[: len(xa)//2], xb[: len(xb)//2])
        second = _ewma_correlation(xa[len(xa)//2 :], xb[len(xb)//2 :])
        instability = None if first is None or second is None else abs(second - first)
        exposure = duplicate_currency_exposure(a, biases.get(a, "WAIT"), b, biases.get(b, "WAIT"))
        regime = "LOWER_TAIL_DOMINANT" if lower_tail > upper_tail + 0.10 else "UPPER_TAIL_DOMINANT" if upper_tail > lower_tail + 0.10 else "BALANCED_TAILS"
        pair_rows.append({
            "symbol": a, "peer_symbol": b, "ordinary_conditional_dependence": ordinary,
            "lower_tail_dependence": lower_tail, "upper_tail_dependence": upper_tail,
            "joint_adverse_move_probability": adverse, "joint_favorable_move_probability": favorable,
            "dependence_regime": regime, "dependence_instability": instability,
            "duplicate_currency_exposure": exposure.get("duplicate_directional_exposure"),
            "currency_leg_detail": exposure, "sample_count": int(len(sample)),
            "copula_validation_status": "EMPIRICAL_ASYMMETRIC_CONDITIONAL_COPULA_ADAPTATION",
        })
    aggregated: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        related = [r for r in pair_rows if r["symbol"] == symbol or r["peer_symbol"] == symbol]
        dup = [finite(r.get("duplicate_currency_exposure")) for r in related]
        adverse = [finite(r.get("joint_adverse_move_probability")) for r in related]
        instability = [finite(r.get("dependence_instability")) for r in related]
        dup = [v for v in dup if v is not None]
        adverse = [v for v in adverse if v is not None]
        instability = [v for v in instability if v is not None]
        duplicate_penalty = None if not dup else float(100.0 * np.mean(dup))
        crowding = None if not adverse else float(100.0 * np.mean(adverse))
        currency_crowding = None if not dup else float(100.0 * max(dup))
        diversification = None if duplicate_penalty is None or crowding is None else float(np.clip(100.0 - 0.60 * duplicate_penalty - 0.40 * crowding, 0.0, 100.0))
        aggregated[symbol] = {
            "duplicate_exposure_penalty": duplicate_penalty,
            "tail_crowding_penalty": crowding,
            "diversification_quality": diversification,
            "currency_leg_crowding": currency_crowding,
            "dependence_instability": None if not instability else float(np.mean(instability)),
            "copula_validation_status": "AVAILABLE" if related else "UNAVAILABLE",
            "pair_count": len(related),
        }
    return {"status": "AVAILABLE", "version": VERSION, "pairs": pair_rows, "symbols": aggregated}


def _fit_var1(panel: pd.DataFrame, ridge: float = 1e-5) -> tuple[np.ndarray, np.ndarray, list[str]] | None:
    clean = panel.replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < max(80, clean.shape[1] * 8) or clean.shape[1] < 2:
        return None
    standardized = (clean - clean.mean()) / clean.std(ddof=1).replace(0, np.nan)
    standardized = standardized.dropna()
    x = standardized.iloc[:-1].to_numpy(float)
    y = standardized.iloc[1:].to_numpy(float)
    design = np.column_stack([np.ones(len(x)), x])
    penalty = np.eye(design.shape[1]) * ridge
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    a = beta[1:].T
    eigen = np.max(np.abs(np.linalg.eigvals(a)))
    if math.isfinite(float(eigen)) and eigen >= 0.995:
        a *= 0.995 / float(eigen)
    residual = y - design @ beta
    sigma = np.cov(residual, rowvar=False, ddof=1)
    if np.ndim(sigma) == 0:
        sigma = np.eye(clean.shape[1]) * float(sigma)
    sigma = np.asarray(sigma, dtype=float) + np.eye(clean.shape[1]) * 1e-8
    return a, sigma, list(clean.columns)


def _generalized_fevd(a: np.ndarray, sigma: np.ndarray, horizon: int = 12) -> np.ndarray:
    n = a.shape[0]
    numerators = np.zeros((n, n), dtype=float)
    denominators = np.zeros(n, dtype=float)
    power = np.eye(n)
    for _ in range(max(1, int(horizon))):
        hs = power @ sigma
        covariance = hs @ power.T
        denominators += np.diag(covariance)
        for j in range(n):
            for k in range(n):
                numerators[j, k] += (hs[j, k] ** 2) / max(sigma[k, k], 1e-12)
        power = power @ a
    theta = numerators / np.maximum(denominators[:, None], 1e-12)
    return theta / np.maximum(theta.sum(axis=1, keepdims=True), 1e-12)


def _directional_rows(theta: np.ndarray, symbols: Sequence[str], prefix: str) -> dict[str, dict[str, float]]:
    n = len(symbols)
    result: dict[str, dict[str, float]] = {}
    for i, symbol in enumerate(symbols):
        received = float(100.0 * (theta[i, :].sum() - theta[i, i]) / max(n - 1, 1))
        transmitted = float(100.0 * (theta[:, i].sum() - theta[i, i]) / max(n - 1, 1))
        result[symbol] = {
            f"{prefix}_received": received,
            f"{prefix}_transmitted": transmitted,
            f"net_{prefix}_spillover": transmitted - received,
        }
    return result


def asymmetric_connectedness(panel: pd.DataFrame) -> dict[str, Any]:
    if panel.empty or panel.shape[1] < 2:
        return {"status": "INSUFFICIENT_PANEL", "version": VERSION, "symbols": {}}
    positive = panel.clip(lower=0.0).pow(2)
    negative = panel.clip(upper=0.0).pow(2)
    fit_bad = _fit_var1(negative)
    fit_good = _fit_var1(positive)
    if fit_bad is None or fit_good is None:
        return {"status": "INSUFFICIENT_VAR_SAMPLE", "version": VERSION, "symbols": {}}
    a_bad, s_bad, symbols = fit_bad
    a_good, s_good, symbols_good = fit_good
    if symbols != symbols_good:
        return {"status": "PANEL_IDENTITY_MISMATCH", "version": VERSION, "symbols": {}}
    bad = _directional_rows(_generalized_fevd(a_bad, s_bad, 12), symbols, "bad_volatility")
    good = _directional_rows(_generalized_fevd(a_good, s_good, 12), symbols, "good_volatility")
    rows: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        row = {**bad[symbol], **good[symbol]}
        bad_received = row["bad_volatility_received"]
        bad_transmitted = row["bad_volatility_transmitted"]
        row.update({
            "stress_receiver_status": "HIGH" if bad_received >= 60 else "MODERATE" if bad_received >= 35 else "LOW",
            "stress_transmitter_status": "HIGH" if bad_transmitted >= 60 else "MODERATE" if bad_transmitted >= 35 else "LOW",
            "adverse_connectedness_score": float(np.clip(0.65 * bad_received + 0.35 * max(0.0, -row["net_bad_volatility_spillover"]), 0.0, 100.0)),
            "contagion_safety_permission": "BLOCK" if bad_received >= 75 else "CAUTION" if bad_received >= 50 else "ALLOW",
        })
        rows[symbol] = row
    return {"status": "AVAILABLE", "version": VERSION, "symbols": rows, "sample_count": int(len(panel))}


def _spectral_theta(a: np.ndarray, sigma: np.ndarray, omega: float) -> np.ndarray:
    n = a.shape[0]
    transfer = np.linalg.inv(np.eye(n, dtype=complex) - a.astype(complex) * np.exp(-1j * omega))
    hs = transfer @ sigma
    spectral = transfer @ sigma @ transfer.conj().T
    theta = np.zeros((n, n), dtype=float)
    for j in range(n):
        denominator = max(float(np.real(spectral[j, j])), 1e-12)
        for k in range(n):
            theta[j, k] = float((abs(hs[j, k]) ** 2) / max(sigma[k, k], 1e-12) / denominator)
    return theta


def frequency_connectedness(panel: pd.DataFrame, *, grid_size: int = 512) -> dict[str, Any]:
    fit = _fit_var1(panel)
    if fit is None:
        return {"status": "INSUFFICIENT_VAR_SAMPLE", "version": VERSION, "mapping_version": FREQUENCY_MAPPING_VERSION, "symbols": {}}
    a, sigma, symbols = fit
    omega = np.linspace(1e-6, math.pi, int(grid_size))
    spectra = np.stack([_spectral_theta(a, sigma, w) for w in omega], axis=0)
    total = spectra.sum(axis=0)
    total = total / np.maximum(total.sum(axis=1, keepdims=True), 1e-12)
    band_matrices: dict[str, np.ndarray] = {}
    for name, mapping in FREQUENCY_BANDS.items():
        min_period = mapping["minimum_period_hours"]
        max_period = mapping["maximum_period_hours"]
        low_frequency = 2.0 * math.pi / max_period
        high_frequency = min(math.pi, 2.0 * math.pi / min_period)
        mask = (omega >= low_frequency) & (omega < high_frequency if high_frequency < math.pi else omega <= high_frequency)
        raw = spectra[mask].sum(axis=0) if mask.any() else np.zeros_like(total)
        # Normalize against total spectral mass, not independently, preserving band shares.
        band_matrices[name] = raw / np.maximum(spectra.sum(axis=0).sum(axis=1, keepdims=True), 1e-12)
    rows: dict[str, dict[str, Any]] = {}
    n = len(symbols)
    for i, symbol in enumerate(symbols):
        values: dict[str, Any] = {}
        received_by_band: dict[str, float] = {}
        for band, matrix in band_matrices.items():
            received = float(100.0 * (matrix[i, :].sum() - matrix[i, i]))
            transmitted = float(100.0 * (matrix[:, i].sum() - matrix[i, i]))
            received_by_band[band] = max(0.0, received)
            values[f"connectedness_{band}"] = max(0.0, received)
            values[f"{band}_horizon_net_transmitter" if band != "persistent" else "persistent_net_transmitter"] = transmitted - received
        total_received = sum(received_by_band.values())
        values["persistent_shock_share"] = None if total_received <= 1e-12 else 100.0 * received_by_band["persistent"] / total_received
        values["horizon_connectedness_status"] = "AVAILABLE"
        rows[symbol] = values
    return {
        "status": "AVAILABLE", "version": VERSION, "mapping_version": FREQUENCY_MAPPING_VERSION,
        "mapping": FREQUENCY_BANDS, "symbols": rows, "sample_count": int(len(panel)),
    }


def full_connectedness_bundle(frames: Mapping[str, pd.DataFrame], biases: Mapping[str, str]) -> dict[str, Any]:
    panel = aligned_return_panel(frames)
    return {
        "panel": panel,
        "copula": conditional_copula_evidence(panel, biases),
        "asymmetric": asymmetric_connectedness(panel),
        "frequency": frequency_connectedness(panel),
    }


__all__ = [
    "VERSION", "FREQUENCY_MAPPING_VERSION", "FREQUENCY_BANDS", "fx_currency_legs",
    "duplicate_currency_exposure", "aligned_return_panel", "conditional_copula_evidence",
    "asymmetric_connectedness", "frequency_connectedness", "full_connectedness_bundle",
]
