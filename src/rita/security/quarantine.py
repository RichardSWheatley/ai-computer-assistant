"""Quarantine boundary — the structural defense against prompt injection.

The privileged planner (which holds the tools/capabilities) must never read raw
untrusted free-text. Everything observed (screen, email, web, tool output) first
passes through the Quarantine, which:

  - neutralizes invisible/bidi characters,
  - coerces observations into a strict, length-bounded, typed shape,
  - scans for injection and attaches a risk signal,
  - (optionally) routes free-text through a Q-LLM that has NO tools and whose
    output is itself re-scanned — so even a model-summarized field can't smuggle
    instructions back to the privileged planner.

Injected instructions can't survive the schema coercion + scan, so the planner
reasons over data, not attacker commands. See docs/SECURITY.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.interfaces import Element, ScreenState
from .injection import InjectionFinding, neutralize, scan


@dataclass
class SanitizedObservation:
    summary: str
    elements: list[Element] = field(default_factory=list)
    finding: InjectionFinding = field(default_factory=InjectionFinding)

    @property
    def suspicious(self) -> bool:
        return self.finding.suspicious

    def to_state(self) -> ScreenState:
        # The planner never receives the raw screenshot path either.
        return ScreenState(summary=self.summary, elements=self.elements,
                           screenshot_path=None)


class Quarantine:
    def __init__(self, max_elements: int = 80, max_label: int = 120,
                 max_text: int = 4000, q_llm=None) -> None:
        self.max_elements = max_elements
        self.max_label = max_label
        self.max_text = max_text
        self.q_llm = q_llm  # optional callable(text) -> str, NO tool access

    def sanitize_text(self, text: str, source: str = "observation"
                      ) -> tuple[str, InjectionFinding]:
        finding = scan(text or "")
        clean = neutralize(text or "")[: self.max_text]
        if self.q_llm is not None:
            try:  # the Q-LLM output is untrusted too -> re-neutralize + re-scan
                summarized = self.q_llm(clean)
                clean = neutralize(str(summarized))[: self.max_text]
                f2 = scan(clean)
                finding = InjectionFinding(
                    risk=max(finding.risk, f2.risk),
                    reasons=finding.reasons + f2.reasons)
            except Exception:
                pass  # fall back to the rule-based sanitized text
        return clean, finding

    def sanitize_state(self, state: ScreenState) -> SanitizedObservation:
        text_parts = [state.summary or ""]
        elements: list[Element] = []
        for e in (state.elements or [])[: self.max_elements]:
            label = neutralize(e.label)[: self.max_label]
            text_parts.append(label)
            elements.append(Element(label=label, role=e.role, x=e.x, y=e.y,
                                    source=e.source))
        finding = scan("\n".join(text_parts))
        return SanitizedObservation(
            summary=neutralize(state.summary or "")[: self.max_text],
            elements=elements, finding=finding)
