"""Built-in computer-use plugin: click, type, hotkey.

This is the Phase-1 'hands'. It wraps InputController and exposes it as tools so
the planner can drive the mouse/keyboard through the standard registry path.
"""

from __future__ import annotations

from ..action.input import InputController
from ..core.interfaces import Plugin, ToolResult, ToolSchema


class ComputerUsePlugin(Plugin):
    name = "computer_use"

    def __init__(self, controller: InputController | None = None) -> None:
        self.input = controller or InputController(dry_run=True)

    def describe(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="click",
                description="Click the mouse at screen coordinates (x, y).",
                parameters={"x": "int", "y": "int", "button": "str=left"},
                permission_tier="local_write",
            ),
            ToolSchema(
                name="type_text",
                description="Type a string via simulated keyboard input.",
                parameters={"text": "str"},
                permission_tier="local_write",
            ),
            ToolSchema(
                name="hotkey",
                description="Press a key combination, e.g. ctrl+c.",
                parameters={"keys": "list[str]"},
                permission_tier="local_write",
            ),
        ]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        if tool == "click":
            return self.input.click(int(args.get("x", 0)), int(args.get("y", 0)),
                                    args.get("button", "left"))
        if tool == "type_text":
            return self.input.type_text(str(args.get("text", args.get("goal", ""))))
        if tool == "hotkey":
            keys = args.get("keys") or []
            return self.input.hotkey(*keys)
        return ToolResult(ok=False, error=f"unknown tool {tool}")


def create() -> Plugin:
    return ComputerUsePlugin()
