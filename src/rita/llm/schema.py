"""Shared conversion from our informal ToolSchema params to JSON Schema.

Both the cloud and Ollama planners turn the same `ToolSchema` objects into
provider tool definitions; this is the one place the param-hint -> JSON-schema
mapping lives so the two providers can't drift.
"""

from __future__ import annotations

_TYPE_MAP = {
    "int": "integer", "integer": "integer",
    "str": "string", "string": "string",
    "bool": "boolean", "boolean": "boolean",
    "float": "number", "number": "number",
}


def param_to_schema(spec: str) -> tuple[dict, bool]:
    """('int' | 'str=left' | 'list[str]') -> (json_schema, has_default)."""
    spec = spec.strip()
    has_default = "=" in spec
    type_part = spec.split("=", 1)[0].strip() if has_default else spec
    if type_part.startswith("list[") and type_part.endswith("]"):
        inner = type_part[5:-1].strip()
        return {"type": "array", "items": {"type": _TYPE_MAP.get(inner, "string")}}, has_default
    return {"type": _TYPE_MAP.get(type_part, "string")}, has_default


def properties_and_required(parameters: dict) -> tuple[dict, list[str]]:
    props: dict[str, dict] = {}
    required: list[str] = []
    for name, spec in parameters.items():
        prop, has_default = param_to_schema(str(spec))
        props[name] = prop
        if not has_default:
            required.append(name)
    return props, required


def object_schema(parameters: dict) -> dict:
    props, required = properties_and_required(parameters)
    return {"type": "object", "properties": props, "required": required}
