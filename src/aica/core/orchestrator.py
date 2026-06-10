"""The orchestrator: the Perceive -> Plan -> Act -> Verify loop.

This is the brain. It is deliberately backend-agnostic: it holds references to
the abstract Perception / LLMProvider / ToolRegistry and drives the loop. A
kill switch and a permission gate wrap every action.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import events
from .events import EventBus
from .interfaces import LLMProvider, Perception, ToolCall
from .registry import ToolRegistry


@dataclass
class StepLog:
    step: int
    state_summary: str
    call: ToolCall
    ok: bool
    detail: str = ""


@dataclass
class RunResult:
    goal: str
    finished: bool
    steps: list[StepLog] = field(default_factory=list)
    message: str = ""


class Orchestrator:
    # The "done" tool any plugin/planner can emit to end the task.
    DONE_TOOL = "task_complete"

    def __init__(
        self,
        perception: Perception,
        planner: LLMProvider,
        registry: ToolRegistry,
        *,
        bus: EventBus | None = None,
        kill_switch=None,
        confirm=None,          # callable(ToolCall) -> bool for gated actions
        max_steps: int = 20,
    ) -> None:
        self.perception = perception
        self.planner = planner
        self.registry = registry
        self.bus = bus or EventBus()
        self.kill_switch = kill_switch
        self.confirm = confirm
        self.max_steps = max_steps

    def _gated(self, call: ToolCall) -> bool:
        """Return True if the action is allowed to proceed."""
        tier = self.registry.tier(call.tool)
        if tier == "read_only":
            return True
        if self.confirm is None:
            return True  # no gate wired up -> allow (dev/headless default)
        return bool(self.confirm(call))

    def run(self, goal: str) -> RunResult:
        result = RunResult(goal=goal, finished=False)
        self.bus.publish(events.TASK_STARTED, goal)
        history: list[dict] = []

        for step in range(1, self.max_steps + 1):
            if self.kill_switch is not None and self.kill_switch.triggered:
                result.message = "Halted by kill switch."
                break

            # 1. PERCEIVE
            state = self.perception.observe()
            self.bus.publish(events.SCREEN_CHANGED, state)

            # 2. PLAN
            call = self.planner.plan(goal, state, self.registry.schemas(), history)

            if call.tool == self.DONE_TOOL:
                result.finished = True
                result.message = call.reasoning or "Task complete."
                result.steps.append(StepLog(step, state.summary, call, True, "done"))
                break

            # gate risky actions
            if not self._gated(call):
                result.steps.append(
                    StepLog(step, state.summary, call, False, "declined by user"))
                result.message = "Action declined."
                break

            # 3. ACT
            tool_result = self.registry.dispatch(call)
            self.bus.publish(events.ACTION_EXECUTED, (call, tool_result))

            # 4. VERIFY (record; planner re-perceives next iteration)
            history.append({
                "tool": call.tool, "args": call.args,
                "ok": tool_result.ok, "output": str(tool_result.output)[:500],
                "error": tool_result.error,
            })
            result.steps.append(StepLog(
                step, state.summary, call, tool_result.ok,
                tool_result.error or str(tool_result.output)[:200]))

            if not tool_result.ok:
                self.bus.publish(events.ERROR_RAISED, tool_result.error)
                # loop continues -> planner can re-plan around the failure

        else:
            result.message = f"Reached max steps ({self.max_steps})."

        self.bus.publish(events.TASK_FINISHED, result)
        return result
