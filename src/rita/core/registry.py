"""Tool registry — the single place the planner sees every available tool.

Plugins register their tools here at load time; the orchestrator dispatches
calls back to the owning plugin. Adding a feature never edits the core.
"""

from __future__ import annotations

from .interfaces import Plugin, ToolCall, ToolResult, ToolSchema


class ToolRegistry:
    def __init__(self) -> None:
        self._schemas: dict[str, ToolSchema] = {}
        self._owner: dict[str, Plugin] = {}

    def register_plugin(self, plugin: Plugin) -> None:
        for schema in plugin.describe():
            if schema.name in self._schemas:
                raise ValueError(f"Duplicate tool name: {schema.name}")
            self._schemas[schema.name] = schema
            self._owner[schema.name] = plugin

    def schemas(self) -> list[ToolSchema]:
        return list(self._schemas.values())

    def has(self, name: str) -> bool:
        return name in self._schemas

    def tier(self, name: str) -> str:
        # Fail closed: an unknown tool is treated as maximally restricted so the
        # gate blocks it rather than letting an unregistered action through.
        return self._schemas[name].permission_tier if name in self._schemas else "outward_facing"

    def dispatch(self, call: ToolCall) -> ToolResult:
        owner = self._owner.get(call.tool)
        if owner is None:
            return ToolResult(ok=False, error=f"Unknown tool: {call.tool}")
        try:
            return owner.invoke(call.tool, call.args)
        except Exception as exc:  # plugin failure is contained, never fatal
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")
