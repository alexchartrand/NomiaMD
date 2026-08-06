"""Derives everything task code needs from a Pydantic result model, so a field only gets
added/changed in one place (the model in app/models.py) instead of being kept in sync by
hand across a task's json_schema(), its prompt's schema description, and any renderer that
turns a parsed result back into text.

Each model field carries its own metadata for this: `description=` is extraction guidance
shown to the LLM in the prompt's schema block, and `json_schema_extra={"fr_label": ...}` is
the French label used when rendering a parsed result back into text (see render_instance).
Supports exactly the shapes these extraction result models use: str/float/bool leaves,
Literal enums, list[str], list[Literal], nested BaseModel, list[BaseModel], and `X | None`
around any of those — anything else raises rather than guessing.
"""

import types
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin is types.UnionType or origin is Union:
        args = get_args(annotation)
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1 and len(args) == 2:
            return non_none[0], True
    return annotation, False


def _fr_label(field: FieldInfo, name: str) -> str:
    extra = field.json_schema_extra
    if isinstance(extra, dict) and extra.get("fr_label"):
        return extra["fr_label"]
    return name


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


# ---------------------------------------------------------------------------
# Strict (OpenAI structured-output) JSON schema
# ---------------------------------------------------------------------------


def _leaf_schema(annotation: Any, optional: bool) -> dict[str, Any]:
    if get_origin(annotation) is Literal:
        values: list[Any] = list(get_args(annotation))
        if optional:
            return {"type": ["string", "null"], "enum": [*values, None]}
        return {"type": "string", "enum": values}
    if annotation is str:
        return {"type": ["string", "null"]} if optional else {"type": "string"}
    if annotation is bool:
        return {"type": ["boolean", "null"]} if optional else {"type": "boolean"}
    if annotation in (float, int):
        return {"type": ["number", "null"]} if optional else {"type": "number"}
    raise TypeError(f"schema.py doesn't know how to render annotation {annotation!r}")


def _field_schema(annotation: Any) -> dict[str, Any]:
    inner, optional = _unwrap_optional(annotation)
    if _is_model(inner):
        return to_strict_schema(inner)
    if get_origin(inner) is list:
        (item_type,) = get_args(inner)
        item_inner, _item_optional = _unwrap_optional(item_type)
        items = to_strict_schema(item_inner) if _is_model(item_inner) else _leaf_schema(item_inner, False)
        return {"type": "array", "items": items}
    return _leaf_schema(inner, optional)


def to_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Recursively builds the additionalProperties:false / all-fields-required JSON schema
    shape OpenAI-compatible structured-output APIs expect, straight from a Pydantic model —
    no hand-maintained duplicate of the model's shape."""
    properties = {name: _field_schema(field.annotation) for name, field in model.model_fields.items()}
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# Human-readable schema block for the prompt
# ---------------------------------------------------------------------------


def _leaf_placeholder(annotation: Any, description: str | None, optional: bool) -> str:
    if get_origin(annotation) is Literal:
        values = " | ".join(str(v) for v in get_args(annotation))
        if optional:
            values += " | null"
        return f'"{values}"'
    if annotation is bool:
        return f'"{"true | false | null" if optional else "true | false"}"'
    if annotation in (float, int):
        return '"<number or null>"' if optional else '"<number>"'
    if annotation is str:
        text = description or "free text"
        return f'"<{text[0].lower()}{text[1:]}>"'
    raise TypeError(f"schema.py doesn't know how to render annotation {annotation!r}")


def _render_block(model: type[BaseModel], indent: int) -> str:
    pad = "  " * indent
    inner_pad = "  " * (indent + 1)
    lines = ["{"]
    field_items = list(model.model_fields.items())
    for i, (name, field) in enumerate(field_items):
        annotation, optional = _unwrap_optional(field.annotation)
        comma = "," if i < len(field_items) - 1 else ""
        if _is_model(annotation):
            nested = _render_block(annotation, indent + 1)
            lines.append(f'{inner_pad}"{name}": {nested}{comma}')
        elif get_origin(annotation) is list:
            (item_type,) = get_args(annotation)
            item_inner, item_optional = _unwrap_optional(item_type)
            if _is_model(item_inner):
                nested = _render_block(item_inner, indent + 1)
                lines.append(f'{inner_pad}"{name}": [{nested}]{comma}')
            elif get_origin(item_inner) is Literal:
                values = " | ".join(str(v) for v in get_args(item_inner))
                note = field.description or "list all that apply, empty list if none"
                lines.append(f'{inner_pad}"{name}": ["{values} — {note}"]{comma}')
            else:
                placeholder = _leaf_placeholder(item_inner, field.description, item_optional)
                lines.append(f'{inner_pad}"{name}": [{placeholder}]{comma}')
        else:
            placeholder = _leaf_placeholder(annotation, field.description, optional)
            lines.append(f'{inner_pad}"{name}": {placeholder}{comma}')
    lines.append(f"{pad}}}")
    return "\n".join(lines)


def render_schema_block(model: type[BaseModel]) -> str:
    """Renders the same JSON-with-placeholders schema example previously hand-written into
    each task's SYSTEM_PROMPT, driven by the model's field types and `description=` text."""
    return _render_block(model, 0)


# ---------------------------------------------------------------------------
# Result -> text rendering (e.g. for grounding a downstream extraction prompt)
# ---------------------------------------------------------------------------


def _render_fields(instance: BaseModel, lines: list[str]) -> None:
    for name, field in type(instance).model_fields.items():
        value = getattr(instance, name)
        label = _fr_label(field, name)
        annotation, _optional = _unwrap_optional(field.annotation)

        if _is_model(annotation):
            _render_fields(value, lines)
            continue

        if get_origin(annotation) is list:
            (item_type,) = get_args(annotation)
            item_inner, _ = _unwrap_optional(item_type)
            if _is_model(item_inner):
                for i, item in enumerate(value, start=1):
                    item_lines: list[str] = []
                    _render_fields(item, item_lines)
                    lines.extend(f"{label} {i} - {item_line}" for item_line in item_lines)
            elif value:
                lines.append(f"{label}: {'; '.join(str(v) for v in value)}")
            continue

        if value is None or value == "":
            continue
        if isinstance(value, bool):
            lines.append(f"{label}: {'oui' if value else 'non'}")
        else:
            lines.append(f"{label}: {value}")


def render_instance(instance: BaseModel) -> str:
    """Renders a parsed result back into a flat, labeled text blob — one line per non-empty
    field, in declaration order, empty/None fields omitted rather than printed as null."""
    lines: list[str] = []
    _render_fields(instance, lines)
    return "\n".join(lines)
