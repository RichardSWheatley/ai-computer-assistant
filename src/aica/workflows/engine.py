"""Workflow engine — run a saved sequence of goals through the assistant.

A Workflow is an ordered list of natural-language goals. The engine runs each
through the same Orchestrator, so every step inherits the security gates
(confirmation, quarantine, egress, audit). It stops early if a step is declined
or fails, so a blocked outward action can't be silently skipped.

Built-in templates ("daily_brief", "meeting_prep") are starting points; users
can define their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Workflow:
    name: str
    description: str
    steps: list[str] = field(default_factory=list)


@dataclass
class WorkflowResult:
    name: str
    completed: bool
    step_results: list = field(default_factory=list)
    message: str = ""


BUILTINS: dict[str, Workflow] = {
    "daily_brief": Workflow(
        name="daily_brief",
        description="Summarize overnight activity across mail, chat, and calendar.",
        steps=[
            "Summarize my unread Outlook inbox.",
            "Summarize what I missed in my Teams channels.",
            "List today's calendar events and flag conflicts.",
        ],
    ),
    "meeting_prep": Workflow(
        name="meeting_prep",
        description="Prepare for the next meeting from its invite and related threads.",
        steps=[
            "Find my next calendar event and its attendees.",
            "Pull the related Outlook email thread and summarize it.",
            "Draft talking points for the meeting.",
        ],
    ),
}


class WorkflowEngine:
    def __init__(self, assistant) -> None:
        # `assistant` is anything with .run(goal) -> RunResult (an Orchestrator).
        self.assistant = assistant

    def run(self, workflow: Workflow) -> WorkflowResult:
        result = WorkflowResult(name=workflow.name, completed=False)
        for goal in workflow.steps:
            step = self.assistant.run(goal)
            result.step_results.append(step)
            if not getattr(step, "finished", False):
                result.message = f"stopped at step: {goal!r} ({step.message})"
                return result
        result.completed = True
        result.message = f"completed {len(workflow.steps)} steps"
        return result

    def run_named(self, name: str) -> WorkflowResult:
        if name not in BUILTINS:
            raise KeyError(f"unknown workflow: {name}")
        return self.run(BUILTINS[name])
