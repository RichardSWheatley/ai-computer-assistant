# AI Computer Assistant

A locally-run, top-tier AI assistant for programmers **and** business users.

It can **see your screen**, **control the mouse and keyboard** (simulated input),
**open and drive programs**, and act as a hands-on pair-programmer. On the
business side it works inside **Microsoft Teams, Outlook, and PowerPoint** —
drafting emails, managing chats and meetings, and generating richly-designed
`.pptx` decks.

> **Status:** Design / outline phase. This repository currently contains the
> architecture, requirements, and roadmap. See [`docs/`](docs/) for the full plan.

---

## What it does

| Capability | Description |
|---|---|
| 👁️ **Screen vision** | Captures the screen and understands UI elements via a vision model + accessibility tree. |
| 🖱️ **Computer control** | Moves/clicks the mouse and types via simulated input. Opens and switches between apps. |
| 🧑‍💻 **Programmer mode** | Reads/writes code, runs commands, debugs, reviews diffs, drives the IDE and terminal. |
| 🏢 **Business mode** | Teams messaging, Outlook email + calendar, and PowerPoint deck generation with strong graphics. |
| 🧠 **Local-first** | Runs on your PC. Local LLM option for privacy; cloud models optional for heavy reasoning. |
| 🔒 **Safe by design** | Sandboxed actions, confirmation gates for risky operations, full audit log. |

## Status: runnable MVP skeleton

Phase 0 + 1 is scaffolded and runs **headless with zero heavy deps** (mock
providers), so the agent loop is testable anywhere before you set up a GPU.
First-pass desktop targets are **Windows and macOS**.

```bash
pip install -e .
aica doctor                          # detected GPU/VRAM, backend, model pick
aica run "type hello into notepad"   # perceive -> plan -> act -> verify
```

See **[docs/QUICKSTART.md](docs/QUICKSTART.md)** to enable real GPU/perception/control.

## Documentation

- **[Quickstart](docs/QUICKSTART.md)** — install, run, and enable real backends.
- **[Architecture](docs/ARCHITECTURE.md)** — system design, components, and data flow.
- **[Top 10 Requirements](docs/TOP-10-REQUIREMENTS.md)** — the ten things we need to build, in priority order.
- **[Modularity & Plugins](docs/MODULARITY.md)** — how features drop in without touching the core.
- **[Performance & Hardware](docs/PERFORMANCE.md)** — speed strategy, VRAM/RAM, and recommended hardware.
- **[Worker Protocol](docs/WORKER-PROTOCOL.md)** — the Python⇄native (Rust) boundary contract.
- **[Decisions (ADRs)](docs/adr/)** — language choice & polyglot architecture.
- **[Business Capabilities](docs/BUSINESS-CAPABILITIES.md)** — Teams, Outlook, PowerPoint, and more.
- **[Roadmap](docs/ROADMAP.md)** — phased delivery plan.
- **[Tech Stack](docs/TECH-STACK.md)** — concrete library and tooling choices.

## High-level architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         User (you)                           │
└───────────────┬──────────────────────────────┬───────────────┘
                │ voice / text / hotkey         │ sees overlay
        ┌───────▼────────┐             ┌─────────▼─────────┐
        │   Orchestrator │◀───────────▶│   Local UI /      │
        │  (agent loop)  │             │   overlay HUD     │
        └───┬───────┬────┘             └───────────────────┘
            │       │
   ┌────────▼─┐  ┌──▼─────────────┐
   │  Planner │  │   Tool Router  │
   │  (LLM)   │  └──┬─────┬─────┬──┘
   └──────────┘     │     │     │
        ┌───────────▼┐ ┌──▼───┐ ┌▼────────────┐
        │ Perception │ │Action│ │ Skills /    │
        │ (vision +  │ │(mouse│ │ Integrations│
        │  a11y tree)│ │/kbd) │ │ (MS Graph,  │
        └────────────┘ └──────┘ │  Git, IDE)  │
                                └─────────────┘
```

## Quick start

> Not yet implemented — this is the design phase. The roadmap in
> [`docs/ROADMAP.md`](docs/ROADMAP.md) describes the first runnable milestone.
