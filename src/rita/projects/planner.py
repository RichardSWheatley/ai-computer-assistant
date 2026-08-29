"""Planning: RITA figures it out herself, or asks an AI for the list.

`quick_plan` first — a goal that already routes as work through RITA's
grammar becomes a one-item project with NO AI involved. Only a genuinely
multi-step ask goes to the planner: ONE bounded completion whose contract
is strict — items phrased in RITA's own command grammar — and the whole
plan is validated deterministically by routing every command. An item that
doesn't route is kept and flagged `needs_user`, never guessed at. The AI
authors data; it schedules nothing and executes nothing.
"""

from __future__ import annotations

import json
import re
from typing import Callable, Sequence

from ..routing import grammar
from ..routing.model import Utterance, normalize
from ..routing.router import route
from ..routing.vocabulary import Vocabulary
from .model import Project, ProjectItem, ProjectStore

Complete = Callable[[str], str]

MAX_ITEMS = 20


class PlanError(ValueError):
    pass


_PLAN_PROMPT = """Break this goal into a short ordered project plan:
{goal}

Return ONLY a JSON object:
{{"items": [{{"title": "...", "command": "...", "depends_on": [<indices>],
             "estimate": "30m", "milestone": "..."}}]}}

Rules for every "command" — it must be ONE imperative sentence in RITA's
own command grammar, because a deterministic router dispatches it:
- work verbs: build / flash / run the <sample> sample / measure / report /
  write|create an application ... naming boards, samples, peripherals;
- questions ("tell me about <board>", "how do I ...") are allowed and get
  answered from indexed data;
- nothing outside firmware/workspace work — no shopping, no emails.
At most {max_items} items. depends_on holds indices of earlier items."""


def quick_plan(goal: str, vocab: Vocabulary,
               store: ProjectStore | None = None) -> Project | None:
    """A directly work-routable goal needs no AI: one item, run it.

    Only a verb-grounded command qualifies ("build blinky for the
    apollo510"). A goal that merely mentions a known entity ("bring up
    blinky and document the board") is a multi-step ask for the planner.
    """
    d = route(Utterance.from_text(goal), vocab)
    if d.kind != "work" or d.matched_by not in ("verb", "verb+entity"):
        return None
    pid = (store or ProjectStore()).new_id() if store else "proj-quick"
    return Project(id=pid, goal=goal, items=[
        ProjectItem(id="item-1", title=goal, command=goal)])


def _classify(command: str, vocab: Vocabulary) -> str:
    d = route(Utterance.from_text(command), vocab)
    if d.kind == "work":
        return "pending"
    if grammar.is_interrogative(normalize(command)):
        return "pending"          # answerable from indexed data/knowledge
    return "needs_user"           # unroutable: flagged, never guessed at


def plan_project(goal: str, complete: Complete, vocab: Vocabulary,
                 store: ProjectStore | None = None) -> Project:
    from ..firmware.jsonio import ask_json

    try:
        data = ask_json(complete,
                        _PLAN_PROMPT.format(goal=goal, max_items=MAX_ITEMS),
                        what="planner")
        entries: Sequence[dict] = data["items"]
    except Exception as exc:
        raise PlanError(f"planner returned no parseable plan: {exc}") from exc
    if not entries:
        raise PlanError("planner returned an empty plan")
    if len(entries) > MAX_ITEMS:
        raise PlanError(f"plan too large ({len(entries)} items; max {MAX_ITEMS})")

    items: list[ProjectItem] = []
    for n, entry in enumerate(entries, 1):
        command = str(entry.get("command", "")).strip()
        if not command:
            raise PlanError(f"item {n} has no command")
        deps = [f"item-{int(i) + 1}" for i in entry.get("depends_on", [])
                if 0 <= int(i) < len(entries)]
        items.append(ProjectItem(
            id=f"item-{n}",
            title=str(entry.get("title", command)),
            command=command,
            depends_on=deps,
            status=_classify(command, vocab),
            estimate=str(entry.get("estimate", "")),
            milestone=str(entry.get("milestone", ""))))

    pid = store.new_id() if store else ProjectStore().new_id()
    return Project(id=pid, goal=goal, items=items)
