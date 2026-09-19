"""Bounded research-governance tests and promotion gates for V8 shadow methods."""
from __future__ import annotations
from typing import Any, Mapping
import hashlib, json, math
import numpy as np
import pandas as pd

VERSION = "research-governance-v8-20260622"


def stable_experiment_id(hypothesis: str, parameters: Mapping[str, Any], logic_version: str) -> str:
    raw = json.dumps({"hypothesis": hypothesis, "parameters": dict(parameters), "logic_version": logic_version}, sort_keys=True, default=str).encode()
    return "EXP-" + hashlib.sha256(raw).hexdigest()[:16].upper()


def temporal_block_bootstrap(values: Any, *, replications: int = 300, block_length: int | None = None, seed: int = 20260622) -> dict[str, Any]:
    x = pd.to_numeric(pd.Series(values), errors="coerce").dropna().to_numpy(dtype=float)
    n = len(x)
    if n < 20: return {"status": "INSUFFICIENT_EVIDENCE", "sample_count": n}
    reps = max(50, min(int(replications), 2000)); block = max(2, min(int(block_length or round(n ** (1/3))), max(2, n // 3)))
    rng = np.random.default_rng(seed); means = np.empty(reps)
    for i in range(reps):
        out = []
        while len(out) < n:
            start = int(rng.integers(0, n)); out.extend(x[(start + np.arange(block)) % n].tolist())
        means[i] = float(np.mean(out[:n]))
    return {"status": "AVAILABLE", "sample_count": n, "estimate": float(x.mean()), "lower": float(np.quantile(means, .025)), "upper": float(np.quantile(means, .975)), "replications": reps, "block_length": block, "seed": seed}


def superior_predictive_ability(loss_differentials: pd.DataFrame, *, replications: int = 300, seed: int = 20260622) -> dict[str, Any]:
    if not isinstance(loss_differentials, pd.DataFrame) or loss_differentials.empty:
        return {"status": "INSUFFICIENT_EVIDENCE", "pass": False}
    x = loss_differentials.apply(pd.to_numeric, errors="coerce").dropna().tail(2000)
    if len(x) < 30: return {"status": "INSUFFICIENT_EVIDENCE", "pass": False, "sample_count": len(x)}
    means = x.mean().to_numpy(); observed = float(np.max(-np.sqrt(len(x)) * means))
    rng = np.random.default_rng(seed); centered = x - x.mean(); stats = []
    for _ in range(max(100, min(replications, 1000))):
        idx = rng.integers(0, len(x), len(x)); sample = centered.iloc[idx]
        stats.append(float(np.max(-np.sqrt(len(x)) * sample.mean().to_numpy())))
    p = float((1 + np.sum(np.asarray(stats) >= observed)) / (len(stats) + 1))
    return {"status": "AVAILABLE", "statistic": observed, "p_value": p, "pass": bool(p < .05 and means.min() < 0), "sample_count": len(x)}


def white_reality_check(loss_differentials: pd.DataFrame, *, replications: int = 300, seed: int = 20260623) -> dict[str, Any]:
    # Loss differential = candidate - benchmark; negative is improvement.
    if not isinstance(loss_differentials, pd.DataFrame) or loss_differentials.empty:
        return {"status": "INSUFFICIENT_EVIDENCE", "pass": False}
    x = loss_differentials.apply(pd.to_numeric, errors="coerce").dropna().tail(2000)
    if len(x) < 30: return {"status": "INSUFFICIENT_EVIDENCE", "pass": False, "sample_count": len(x)}
    observed = float(max(0.0, -x.mean().min()) * math.sqrt(len(x)))
    rng = np.random.default_rng(seed); centered = x - x.mean(); boot = []
    for _ in range(max(100, min(replications, 1000))):
        idx = rng.integers(0, len(x), len(x)); boot.append(float(max(0.0, -centered.iloc[idx].mean().min()) * math.sqrt(len(x))))
    p = float((1 + np.sum(np.asarray(boot) >= observed)) / (len(boot) + 1))
    return {"status": "AVAILABLE", "statistic": observed, "p_value": p, "pass": bool(p < .05 and observed > 0), "sample_count": len(x)}


def probability_of_backtest_overfitting(performance: pd.DataFrame, *, max_combinations: int = 256, seed: int = 20260622) -> dict[str, Any]:
    """Sampled CSCV-style PBO. Rows are chronological blocks; columns strategies."""
    if not isinstance(performance, pd.DataFrame) or performance.shape[0] < 8 or performance.shape[1] < 2:
        return {"status": "INSUFFICIENT_EVIDENCE", "pbo": None, "pass": False}
    x = performance.apply(pd.to_numeric, errors="coerce").dropna().tail(1000)
    blocks = min(12, max(8, len(x) // 10)); chunks = [a for a in np.array_split(np.arange(len(x)), blocks) if len(a)]
    rng = np.random.default_rng(seed); combos = []
    for _ in range(min(max_combinations, 2 ** max(1, blocks - 1))):
        pick = np.sort(rng.choice(blocks, size=blocks // 2, replace=False)); key = tuple(pick.tolist())
        if key not in combos: combos.append(key)
    logits = []
    all_blocks = set(range(blocks))
    for pick in combos:
        train_idx = np.concatenate([chunks[i] for i in pick]); test_idx = np.concatenate([chunks[i] for i in sorted(all_blocks - set(pick))])
        train = x.iloc[train_idx].mean(); winner = train.idxmax(); ranks = x.iloc[test_idx].mean().rank(pct=True)
        q = float(ranks[winner]); logits.append(math.log(max(q, 1e-6) / max(1.0 - q, 1e-6)))
    pbo = float(np.mean(np.asarray(logits) < 0)) if logits else 1.0
    return {"status": "AVAILABLE", "pbo": pbo, "pass": pbo < .20, "combinations": len(logits), "sampled": True, "seed": seed}


def promotion_decision(*, leakage_free: bool, settled_samples: int, minimum_samples: int, improved_oos_loss: bool, stable_blocks: bool, spa: Mapping[str, Any], reality_check: Mapping[str, Any], pbo: Mapping[str, Any], acceptable_resources: bool, readiness_critical_failures: int, explicit_production_promotion: bool) -> dict[str, Any]:
    gates = {
        "no_leakage": bool(leakage_free), "sufficient_settled_samples": int(settled_samples) >= int(minimum_samples),
        "improved_out_of_sample_loss": bool(improved_oos_loss), "stable_across_blocks": bool(stable_blocks),
        "spa_pass": bool(spa.get("pass")), "reality_check_pass": bool(reality_check.get("pass")),
        "pbo_below_limit": bool(pbo.get("pass")), "acceptable_cpu_ram": bool(acceptable_resources),
        "no_critical_readiness_failures": int(readiness_critical_failures) == 0,
        "explicit_production_promotion_configuration": bool(explicit_production_promotion),
    }
    passed = all(gates.values())
    return {"status": "PROMOTED" if passed else "SHADOW_ONLY", "production_influence_enabled": passed, "gates": gates, "failed_gates": [k for k, v in gates.items() if not v], "version": VERSION}

__all__ = ["stable_experiment_id", "temporal_block_bootstrap", "superior_predictive_ability", "white_reality_check", "probability_of_backtest_overfitting", "promotion_decision", "VERSION"]
