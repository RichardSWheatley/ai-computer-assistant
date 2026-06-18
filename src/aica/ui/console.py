"""Console approval prompt — the human-in-the-loop for gated actions.

`build_assistant(confirm=...)` accepts a callable(ToolCall) -> bool. This builds
one that previews the action and asks the user. I/O is injectable so it's
testable without real stdin. The orchestrator only calls this for actions the
SecurityPolicy says need confirmation (outward-facing, destructive, or local
writes under suspicion), so the user is asked exactly when it matters.
"""

from __future__ import annotations

from typing import Callable

from ..core.interfaces import ToolCall


def describe_action(call: ToolCall) -> str:
    args = ", ".join(f"{k}={v!r}" for k, v in (call.args or {}).items())
    line = f"{call.tool}({args})"
    if call.reasoning:
        line += f"   — {call.reasoning}"
    return line


def make_console_confirmer(
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> Callable[[ToolCall], bool]:
    def confirm(call: ToolCall) -> bool:
        output_fn("")
        output_fn("⚠  Approval needed for a high-risk action:")
        output_fn(f"    {describe_action(call)}")
        answer = input_fn("    Approve this action? [y/N] ").strip().lower()
        approved = answer in ("y", "yes")
        output_fn("    → approved" if approved else "    → denied")
        return approved

    return confirm
