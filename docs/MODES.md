# Operating Modes

Two modes trade privacy against power. **Cloud-default is the default**;
**local-only** is a hard privacy guarantee.

| | `cloud-default` (default) | `local-only` |
|---|---|---|
| Heavy reasoning | **Claude** (cloud) | larger **local** model |
| Routine / mechanical steps | local model | local model |
| Data leaving the machine | redacted, for heavy steps only | **never** |
| Enforcement | router prefers cloud for heavy steps | cloud provider **not constructed** |

## How routing works

Every planning step is classified **heavy** vs **light** (`HeuristicClassifier`):

- **Heavy** — deep reasoning: analyze, design, debug, refactor, plan, summarize,
  write/generate, long goals, or when the agent is stuck (recent steps failed).
- **Light** — mechanical: click, type, open, navigate.

Then:

- **cloud-default:** heavy → Claude (after redaction) · light → local model.
  This sends the *thinking* to the cloud while keeping fast UI steps local.
- **local-only:** heavy → larger local model · light → small local model.
  The cloud branch does not exist.

`router.last_route` records which path each step took (`cloud` /
`local-large` / `local-small`) for logging and the HUD.

## The privacy guarantee is structural

`local-only` is not just a flag that's checked at call time — the router
**refuses to even hold a cloud provider** in that mode:

```python
if mode is OperatingMode.LOCAL_ONLY and cloud is not None:
    raise ValueError("LOCAL_ONLY mode must not be given a cloud provider")
```

And `build_default_planner` never constructs/imports the Claude provider when
the mode is local-only. So there is no reachable code path to the network — the
guarantee holds by construction, not by discipline.

## Redaction (cloud-default)

Before any heavy step goes to the cloud, the router redacts the payload
(`_redact`): the **raw screenshot is dropped** and only the text summary +
element metadata go out. This is the single, testable choke point — extend it
to mask secrets/PII in element text as needed.

## How to select a mode

```bash
# Default — cloud for heavy lifting
aica run "refactor this module"

# Local-only for a single run (privacy)
aica run "summarize this contract" --local-only

# Force local-only everywhere
export AICA_LOCAL_ONLY=1
```

Or in a config file:

```toml
[aica]
mode = "local-only"   # or "cloud-default"
```

## Graceful degradation

In `cloud-default`, if no `ANTHROPIC_API_KEY` / `anthropic` package is present,
the cloud provider simply isn't built and heavy steps fall back to the best
available **local** model. The assistant always runs; it never hard-fails for
lack of cloud access.
