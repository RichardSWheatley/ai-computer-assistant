"""Execution: RITA completes the tasks — never the AI.

Dependency-ordered walk over the plan. Work items run a full
IteratePipeline (CERBERUS -> unit tests -> final test) in their own
workdir; question items get their deterministic answer recorded; an item
whose dependency failed is blocked by cascade — reported, never looped
past. The store persists every transition, and the TaskControl checkpoint
between items makes PAUSE/STOP land at safe boundaries on top of the
in-item stage checkpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..core.tasks import TaskStopped
from ..routing.model import Utterance
from ..routing.router import route
from ..routing.vocabulary import Vocabulary
from .model import Project, ProjectStore

_BAD = ("blocked", "needs_user", "stopped")


@dataclass(frozen=True)
class ProjectResult:
    outcome: str            # completed | partial | blocked
    done: int = 0
    answered: int = 0
    blocked: int = 0
    needs_user: int = 0


def describe_project(result: ProjectResult) -> str:
    """The spoken/screen summary for a finished project task."""
    parts = []
    if result.done:
        parts.append(f"{result.done} item(s) done")
    if result.answered:
        parts.append(f"{result.answered} answered")
    if result.blocked:
        parts.append(f"{result.blocked} blocked")
    if result.needs_user:
        parts.append(f"{result.needs_user} waiting on you")
    detail = ", ".join(parts) or "no items"
    return f"Project {result.outcome}: {detail}."


def run_project(project: Project, store: ProjectStore, *,
                pipeline_factory: Callable[[str], object],
                chat: Callable[[str], str],
                vocab: Vocabulary, ctl=None) -> ProjectResult:
    from ..firmware.pipeline import describe, dispatch_params

    by_id = {i.id: i for i in project.items}
    for item in project.items:
        if item.status == "needs_user":
            continue
        if any(by_id[d].status in _BAD for d in item.depends_on
               if d in by_id):
            item.status = "blocked"
            item.note = "blocked: a dependency did not complete"
            store.save(project)
            continue

        d = route(Utterance.from_text(item.command), vocab)
        try:
            if d.kind == "work":
                item.status = "running"
                store.save(project)
                pipeline = pipeline_factory(item.id)
                report = pipeline.run(ctl=ctl, **dispatch_params(d))
                item.status = "done" if report.outcome == "green" else "blocked"
                item.note = describe(report)
            else:
                item.note = chat(item.command)
                item.status = "answered"
        except TaskStopped:
            item.status = "stopped"
            item.note = "stopped by the user"
            store.save(project)
            raise
        store.save(project)
        if ctl is not None:
            ctl.checkpoint(f"ITEM:{item.id}")

    done = sum(1 for i in project.items if i.status == "done")
    answered = sum(1 for i in project.items if i.status == "answered")
    blocked = sum(1 for i in project.items if i.status == "blocked")
    needs_user = sum(1 for i in project.items if i.status == "needs_user")
    if blocked == 0 and needs_user == 0:
        outcome = "completed"
    elif done or answered:
        outcome = "partial"
    else:
        outcome = "blocked"
    return ProjectResult(outcome=outcome, done=done, answered=answered,
                         blocked=blocked, needs_user=needs_user)
