"""Central registry for independently maintained, lazily imported Lunch fields."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Any, Callable


@dataclass(frozen=True)
class LunchFieldDefinition:
    field_id: str
    title: str
    short_title: str
    validate: Callable[[Any], list[str]]
    build_view_model: Callable[[Any], Any]
    render: Callable[[Any], None]
    order: int
    enabled: bool = True
    experimental: bool = False


def _lazy(module_name: str, function_name: str) -> Callable[..., Any]:
    """Resolve only the selected field's implementation when it is called."""
    def invoke(*args: Any, **kwargs: Any) -> Any:
        function = getattr(import_module(module_name), function_name)
        return function(*args, **kwargs)
    invoke.__name__ = function_name
    invoke.__qualname__ = f"lazy:{module_name}.{function_name}"
    return invoke


def _field(
    field_id: str,
    title: str,
    short_title: str,
    order: int,
    *,
    experimental: bool = False,
    package_name: str | None = None,
) -> LunchFieldDefinition:
    package = f"lunch.{package_name or field_id}"
    return LunchFieldDefinition(
        field_id=field_id,
        title=title,
        short_title=short_title,
        validate=_lazy(f"{package}.contract", "validate"),
        build_view_model=_lazy(f"{package}.view_model", "build_view_model"),
        render=_lazy(f"{package}.renderer", "render"),
        order=order,
        experimental=experimental,
    )


FIELD_REGISTRY = {
    definition.field_id: definition
    for definition in (
        _field("field_01", "Decision Table and Full Metric History", "Decision Table", 1, package_name="field_01_visible"),
        _field("field_02", "Power BI Prediction Projection", "Projection", 2),
        _field("field_03", "Regime and Three-Standards History", "Regime", 3),
        _field("field_arcef", "Quant Research and Thesis Engine — ARCEF-SV", "ARCEF-SV", 10),
        _field("field_12", "Motion Symbol Higher-Regime Rank", "Motion Rank", 12),
    )
}


def ordered_field_ids() -> list[str]:
    return [
        item.field_id
        for item in sorted(FIELD_REGISTRY.values(), key=lambda value: value.order)
        if item.enabled
    ]


__all__ = ["LunchFieldDefinition", "FIELD_REGISTRY", "ordered_field_ids"]
