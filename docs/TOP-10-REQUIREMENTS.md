# Top 10 Things We Need

The ten building blocks for a top-tier local AI assistant, in **priority /
dependency order**. Each is a component you can build and test on its own.

---

### 1. Agent orchestrator (the brain) 🧠
The core **Perceive → Plan → Act → Verify** loop with tool-calling, memory, and
re-planning on failure. Everything else plugs into this.
**Why first:** nothing works without the loop that ties perception, reasoning,
and action together.

### 2. LLM / reasoning engine with model routing 🤖
A planner backed by an LLM. Local model (Ollama / llama.cpp) for privacy +
speed; optional frontier cloud model for hard problems. Structured tool-calling
output is mandatory.
**Why:** the quality of the assistant is the quality of its reasoning.

### 3. Screen perception (vision + accessibility tree) 👁️
Screen capture → element grounding via a **vision model + Windows UI Automation
+ OCR**. Produces a list of clickable, labeled targets with coordinates.
**Why:** the assistant can't act reliably on what it can't accurately see.

### 4. Computer control / action layer (mouse, keyboard, windows) 🖱️
Simulated input: move/click/drag the mouse, type text and hotkeys, launch and
switch apps, manage the clipboard — with a global **kill switch**.
**Why:** this is the "hands." Pair it with #3 (the "eyes") for true computer use.

### 5. Tool/skill framework with a uniform schema 🧩
A registry where every capability (OS, dev, business, web) is a typed,
discoverable tool. Makes the system extensible without touching the core.
**Why:** keeps the assistant open-ended — add Outlook, Photoshop, anything later.

### 6. Developer toolkit (the programmer superpowers) 💻
Shell execution (sandboxed), git, run/observe tests, read & edit files, project
RAG over your codebase, and IDE/terminal control. Code review and debugging
workflows built in.
**Why:** this is what makes it a *programmer's* assistant, not a generic bot.

### 7. Business integrations via Microsoft Graph 🏢
**Teams** (read/post messages, channels, meetings), **Outlook** (read/compose/
send mail, triage inbox), **Calendar** (schedule, find times). API-first, not UI
scraping. See [BUSINESS-CAPABILITIES.md](BUSINESS-CAPABILITIES.md).
**Why:** covers the "work in Teams / make emails in Outlook" requirement cleanly.

### 8. Document & presentation generation (PPTX with immense graphics) 📊
A PowerPoint builder (`python-pptx`) plus a **graphics/asset pipeline**:
templated layouts, charts, diagrams, icon sets, and AI-generated imagery. Also
Word/Excel and PDF.
**Why:** "build PPTX files with immense graphics" is a flagship business feature.

### 9. Memory & context store (RAG + preferences) 📚
Vector DB for project knowledge, past tasks, and your personal style/preferences
so the assistant stays consistent and gets smarter over time.
**Why:** turns a stateless bot into an assistant that actually knows *you*.

### 10. Security, permissions & the control UI 🔒
Permission tiers, confirmation gates, secret vault, audit log, sandboxing — plus
the **overlay HUD** (chat, "what I'll do next" preview, approvals) and optional
voice. The kill switch lives here.
**Why:** an assistant with this much power is only acceptable if it's safe,
transparent, and instantly stoppable.

---

## Dependency map

```
1 Orchestrator
├── 2 LLM + routing        (brain)
├── 3 Perception           ┐
├── 4 Action layer         ┘ together = "computer use"
├── 5 Tool framework
│     ├── 6 Developer toolkit
│     ├── 7 Business / Graph
│     └── 8 Doc & PPTX generation
├── 9 Memory / RAG
└── 10 Security + Control UI  (wraps everything)
```

**Minimum viable assistant** = 1 + 2 + 3 + 4 + 5 + a slice of 10 (kill switch).
That gives a safe agent that can see the screen and operate the computer. Layers
6–9 then turn it into the programmer + business powerhouse.
