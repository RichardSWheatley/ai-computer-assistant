# ADR 0002 — Polyglot: native worker for the hot path

**Status:** accepted · **Date:** 2026-06-10

## Context

ADR 0001 chose Python for the brain. But some areas genuinely favor a native
language (Rust): the **screen-capture loop**, **input injection**, the **kill
switch**, and **single-binary distribution**. "Write each part in the language
that wins, then link them" is the goal.

## Decision

Split the system across a **process boundary**:

- **Python brain process** — orchestrator, LLM routing, RAG, Office gen,
  business plugins.
- **Native worker process** (Rust in production; a Python reference worker
  today) — screen capture, accessibility tree, input injection, kill switch.

They communicate over a small **versioned RPC contract**
(docs/WORKER-PROTOCOL.md): newline-JSON over stdio, with bulk frames passed by
path. The Python `Perception`/`ActionExecutor` interfaces have worker-backed
adapters (`workers/proxy.py`), so the orchestrator is unaware of the language
on the other side.

## Why this works cleanly

- The **modular interfaces already define the seam** — swapping in a worker is a
  config flag (`use_native_worker`), not a refactor.
- The Rust worker is introduced **incrementally**: ship Python-only, then
  replace the reference worker with a binary that speaks the same protocol
  (`worker_command = ["rita-worker"]`) — no brain-side changes.
- Each side uses its best ecosystem: Python's AI/Office libraries, Rust's
  latency, memory safety, and single-binary packaging (incl. a Tauri shell).

## Consequences

- A serialization boundary exists; keep bulk data (frames) off the JSON channel
  via shared-memory/file paths.
- Two runtimes to package — mitigated because the worker is a single static
  binary and the brain is a standard Python app.
- Protocol must be versioned and kept in one place
  (`src/rita/workers/protocol.py`).

## Status of implementation

- ✅ Protocol, client, proxies, and a runnable Python reference worker exist and
  are covered by tests (`tests/test_worker.py`) — the boundary is proven.
- ⬜ Rust worker binary — future work; implement the same protocol.
