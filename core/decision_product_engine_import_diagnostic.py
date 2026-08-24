"""Small deployment diagnostic for the repaired decision engine import."""
from __future__ import annotations


def run() -> dict[str, object]:
    from core import decision_product_engine_20260617 as engine

    required = (
        "validate_data_quality",
        "build_decision_result",
        "data_signature",
        "serialize_result",
    )
    missing = [name for name in required if not callable(getattr(engine, name, None))]
    return {
        "ok": not missing,
        "implementation_source": getattr(engine, "IMPLEMENTATION_SOURCE", "unknown"),
        "missing_callables": missing,
        "module_file": getattr(engine, "__file__", None),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2, default=str))
