"""Outlook plugin — triage/summarize inbox, draft and send mail via Graph.

Safety: drafting is local_write; SENDING is outward_facing, so the orchestrator
gates it behind a confirmation. The Graph client is built lazily on first use
(device-code login) and can be injected for testing.

Opt-in (enabled=false): needs msal + a signed-in account (AICA_GRAPH_* env).
"""

from rita.business.graph import GraphClient
from rita.core.interfaces import Plugin, ToolResult, ToolSchema


class OutlookPlugin(Plugin):
    name = "outlook"

    def __init__(self, client: GraphClient | None = None) -> None:
        self._client = client

    def _graph(self) -> GraphClient:
        if self._client is None:
            self._client = GraphClient.from_env()
        return self._client

    def describe(self) -> list[ToolSchema]:
        return [
            ToolSchema("summarize_inbox",
                       "Summarize the most recent inbox messages (read-only).",
                       {"count": "int=10"}, "read_only"),
            ToolSchema("draft_email",
                       "Create a draft email in the mailbox (does not send).",
                       {"to": "list[str]", "subject": "str", "body": "str"},
                       "local_write"),
            ToolSchema("send_email",
                       "Send an email. Outward-facing — gated by confirmation.",
                       {"to": "list[str]", "subject": "str", "body": "str"},
                       "outward_facing"),
        ]

    def invoke(self, tool: str, args: dict) -> ToolResult:
        try:
            g = self._graph()
        except Exception as exc:
            return ToolResult(ok=False, error=f"Outlook unavailable: {exc}")
        try:
            if tool == "summarize_inbox":
                msgs = g.list_messages(int(args.get("count", 10)))
                lines = [
                    f"- {m.get('subject','(no subject)')} "
                    f"— {m.get('from',{}).get('emailAddress',{}).get('address','?')}"
                    f"{'' if m.get('isRead') else '  [unread]'}"
                    for m in msgs
                ]
                summary = f"{len(msgs)} messages:\n" + "\n".join(lines)
                return ToolResult(ok=True, output=summary)
            if tool == "draft_email":
                mid = g.create_draft(args.get("to", []), args.get("subject", ""),
                                     args.get("body", ""))
                return ToolResult(ok=True, output=f"draft created: {mid}")
            if tool == "send_email":
                g.send_mail(args.get("to", []), args.get("subject", ""),
                            args.get("body", ""))
                return ToolResult(ok=True, output="email sent")
            return ToolResult(ok=False, error=f"unknown tool {tool}")
        except Exception as exc:
            return ToolResult(ok=False, error=f"{type(exc).__name__}: {exc}")


def create() -> Plugin:
    return OutlookPlugin()
