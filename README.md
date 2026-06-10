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

## Documentation

- **[Architecture](docs/ARCHITECTURE.md)** — system design, components, and data flow.
- **[Top 10 Requirements](docs/TOP-10-REQUIREMENTS.md)** — the ten things we need to build, in priority order.
- **[Modularity & Plugins](docs/MODULARITY.md)** — how features drop in without touching the core.
- **[Performance & Hardware](docs/PERFORMANCE.md)** — speed strategy, VRAM/RAM, and recommended hardware.
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
