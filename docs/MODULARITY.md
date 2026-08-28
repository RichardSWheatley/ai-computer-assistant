# Modularity & Plugin Architecture

Goal: **add new features later without touching the core.** Every capability is
a plugin discovered at runtime. The core only knows the interfaces, never the
concrete features.

## Core principle: stable interfaces, swappable everything

The orchestrator depends on **abstract interfaces**, not concrete classes:

| Interface | Responsibility | Swappable implementations |
|---|---|---|
| `LLMProvider` | plan / reason / tool-call | local (Ollama, llama.cpp), cloud (the cloud model) |
| `Perception` | turn screen → grounded elements | a11y tree, vision model, OCR |
| `Action` | mouse / keyboard / window | pyautogui, pydirectinput |
| `MemoryStore` | store/recall, RAG | Chroma, sqlite-vec, faiss |
| `Plugin` | a feature with its own tools | anything (see below) |

Swap a local model for another, or the vector DB, by changing one binding — no
ripple through the codebase.

## The plugin contract

Every feature is a plugin that declares its tools and how to run them:

```python
class Plugin(Protocol):
    manifest: Manifest          # name, version, permission_tier, scopes
    def describe(self) -> list[ToolSchema]: ...      # tools it exposes
    def invoke(self, tool: str, args: dict) -> ToolResult: ...
    # optional: subscribe(event_bus), on_load(), on_unload()
```

A `Manifest` (e.g. `plugin.toml`) declares metadata and **least-privilege**
needs:

```toml
[plugin]
name = "outlook"
version = "0.1.0"
permission_tier = "outward_facing"   # gated: confirm before send
scopes = ["graph.mail.read", "graph.mail.send"]
isolation = "process"                # run out-of-process
```

## Discovery & loading

- **Drop-in folder**: `plugins/<name>/` with a manifest + entry point. The core
  scans it at startup (and via Python entry-points for installed packages).
- **Registry**: discovered tools are merged into the Tool Router. The planner
  sees them automatically — no core edits.
- **Hot enable/disable**: turn plugins on/off without rebuilding.

```
plugins/
├── developer/      # shell, git, tests, file edit
├── outlook/        # Graph mail
├── teams/          # Graph chat
├── powerpoint/     # python-pptx + graphics
├── calendar/
└── <your-next-feature>/   ← just add a folder
```

## Isolation & safety

- **Process isolation** (`isolation = "process"`): heavy or risky plugins run as
  a separate process over local RPC. A crash or hang can't take down the agent.
- **Scope enforcement**: a plugin only receives the credentials/scopes its
  manifest declares. The permission tier decides whether actions need a
  confirmation gate.

## Event bus (decoupled extensibility)

Plugins can publish/subscribe to events without the core knowing about them:

```
events: screen_changed, task_started, task_finished,
        action_executed, escalation_requested, error_raised
```

Example: a future "activity logger" or "screenshot annotator" plugin just
subscribes to `action_executed` — zero core changes.

## Versioning

- Tool schemas are versioned; the core tolerates multiple plugin versions.
- Interfaces follow semver so plugins built against v1 keep working.

## Why this shape

It means the roadmap (Outlook, Teams, PPTX, then anything you dream up later) is
purely **additive**: each phase is "write a plugin," never "rewrite the core."
