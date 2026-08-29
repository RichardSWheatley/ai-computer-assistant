"""The intelligent manager: the AI decides what to do with a request.

The owner's rule: RITA is the automation; the coding agent is the
routing manager. It sees the user's exact words plus RITA's synced
reality — board list, sample list, machine facts — and answers ONE
bounded JSON work order. RITA validates the order against that same
reality before acting (a board not in the sync, a sample not in the
index: rejected with evidence), states the decision out loud, and runs
the deterministic gates. The LLM decides intent; it never grades work.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WorkOrder:
    action: str        # build | modify | scaffold | chat
    board: str         # from the synced list, or "" = RITA defaults
    sample: str        # sample id for build/modify, "" otherwise
    goal: str          # one line: what to accomplish
    why: str           # one line: the manager's reasoning, spoken back


_PROMPT = (
    "You are the routing manager for RITA, a deterministic firmware "
    "orchestrator. Decide what to do with the user's request.\n"
    "Machine: {machine}\n"
    "Boards available (choose ONLY from these): {boards}\n"
    "Existing samples/suites (id — path):\n{samples}\n"
    'User request: "{text}"\n\n'
    "Answer with ONLY this JSON object: "
    '{{"action": "build|modify|scaffold|chat", '
    '"board": "<a board from the list, or empty to let RITA pick>", '
    '"sample": "<the sample id to build or modify, or empty>", '
    '"goal": "<one line: what to accomplish>", '
    '"why": "<one line: why this action and board>"}}\n'
    'Use "modify" when the user wants changes to an existing sample '
    "(RITA works on a copy; the tree stays untouched), \"scaffold\" for "
    'a brand-new application, "build" to run an existing sample or '
    'suite unchanged, and "chat" when it is not a work request. When '
    "the user names no board, pick one this machine can actually run.")


def interpret_request(complete, text: str, *, boards, samples,
                      machine: str) -> tuple[WorkOrder | None, str]:
    """(order, note). The order is validated against the given reality;
    None means the manager's answer didn't hold up — the note carries
    the evidence and the caller falls back to grammar routing."""
    from .jsonio import ask_json

    listing = "\n".join(f"- {sid} — {path}"
                        for sid, path in samples) or "- (none synced yet)"
    prompt = _PROMPT.format(machine=machine,
                            boards=", ".join(boards) or "(none synced)",
                            samples=listing, text=text)
    try:
        data = ask_json(complete, prompt, what="the routing manager")
    except ValueError as exc:
        return None, str(exc)
    action = str(data.get("action", "")).strip().lower()
    if action not in ("build", "modify", "scaffold", "chat"):
        return None, (f"the routing manager answered an unknown action "
                      f"{action!r}")
    board = str(data.get("board") or "").strip()
    # Upstream simulator targets (qemu_*, native_sim) are always valid:
    # every Zephyr tree ships them even when a sparse sync missed them.
    simulator = board.startswith("qemu_") or board == "native_sim"
    if board and boards and board not in boards and not simulator:
        return None, (f"the routing manager picked a board that is not "
                      f"in your sync: {board!r}")
    sample = str(data.get("sample") or "").strip()
    if action == "modify":
        known = [sid for sid, _ in samples] + [p for _, p in samples]
        if not sample or not any(sample == k or sample in k
                                 for k in known):
            return None, (f"the routing manager named a sample that is "
                          f"not in your workspace: {sample!r}")
    return WorkOrder(action=action, board=board, sample=sample,
                     goal=str(data.get("goal") or text).strip(),
                     why=str(data.get("why") or "").strip()), "ok"
