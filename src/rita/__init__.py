"""RITA — Routing, Iteration, Testing, Automation.

A deterministic orchestrator with a speech front end for Zephyr firmware
work (formerly AICA, the AI computer assistant — the legacy desktop-agent
capabilities remain under `rita run`).

Core stays dependency-light and runs headless with mock providers, so the
agent loop is testable anywhere. Real perception/action/LLM backends are
optional plugins/extras you enable per machine.
"""

__version__ = "0.34.3"
