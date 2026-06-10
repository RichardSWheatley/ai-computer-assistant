# ADR 0001 — Primary language: Python for the brain

**Status:** accepted · **Date:** 2026-06-10

## Context

The assistant needs local model serving, vision/OCR, RAG, GUI automation +
accessibility trees, and Office generation (PPTX/Word/Excel) — plus fast
iteration on agent logic. Rust was considered as an alternative.

## Decision

Use **Python** as the primary language for the orchestrator, LLM routing,
memory/RAG, and all business/Office integrations.

## Rationale

- **The ecosystem is the product.** `python-pptx`/`python-docx`/`openpyxl`,
  Ollama/transformers, OCR, embeddings, and `pywinauto`/`pyobjc` accessibility
  bindings are Python-first. A Rust equivalent of `python-pptx` alone is months
  of work.
- **Performance lives elsewhere.** End-to-end latency is dominated by GPU/model
  serving and OS/screen I/O, not orchestrator glue. The model engines are
  already native (C++/Rust) regardless of host language, so Python as conductor
  costs little of the speed that matters (see docs/PERFORMANCE.md).
- **Iteration speed.** Agent logic changes constantly; Python shortens the loop.

## Consequences

- Single-binary distribution and a tight native capture/input loop are *not*
  Python's strengths — addressed by ADR 0002 (polyglot worker boundary).
- If the project ever drops local models **and** local Office generation
  (cloud-only), this decision should be revisited — Rust becomes attractive.
