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

All of the above is on `feature/security-and-hardening` (the cumulative tip).
**70 tests pass.** Runs headless via mock backends; real backends are opt-in.

## What's next (prioritized backlog — pick the top item)

1. **Sandbox the native worker / code execution** — restricted container: no
   secret access, read-only FS where possible, egress-filtered. → `feature/worker-sandboxing`
2. **Quarantined-LLM model split** — wire a no-tools Q-LLM behind the existing
   `Quarantine(q_llm=…)` hook so untrusted free-text is model-summarized and
   re-scanned before the privileged planner sees it. → `feature/quarantine-llm`
3. **Secret vault + proxy injection** — OS keychain; credentials injected after
   a request leaves the sandbox (never in prompts/screenshots). → `feature/secret-vault`
4. **Interactive confirmation UI / overlay HUD** — real human approval for the
   gated outward/destructive actions; "what I'll do next" preview. → `feature/control-ui`
5. **Word/Excel generation** alongside PPTX. → `feature/office-docs`
6. **Composed workflows** ("prep me for the 9am" → calendar + mail + Teams + deck)
   and a memory/RAG store. → `feature/workflows`

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

