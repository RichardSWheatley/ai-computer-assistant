"""Teams plugin — post a message to a channel via Microsoft Graph.

Posting is outward_facing, so the orchestrator gates it behind a confirmation.
Opt-in (enabled=false): needs msal + a signed-in account.
"""

from rita.business.graph import GraphClient
from rita.core.interfaces import Plugin, ToolResult, ToolSchema


class TeamsPlugin(Plugin):
    name = "teams"

    def __init__(self, client: GraphClient | None = None) -> None:
        self._client = client

    def _graph(self) -> GraphClient:
        if self._client is None:
            self._client = GraphClient.from_env()
        return self._client

    def describe(self) -> list[ToolSchema]:
        return [ToolSchema(
            "post_message",
            "Post a message to a Teams channel. Outward-facing — gated by confirmation.",
            {"team_id": "str", "channel_id": "str", "text": "str"},
            "outward_facing",
        )]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        if tool != "post_message":
            return ToolResult(ok=False, error=f"unknown tool {tool}")
        try:
            g = self._graph()
            mid = g.post_channel_message(args.get("team_id", ""),
                                         args.get("channel_id", ""),
                                         args.get("text", ""))
            return ToolResult(ok=True, output=f"posted message: {mid}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"Teams post failed: {exc}")


def create() -> Plugin:
    return TeamsPlugin()
