"""The orchestrator: the Perceive -> Plan -> Act -> Verify loop.

This is the brain. It is deliberately backend-agnostic: it holds references to
the abstract Perception / LLMProvider / ToolRegistry and drives the loop. A
kill switch and a permission gate wrap every action.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..security.policy import SecurityPolicy
from ..security.quarantine import Quarantine
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
        confirm=None,          # callable(ToolCall) -> bool; the human yes/no prompt
        max_steps: int = 20,
        policy: SecurityPolicy | None = None,
        quarantine: Quarantine | None = None,
        audit=None,
    ) -> None:
        self.perception = perception
        self.planner = planner
        self.registry = registry
        self.bus = bus or EventBus()
        self.kill_switch = kill_switch
        self.confirm = confirm
        self.max_steps = max_steps
        self.policy = policy or SecurityPolicy()
        self.quarantine = quarantine or Quarantine()
        self.audit = audit
        self._suspicious = False  # set when the latest untrusted input looks hostile

    def _needs_confirmation(self, call: ToolCall) -> bool:
        tier = self.registry.tier(call.tool)
        return self.policy.needs_confirmation(tier, untrusted_context=self._suspicious)

    def _gated(self, call: ToolCall) -> bool:
        """Return True if the action is allowed to proceed."""
        if not self._needs_confirmation(call):
            return True
        # Confirmation is required. Secure default: no human confirmer -> deny.
        if self.confirm is None:
            return False
        return bool(self.confirm(call))

    def would_allow(self, call: ToolCall) -> bool:
        """Public view of the gate (for UIs/tests) under current suspicion state."""
        return self._gated(call)

    def run(self, goal: str) -> RunResult:
        result = RunResult(goal=goal, finished=False)
        self.bus.publish(events.TASK_STARTED, goal)
        history: list[dict] = []

        for step in range(1, self.max_steps + 1):
            if self.kill_switch is not None and self.kill_switch.triggered:
                result.message = "Halted by kill switch."
                break

            # 1. PERCEIVE -> QUARANTINE. The privileged planner only ever sees
            # sanitized, typed data; raw untrusted content is contained here.
            raw_state = self.perception.observe()
            sanitized = self.quarantine.sanitize_state(raw_state)
            self._suspicious = sanitized.suspicious
            safe_state = sanitized.to_state()
            self.bus.publish(events.SCREEN_CHANGED, safe_state)

            # 2. PLAN (on sanitized observation only)
            call = self.planner.plan(goal, safe_state, self.registry.schemas(), history)

            if call.tool == self.DONE_TOOL:
                result.finished = True
                result.message = call.reasoning or "Task complete."
                result.steps.append(StepLog(step, safe_state.summary, call, True, "done"))
                break

            # gate risky actions (provenance binding: suspicion escalates the bar)
            if not self._gated(call):
                reason = ("blocked: action needs confirmation after suspicious "
                          "content" if self._suspicious else "declined (needs confirmation)")
                result.steps.append(
                    StepLog(step, safe_state.summary, call, False, reason))
                result.message = reason
                break

            # 3. ACT
            tool_result = self.registry.dispatch(call)
            self.bus.publish(events.ACTION_EXECUTED, (call, tool_result))

            # 4. VERIFY. Tool output is untrusted too -> sanitize before it enters
            # history, and let it raise suspicion for the next step's gating.
            clean_out, out_finding = self.quarantine.sanitize_text(
                str(tool_result.output), source=f"tool:{call.tool}")
            if out_finding.suspicious:
                self._suspicious = True
            history.append({
                "tool": call.tool, "args": call.args,
                "ok": tool_result.ok, "output": clean_out[:500],
                "error": tool_result.error,
            })
            result.steps.append(StepLog(
                step, safe_state.summary, call, tool_result.ok,
                tool_result.error or clean_out[:200]))

            if not tool_result.ok:
                self.bus.publish(events.ERROR_RAISED, tool_result.error)
                # loop continues -> planner can re-plan around the failure

        else:
            result.message = f"Reached max steps ({self.max_steps})."

        self.bus.publish(events.TASK_FINISHED, result)
        return result
