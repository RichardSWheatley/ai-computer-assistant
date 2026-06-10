# Architecture

This document outlines the design of a **top-tier, locally-run AI assistant**
that can see the screen, control the computer, write software, and handle
business workflows (Teams, Outlook, PowerPoint).

## 1. Design principles

1. **Local-first, cloud-optional.** Default to a local LLM for privacy and
   offline use; allow opting into a frontier cloud model for hard reasoning.
2. **Perceive → Plan → Act → Verify.** Every action closes a loop: observe the
   result before taking the next step. Never fire blind sequences.
3. **Human-in-the-loop for risk.** Destructive, financial, or outward-facing
   actions (send email, delete files, post in Teams) require confirmation
   unless explicitly pre-authorized.
4. **Everything is a tool.** Capabilities are pluggable tools behind a uniform
   interface, so new skills (apps, APIs) drop in without touching the core.
5. **Auditable.** Every observation and action is logged, replayable, and
   reversible where possible.

## 2. System components

### 2.1 Orchestrator (agent loop)
The brain. Runs the **Perceive → Plan → Act → Verify** loop, maintains task
state, short/long-term memory, and decides which tool to call next.

### 2.2 Planner (LLM)
Turns a high-level goal ("fix this bug", "build a deck for Q3") into a sequence
of steps. Supports:
- **Tool calling** for deterministic actions.
- **Reflection / re-planning** when a step fails or the screen doesn't match.
- **Model routing**: small/fast local model for routine steps, large model for
  hard reasoning.

### 2.3 Perception layer
How the assistant "sees":
- **Screen capture** — periodic or on-demand screenshots.
- **Vision model** — a multimodal model locates UI elements, reads text, and
  describes state. Returns elements with bounding boxes and labels.
- **Accessibility (a11y) tree** — on Windows, the UI Automation API gives
  structured, reliable element data (buttons, fields, values). This is far more
  robust than pixels alone; vision is the fallback for non-accessible UIs.
- **OCR** — for text inside images/canvases the a11y tree can't expose.
- **Element grounding** — fuses vision + a11y into a single list of
  addressable, clickable targets.

### 2.4 Action layer
How the assistant "acts" (all simulated input):
- **Mouse** — move, click, double-click, right-click, drag, scroll.
- **Keyboard** — type text, key combos, hotkeys.
- **Window/app control** — launch programs, focus/switch/resize windows.
- **Clipboard** — read/write for reliable text transfer.
- **Safety guard** — rate limiting, a global kill-switch hotkey, and an
  "are you sure?" gate for flagged actions.

### 2.5 Tool / Skill router
A registry of tools with typed schemas. Categories:
- **OS & desktop**: launch app, file ops, clipboard, screenshot.
- **Computer use**: click, type, scroll (the action layer, exposed as tools).
- **Developer**: shell, git, run tests, read/edit files, IDE control.
- **Business**: Microsoft Graph (Teams/Outlook/Calendar), PowerPoint builder.
- **Web**: search, fetch, scrape.
- **Memory**: store/recall facts, project context.

### 2.6 Integrations
Prefer **APIs over UI automation** whenever one exists — they're faster and
more reliable. Drive the GUI only when no API exists.
- **Microsoft 365** via **Microsoft Graph API** (Teams, Outlook mail, Calendar,
  OneDrive/SharePoint).
- **PowerPoint** via `python-pptx` (+ a rendering/asset pipeline for graphics).
- **Git/GitHub**, IDE (VS Code) extensions, terminals.

### 2.7 Memory
- **Working memory** — current task, recent screenshots/actions.
- **Episodic memory** — past task transcripts for replay/learning.
- **Semantic memory** — a vector store of project docs, code, and user prefs
  (RAG) so the assistant knows your stack and style.

### 2.8 Local UI / overlay HUD
- A lightweight desktop app: chat panel, live "what I see / what I'll do next"
  overlay, approval prompts, and the kill switch.
- Optional **voice** in/out (wake word, speech-to-text, text-to-speech).

## 3. The core loop

```
goal ──▶ Planner ──▶ next step
              ▲            │
              │            ▼
        Verify result   Tool Router ──▶ Perception | Action | Integration
              ▲            │
              └────────────┘  (observe new screen state, repeat)
```

1. **Perceive**: screenshot + a11y tree → grounded element list.
2. **Plan**: LLM picks the next tool call given the goal + current state.
3. **Act**: execute the tool (click, type, API call, run command).
4. **Verify**: re-perceive; did the state change as expected? If not, re-plan.
5. Repeat until the goal is met or a confirmation/escalation is needed.

## 4. Security & safety model

- **Permission tiers**: read-only (free), local-write (light confirm),
  outward-facing/destructive (explicit confirm + audit).
- **Sandboxing**: code execution in a contained workspace; allow-list for
  shell commands.
- **Secrets**: OS keychain / credential vault; never in plaintext config.
- **Kill switch**: global hotkey instantly halts all simulated input.
- **Audit log**: append-only record of every observation and action.
- **Data boundaries**: local model keeps sensitive screens off the cloud;
  cloud routing is opt-in and redaction-aware.

## 5. Why local-first matters here

The assistant sees your screen and reads your email — that's highly sensitive.
A local model (e.g. via Ollama / llama.cpp) keeps that data on-device. Heavy
reasoning can still route to a frontier model, but only with redaction and your
consent. This gives privacy by default with power on demand.

See [TECH-STACK.md](TECH-STACK.md) for concrete library choices and
[TOP-10-REQUIREMENTS.md](TOP-10-REQUIREMENTS.md) for the build priority.
