from __future__ import annotations

def promotion_allowed(*, drift_detected: bool, leakage_risk: bool, pbo: float | None, pbo_limit: float, calibration_ok: bool, coverage_ok: bool, minimum_sample_ok: bool) -> tuple[bool, str]:
    reasons = []
    if drift_detected: reasons.append("DRIFT_DETECTED")
    if leakage_risk: reasons.append("LEAKAGE_RISK")
    if pbo is None or pbo > pbo_limit: reasons.append("PBO_LIMIT")
    if not calibration_ok: reasons.append("CALIBRATION_FAILED")
    if not coverage_ok: reasons.append("COVERAGE_FAILED")
    if not minimum_sample_ok: reasons.append("INSUFFICIENT_DATA")
    return (not reasons, "VALIDATION_PASSED" if not reasons else ",".join(reasons))
