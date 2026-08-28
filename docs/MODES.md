# Operating Modes

Two modes. **`auto` is the default and is hardware-driven**; **`local-only`** is a
hard privacy guarantee.

| | `auto` (default) | `local-only` |
|---|---|---|
| Heavy reasoning, **VRAM present** | **local LLM** (the best local model) | local LLM |
| Heavy reasoning, **no VRAM** | **the cloud model** (cloud) | small local model (no cloud) |
| Routine / mechanical steps | small local model | small local model |
| Data leaving the machine | only heavy steps, only when no capable local model (redacted) | **never** |
| Enforcement | router prefers local; cloud only as fallback/escalation | cloud provider **not constructed** |

## The rule, in one line

> **Local LLM is the default when you have VRAM; the cloud model is the default when you
> don't.** A capable local model only exists when there's a GPU to run it, so the
> router simply prefers the best local model and falls back to the cloud model when there
> isn't one.

## How routing works

Each planning step is classified **heavy** vs **light** (`HeuristicClassifier`):

- **Heavy** — deep reasoning: analyze, design, debug, refactor, plan, summarize,
  write/generate, long goals, or when the agent is stuck (recent steps failed).
- **Light** — mechanical: click, type, open, navigate.

Then, in `auto` mode:

- **Heavy** → the **local large model** if one exists (VRAM present); otherwise
  **the cloud model**. A stuck local model (repeated failures) also escalates to the cloud model.
- **Light** → the small local model, for speed.

`router.last_route` records which path each step took (`local-large` /
`local-small` / `cloud`) for logging and the HUD.

## The privacy guarantee is structural

`local-only` is not just a flag checked at call time — the router **refuses to
even hold a cloud provider** in that mode:

```python
if mode is OperatingMode.LOCAL_ONLY and cloud is not None:
    raise ValueError("LOCAL_ONLY mode must not be given a cloud provider")
```

`build_default_planner` never constructs/imports the the cloud model provider when the
mode is local-only. So there is no reachable code path to the network — the
guarantee holds by construction, not by discipline.

## Redaction (when cloud is used)

Before any step goes to the cloud, the router redacts the payload (`_redact`):
the **raw screenshot is dropped** and only the text summary + element metadata go
out. This is the single, testable choke point — extend it to mask secrets/PII in
element text as needed.

## The planners

Both planners implement the same single-step contract (`plan()` returns one
`ToolCall`) via real tool-calling, so they're interchangeable:

- **`OllamaPlanner`** (local) — Ollama tool-calling, GPU-accelerated, fully
  on-device. The default heavy engine when VRAM exists.
- **`the cloud modelPlanner`** (cloud) — the model vendor `your configured cloud model` with adaptive
  thinking and tool-use. The default heavy engine when there's no VRAM. The
  router redacts the screen state before calling it.

## Selecting a mode

```bash
rita run "refactor this module"               # auto: local if VRAM, the cloud model if not
rita run "summarize this contract" --local-only   # privacy, one run
export AICA_LOCAL_ONLY=1                        # force local everywhere
```

or in a config file:

```toml
[rita]
mode = "local-only"   # or "auto"
```

## Graceful degradation

If `auto` would use the cloud but no API key / cloud SDK package is
present, the cloud provider isn't built and heavy steps fall back to the best
available local model (or the small one). The assistant always runs; it never
hard-fails for lack of cloud access.
