"""The polyglot boundary: Python brain <-> native (Rust) worker.

This package defines a small, versioned RPC contract so the latency- and
reliability-critical layer (screen capture, input injection, kill switch) can be
a separate native process while the orchestrator stays in Python.

Transport: newline-delimited JSON over the worker's stdin/stdout (simple,
debuggable, language-agnostic). Bulk data (screen frames) is passed by file/
shared-memory *path*, never inlined. A Rust worker just needs to speak this
same protocol — see docs/adr/0002-polyglot-worker-boundary.md and
docs/WORKER-PROTOCOL.md.
"""
