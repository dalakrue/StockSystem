"""Robust evidence dependence, clustering and cluster-weight budgets."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

VERSION = "field10-evidence-clustering-20260705-v1"


def _winsorized(frame: pd.DataFrame, lower: float = 0.05, upper: float = 0.95) -> pd.DataFrame:
    numeric = frame.apply(pd.to_numeric, errors="coerce")
    result = numeric.copy()
    for column in result:
        values = result[column].dropna()
        if len(values) >= 8:
            lo, hi = values.quantile([lower, upper])
            result[column] = result[column].clip(lo, hi)
    return result


def _distance_correlation(x: pd.Series, y: pd.Series) -> float | None:
    pair = pd.concat([x, y], axis=1).dropna()
    if len(pair) < 12:
        return None
    a, b = pair.iloc[:, 0].to_numpy(float), pair.iloc[:, 1].to_numpy(float)
    ax = np.abs(a[:, None] - a[None, :]); by = np.abs(b[:, None] - b[None, :])
    ax -= ax.mean(0)[None, :] + ax.mean(1)[:, None] - ax.mean()
    by -= by.mean(0)[None, :] + by.mean(1)[:, None] - by.mean()
    dcov = float(np.sqrt(max(np.mean(ax * by), 0.0)))
    dvarx = float(np.sqrt(max(np.mean(ax * ax), 0.0)))
    dvary = float(np.sqrt(max(np.mean(by * by), 0.0)))
    denominator = np.sqrt(max(dvarx * dvary, 1e-18))
    return float(np.clip(dcov / denominator, 0.0, 1.0))


def _union_find(columns: list[str], dependence: pd.DataFrame, threshold: float) -> dict[str, int]:
    parent = {column: column for column in columns}
    def find(item: str) -> str:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item
    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for i, left in enumerate(columns):
        for right in columns[i + 1:]:
            value = dependence.loc[left, right]
            if pd.notna(value) and abs(float(value)) >= threshold:
                union(left, right)
    roots: dict[str, int] = {}
    output: dict[str, int] = {}
    for column in columns:
        root = find(column)
        roots.setdefault(root, len(roots) + 1)
        output[column] = roots[root]
    return output


def effective_number_of_components(correlation: pd.DataFrame) -> float | None:
    if correlation.empty:
        return None
    matrix = correlation.fillna(0.0).to_numpy(float)
    np.fill_diagonal(matrix, 1.0)
    eigenvalues = np.clip(np.linalg.eigvalsh(matrix), 0.0, None)
    total = float(eigenvalues.sum())
    return None if total <= 0 else float(total * total / max(float(np.square(eigenvalues).sum()), 1e-12))


def cluster_evidence(frame: pd.DataFrame, configured_weights: Mapping[str, float], *, threshold: float = 0.80) -> dict[str, Any]:
    columns = [column for column in configured_weights if column in frame.columns]
    if not columns:
        return {"status": "NO_EVIDENCE", "clusters": {}, "effective_weights": {}}
    work = _winsorized(frame[columns])
    pearson = work.corr(method="pearson", min_periods=8)
    spearman = work.corr(method="spearman", min_periods=8)
    composite = pd.DataFrame(np.fmax(pearson.abs().to_numpy(float), spearman.abs().to_numpy(float)), index=pearson.index, columns=pearson.columns)
    nonlinear_rows: list[dict[str, Any]] = []
    if len(work) <= 800:
        for i, left in enumerate(columns):
            for right in columns[i + 1:]:
                value = _distance_correlation(work[left], work[right])
                if value is not None:
                    composite.loc[left, right] = composite.loc[right, left] = max(float(composite.loc[left, right]) if pd.notna(composite.loc[left, right]) else 0.0, value)
                    nonlinear_rows.append({"left": left, "right": right, "distance_correlation": value})
    clusters = _union_find(columns, composite, threshold)
    cluster_members: dict[int, list[str]] = {}
    for component, cluster_id in clusters.items():
        cluster_members.setdefault(cluster_id, []).append(component)
    total_weight = float(sum(max(0.0, float(configured_weights[c])) for c in columns))
    effective_weights: dict[str, float] = {}
    cluster_budgets: dict[int, float] = {}
    for cluster_id, members in cluster_members.items():
        # The cluster receives the largest registered member weight plus half of
        # remaining distinct budget, capped by the original cluster sum.
        raw = [max(0.0, float(configured_weights[m])) for m in members]
        budget = min(sum(raw), max(raw) + 0.5 * (sum(raw) - max(raw)))
        cluster_budgets[cluster_id] = budget
        denominator = sum(raw) or 1.0
        for member, weight in zip(members, raw):
            effective_weights[member] = budget * weight / denominator
    scale = total_weight / max(sum(effective_weights.values()), 1e-12)
    effective_weights = {key: value * scale for key, value in effective_weights.items()}
    audit_rows = []
    for component in columns:
        audit_rows.append({
            "component": component, "cluster_id": clusters[component],
            "configured_weight": float(configured_weights[component]),
            "cluster_budget": cluster_budgets[clusters[component]],
            "effective_weight": effective_weights[component],
            "duplicate_penalty": max(0.0, float(configured_weights[component]) - effective_weights[component]),
        })
    return {
        "status": "AVAILABLE", "method": "ROBUST_PEARSON_SPEARMAN_NONLINEAR_UNION_CLUSTER",
        "threshold": threshold, "robust_correlation": pearson.to_dict(), "rank_correlation": spearman.to_dict(),
        "composite_dependence": composite.to_dict(), "nonlinear_dependence": nonlinear_rows,
        "clusters": clusters, "cluster_members": cluster_members, "cluster_budgets": cluster_budgets,
        "effective_weights": effective_weights, "audit_rows": audit_rows,
        "effective_number_of_independent_components": effective_number_of_components(pearson),
    }


__all__ = ["VERSION", "effective_number_of_components", "cluster_evidence"]
