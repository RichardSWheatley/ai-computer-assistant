"""Example drop-in plugin.

Demonstrates the whole contract in ~20 lines: declare tools in `describe()`,
handle them in `invoke()`, expose `create()`. Drop this folder into `plugins/`
and its tools appear automatically — no core changes.
"""

from rita.core.interfaces import Plugin, ToolResult, ToolSchema


class HelloPlugin(Plugin):
    name = "hello"

    def describe(self) -> list[ToolSchema]:
        return [ToolSchema(
            name="say_hello",
            description="Return a friendly greeting (example tool).",
            parameters={"name": "str"},
            permission_tier="read_only",
        )]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        if tool == "say_hello":
            who = args.get("name") or args.get("goal") or "world"
            return ToolResult(ok=True, output=f"Hello, {who}!")
        return ToolResult(ok=False, error=f"unknown tool {tool}")


def create() -> Plugin:
    return HelloPlugin()
