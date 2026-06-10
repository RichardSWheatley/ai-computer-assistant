"""AICA — a local-first, modular AI computer assistant.

Core stays dependency-light and runs headless with mock providers, so the
agent loop is testable anywhere. Real perception/action/LLM backends are
optional plugins/extras you enable per machine.
"""

__version__ = "0.1.0"
