"""Machine-readable ML production-readiness rubric.

The score is diagnostic only. Critical failures block research promotion, not
the protected canonical calculation unless a separate validation gate fails.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Mapping, Sequence

from core.research_validation_common_20260621 import json_safe, stable_hash, utc_now_iso

VERSION = "ml-production-readiness-score-20260621-v1"
GROUPS = ("data_tests", "model_development_tests", "infrastructure_tests", "monitoring_tests")


@dataclass(frozen=True)
class ReadinessCheck:
    check_id: str
    group: str
    title: str
    status: str
    severity: str
    evidence: Any
    requirement: str
    remediation: str = ""

    def as_dict(self) -> dict[str, Any]:
        return json_safe(asdict(self))


def _status(value: Any, *, unknown: str = "WARNING") -> str:
    if value is True:
        return "PASS"
    if value is False:
        return "FAIL"
    return unknown


def build_ml_production_readiness_score(evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    e = dict(evidence or {})
    specs = [
        ("feature_schema", "data_tests", "Feature schema", e.get("feature_schema_pass"), "CRITICAL", "Required production features and types match the declared schema."),
        ("feature_usefulness", "model_development_tests", "Feature usefulness evidence", e.get("feature_usefulness_pass"), "WARNING", "Features have settled, out-of-sample usefulness evidence."),
        ("feature_cost", "infrastructure_tests", "Feature computation cost", e.get("feature_cost_pass"), "WARNING", "Feature computation fits CPU and RAM budgets."),
        ("secret_handling", "infrastructure_tests", "Privacy and secret handling", e.get("secret_handling_pass"), "CRITICAL", "Secrets are not committed, logged, or embedded in outputs."),
        ("reproducibility", "model_development_tests", "Reproducibility", e.get("reproducibility_pass"), "CRITICAL", "Same inputs, versions, seed and configuration produce the same output."),
        ("baseline_comparison", "model_development_tests", "Baseline comparison", e.get("baseline_comparison_pass"), "WARNING", "Every challenger is compared with the production benchmark."),
        ("important_slices", "model_development_tests", "Important data slices", e.get("important_slice_pass"), "WARNING", "Regime, session, volatility and event-risk slices are evaluated."),
        ("model_staleness", "monitoring_tests", "Model staleness", e.get("model_staleness_pass"), "WARNING", "Artifact age and settled performance remain within limits."),
        ("unit_tests", "infrastructure_tests", "Unit tests", e.get("unit_tests_pass"), "CRITICAL", "Critical statistical and persistence components have deterministic unit tests."),
        ("integration_tests", "infrastructure_tests", "Integration tests", e.get("integration_tests_pass"), "CRITICAL", "Run Calculation through atomic publication is tested."),
        ("rollback", "infrastructure_tests", "Calculation rollback", e.get("rollback_pass"), "CRITICAL", "A failed generation leaves the prior completed generation valid."),
        ("debuggability", "infrastructure_tests", "Debuggability", e.get("debuggability_pass"), "WARNING", "Exact failed constraints, generation IDs and versions are recorded."),
        ("numerical_stability", "model_development_tests", "Numerical stability", e.get("numerical_stability_pass"), "CRITICAL", "NaN, infinity, degenerate variance and sparse samples are handled safely."),
        ("dependency_changes", "infrastructure_tests", "Dependency changes", e.get("dependency_change_pass"), "WARNING", "Dependency changes are pinned, reviewed and cloud-compatible."),
        ("data_invariants", "data_tests", "Data invariants", e.get("data_invariants_pass"), "CRITICAL", "OHLC, chronology, uniqueness, frequency and freshness constraints pass."),
        ("training_production_skew", "data_tests", "Training/production skew", e.get("training_production_skew_pass"), "CRITICAL", "Training and production transformations are consistent."),
        ("cpu_regression", "monitoring_tests", "CPU regression", e.get("cpu_regression_pass"), "WARNING", "Calculation CPU does not materially regress."),
        ("ram_regression", "monitoring_tests", "RAM regression", e.get("ram_regression_pass"), "WARNING", "Peak RSS does not materially regress."),
        ("settled_quality_regression", "monitoring_tests", "Settled prediction-quality regression", e.get("settled_quality_regression_pass"), "CRITICAL", "Settled out-of-sample quality has not materially degraded."),
    ]
    checks: list[ReadinessCheck] = []
    for check_id, group, title, value, severity, requirement in specs:
        checks.append(ReadinessCheck(
            check_id=check_id, group=group, title=title, status=_status(value), severity=severity,
            evidence=e.get(f"{check_id}_evidence", value), requirement=requirement,
            remediation="Collect or verify evidence before research promotion." if value is not True else "",
        ))
    group_scores: dict[str, float] = {}
    for group in GROUPS:
        group_checks = [c for c in checks if c.group == group]
        points = sum(1.0 if c.status == "PASS" else 0.5 if c.status == "WARNING" else 0.0 for c in group_checks)
        group_scores[group] = round(100.0 * points / max(len(group_checks), 1), 2)
    critical_failures = sum(c.status == "FAIL" and c.severity == "CRITICAL" for c in checks)
    warning_count = sum(c.status == "WARNING" or (c.status == "FAIL" and c.severity == "WARNING") for c in checks)
    overall = round(sum(group_scores.values()) / len(group_scores), 2)
    promotion_allowed = critical_failures == 0 and warning_count == 0 and overall >= 90.0
    result = {
        "version": VERSION,
        "evaluated_at": utc_now_iso(),
        "checks": [c.as_dict() for c in checks],
        "data_readiness_score": group_scores["data_tests"],
        "model_readiness_score": group_scores["model_development_tests"],
        "infrastructure_readiness_score": group_scores["infrastructure_tests"],
        "monitoring_readiness_score": group_scores["monitoring_tests"],
        "overall_readiness_score": overall,
        "critical_failure_count": critical_failures,
        "warning_count": warning_count,
        "promotion_allowed": promotion_allowed,
        "compact_summary": f"Readiness {overall:.0f}/100 · {critical_failures} critical · {warning_count} warning",
    }
    result["evaluation_id"] = "MLR-" + stable_hash({k: v for k, v in result.items() if k != "evaluated_at"})[:24]
    return result


__all__ = ["VERSION", "ReadinessCheck", "build_ml_production_readiness_score"]
