# Roadmap & Status

A phased plan that delivers something runnable early, then layers on power.
This file is the **single source of truth for what's done and what's next** —
start here to move the project forward.

## Status snapshot (what's built)

| Area | Status | Branch |
|---|---|---|
| Modular agent core, plugin system, VRAM-aware config | ✅ shipped | `feature/core-and-modularity` |
| Polyglot worker boundary (Python⇄native RPC) | ✅ shipped | `feature/polyglot-worker` |
| Operating modes + Claude/Ollama planners + hardware routing | ✅ shipped | `feature/llm-modes-and-planners` |
| Local desktop control (capture, a11y, input, click-by-label) | ✅ shipped | `feature/local-desktop-control` |
| Business: Graph (Outlook/Teams/Calendar) + PowerPoint | ✅ shipped (opt-in) | `feature/business-microsoft365` |
| Security: trust/quarantine, injection defense, egress, DLP, audit | ✅ shipped | `feature/security-and-hardening` (tip) |

The latest cumulative tip is `feature/workflows`. **97 tests pass.** Runs
headless via mock backends; real backends (GPU model, desktop control, M365,
office docs) are opt-in.

## Recently completed (security hardening + features)

| Item | Status | Branch |
|---|---|---|
| Worker sandbox (scrubbed env, cwd, rlimits, no-network) | ✅ shipped | `feature/worker-sandboxing` |
| Quarantined-LLM split (no-tools digest, re-scanned) | ✅ shipped | `feature/quarantine-llm` |
| Secret vault (OS keychain + `vault:` refs) | ✅ shipped | `feature/secret-vault` |
| Interactive confirmation (`rita run --confirm`) | ✅ shipped | `feature/control-ui` |
| Word (.docx) + Excel (.xlsx) generation | ✅ shipped | `feature/office-docs` |
| Workflows engine + persistent memory/RAG | ✅ shipped | `feature/workflows` |
| Weekend path: no-key `rita doc` CLI, `--live`, no-GPU routing | ✅ shipped | `feature/weekend-quickstart` |
| Voice I/O: mic→Whisper→task→TTS speaker (`rita talk`) | ✅ shipped | `feature/voice-io` |
| Push-to-talk (press Enter to talk) | ✅ shipped | `feature/voice-io` (tip) |
| Wake-word ("Hey RITA") always-on trigger | ⏳ next | — |

## What's next (remaining backlog)

1. **Programmer mode** — sandboxed shell, git, test runner, codebase RAG so it
   can fix bugs in your repo. → `feature/programmer-mode`
2. **Overlay HUD (GUI)** — a desktop window: chat, live "what I'll do next"
   preview, approve/deny buttons, kill switch. (CLI approval exists today.)
   → `feature/overlay-hud`
3. **AI imagery for decks** — generated hero/background images in PPTX.
   → `feature/deck-imagery`
4. **Real on-device tuning** — exercise the Windows/macOS a11y traversals and the
   Claude/Ollama planners against a real GPU box; calibrate. → on your hardware
5. **Rust worker binary** — implement the worker protocol natively for the hot
   capture/input path + single-binary distribution. → `feature/rust-worker`

## Phase view (original plan, for reference)

- **Phase 0–1 — Foundations + Computer use:** ✅ done.
- **Phase 3–4 — Business + documents:** ✅ first cut done (Outlook/Teams/PPTX).
- **Phase 2 — Programmer mode** (sandboxed shell, git, test runner, codebase RAG): ⬜ next.
- **Phase 5 — Polish, safety & UX** (HUD, voice, preferences memory): ⬜ partial (security done; UI pending).
- **Phase 6 — Workflows & plugin SDK:** ⬜ pending.

## Branching & workflow

- **No `claude/` branches.** Use descriptive `feature/<area>` branches.
- Work is currently stacked on `feature/security-and-hardening` (the full
  project). Branch new work as `feature/<name>` from the tip, named for what it
  delivers.
- Commit per logical change; keep `pytest` green (`pip install -e ".[dev]" && pytest -q`).
- Open a PR per feature branch when ready (none open yet).

