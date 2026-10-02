"""Safe recursive discovery of already-published tabular evidence.

Presentation-only helpers. They never run a model or synthesize historical rows.
"""
from __future__ import annotations
from typing import Any, Iterable, Mapping
import pandas as pd


def as_frame(value: Any) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        return value.copy(deep=False)
    if isinstance(value, (list, tuple)) and (not value or isinstance(value[0], Mapping)):
        try:
            return pd.DataFrame(value)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def iter_published_frames(root: Any, *, max_depth: int = 5) -> Iterable[tuple[str, pd.DataFrame]]:
    """Yield unique DataFrames from nested mappings/lists with their key path."""
    seen_obj: set[int] = set()
    seen_frame: set[int] = set()

    def walk(value: Any, path: str, depth: int):
        if depth > max_depth or id(value) in seen_obj:
            return
        seen_obj.add(id(value))
        frame = as_frame(value)
        if not frame.empty and id(value) not in seen_frame:
            seen_frame.add(id(value))
            yield path, frame
        if isinstance(value, Mapping):
            for key, child in value.items():
                yield from walk(child, f"{path}.{key}" if path else str(key), depth + 1)
        elif isinstance(value, (list, tuple)) and value and not isinstance(value[0], Mapping):
            for index, child in enumerate(value[:200]):
                if isinstance(child, (Mapping, pd.DataFrame, list, tuple)):
                    yield from walk(child, f"{path}[{index}]", depth + 1)

    yield from walk(root, "", 0)


def matching_frames(root: Any, *, path_tokens=(), column_tokens=(), max_depth: int = 5) -> list[pd.DataFrame]:
    out: list[pd.DataFrame] = []
    pt = tuple(str(x).lower() for x in path_tokens)
    ct = tuple(str(x).lower() for x in column_tokens)
    for path, frame in iter_published_frames(root, max_depth=max_depth):
        hay = path.lower()
        columns = " ".join(str(c).lower() for c in frame.columns)
        if pt and not all(token in hay or token in columns for token in pt):
            continue
        if ct and not all(token in columns for token in ct):
            continue
        out.append(frame)
    return out
