"""Memory plugin — let the assistant remember facts and recall them later.

`recall` is read-only; `remember` is a local write. Opt-in (enabled=false). The
store is in-memory by default; pass a path for persistence.
"""

from rita.core.interfaces import Plugin, ToolResult, ToolSchema
from rita.memory.store import MemoryStore


class MemoryPlugin(Plugin):
    name = "memory"

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or MemoryStore()

    def describe(self) -> list[ToolSchema]:
        return [
            ToolSchema("remember", "Store a fact/preference for later recall.",
                       {"key": "str", "value": "str", "namespace": "str=facts"},
                       "local_write"),
            ToolSchema("recall", "Recall stored items relevant to a query.",
                       {"query": "str", "k": "int=5"}, "read_only"),
        ]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        if tool == "remember":
            key = str(args.get("key", "")).strip()
            if not key:
                return ToolResult(ok=False, error="remember needs a 'key'")
            self.store.remember(key, str(args.get("value", "")),
                                str(args.get("namespace", "facts")))
            return ToolResult(ok=True, output=f"remembered {key!r}")
        if tool == "recall":
            hits = self.store.recall(str(args.get("query", "")),
                                     int(args.get("k", 5)))
            return ToolResult(ok=True, output=hits)
        return ToolResult(ok=False, error=f"unknown tool {tool}")


def create() -> Plugin:
    return MemoryPlugin()
