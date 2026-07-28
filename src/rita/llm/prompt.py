"""Shared, injection-resistant prompt construction for planners.

The user's GOAL is trusted; the SCREEN/ELEMENTS/HISTORY are untrusted data the
agent observed, so they go inside an <untrusted_data> fence. Both the Claude and
Ollama planners use this so the control/data separation can't drift between them.
"""

from __future__ import annotations

from ..core.interfaces import ScreenState
from ..security.trust import TRUST_DIRECTIVE, fence_untrusted


def build_user_message(goal: str, state: ScreenState, history: list[dict]) -> str:
    # Trusted: the user's goal.
    trusted = f"GOAL: {goal}"

    # Untrusted: everything observed. Fenced so injected text can't pose as a command.
    obs = [f"SCREEN: {state.summary}"]
    if state.elements:
        obs.append("ELEMENTS:")
        for e in state.elements:
            obs.append(f"  - {e.role} {e.label!r} at ({e.x},{e.y})")
    if history:
        obs.append("HISTORY (most recent last):")
        for h in history[-10:]:
            status = "ok" if h.get("ok") else f"ERROR: {h.get('error')}"
            obs.append(f"  - {h.get('tool')}({h.get('args')}) -> {status}")
    fenced = fence_untrusted("\n".join(obs), source="observation")

    return f"{trusted}\n\n{fenced}\n\nChoose the single next tool call."


__all__ = ["build_user_message", "TRUST_DIRECTIVE"]
