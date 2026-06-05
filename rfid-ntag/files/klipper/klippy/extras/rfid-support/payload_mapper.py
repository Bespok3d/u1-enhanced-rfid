from collections.abc import Callable
from typing import Any

FieldMap = dict[str, tuple[str | None, Callable[[Any], Any], Any]]


def _convert(value: Any, converter: Callable[[Any], Any], default: Any) -> Any:
    try:
        return converter(value)
    except (ValueError, TypeError):
        return default


def apply_field_map(
    src_dict: dict[str, Any], dest_dict: dict[str, Any], field_map: FieldMap,
) -> None:
    for dest_key, (src_key, converter, default) in field_map.items():
        if src_key is None or src_key not in src_dict:
            dest_dict[dest_key] = default
        else:
            dest_dict[dest_key] = _convert(src_dict[src_key], converter, default)
