# Roadmap

A phased plan that delivers something runnable early, then layers on power.
Each phase is shippable on its own.

## Phase 0 — Foundations (skeleton)
- Repo, packaging, config, secret vault, logging/audit scaffolding.
- Orchestrator loop stub + tool registry (#1, #5).
- Plug in a local LLM with tool-calling (#2).
- **Kill switch** from day one (#10, minimal).
- ✅ *Outcome:* the agent can take a goal and call a trivial tool.

## Phase 1 — Computer use (MVP)
- Screen capture + a11y tree + OCR → element grounding (#3).
- Mouse/keyboard/window/app control as tools (#4).
- Perceive → Plan → Act → **Verify** working end to end.
- ✅ *Outcome:* "open Notepad and type a haiku" works reliably and safely.

## Phase 2 — Programmer mode
- Sandboxed shell, git, file read/edit, test runner (#6).
- Codebase RAG so it knows your project (#9, first slice).
- IDE/terminal control.
- ✅ *Outcome:* "find and fix this bug, run the tests" works.

## Phase 3 — Business: Outlook + Teams + Calendar
- Microsoft Graph auth (OAuth/MSAL) + scopes (#7).
- Read/triage/draft email with confirm-before-send.
- Teams read/post/summarize; calendar scheduling.
- ✅ *Outcome:* "summarize my inbox and draft replies" works.

## Phase 4 — Document & presentation generation
- PPTX builder + layout engine + graphics/chart/diagram pipeline (#8).
- AI imagery for hero slides/backgrounds.
- Word/Excel generation.
- ✅ *Outcome:* "build a Q3 deck from this spreadsheet" produces a polished `.pptx`.

## Phase 5 — Polish, safety & UX
- Overlay HUD: chat, "what I'll do next" preview, approvals (#10).
- Permission tiers, full audit UI, redaction-aware cloud routing.
- Optional voice in/out.
- Memory of personal style/preferences across tasks (#9, full).
- ✅ *Outcome:* a safe, transparent, daily-driver assistant.

## Phase 6 — Workflows & extensibility
- Saved multi-step workflows ("prep me for the 9am", "monthly report").
- Plugin SDK so anyone can add new app/skill integrations.
- ✅ *Outcome:* one command chains email + Teams + docs + deck.

---

### Suggested first milestone to build
**Phase 0 + Phase 1** = a safe agent that sees the screen and operates the
computer. It's the hardest, most differentiating piece and everything else
builds on it. Recommend starting there.
