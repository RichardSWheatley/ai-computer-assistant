# RITA — Routing, Iteration, Testing, Automation

A **deterministic orchestrator** with a speech front end that drives
firmware development on a **Zephyr workspace**. Formerly AICA; see
[`BRIEF.md`](BRIEF.md) for the reframe and [`CLAUDE.md`](CLAUDE.md) for the
working rules every change follows.

RITA is **not an LLM agent**. Claude (`claude -p`) is one capability among
several — it writes applications, tests, and patches when asked. It does not
route, does not decide when tests run, and does not judge its own success:

- **Routing is grammar, not guessing.** A pure, table-driven router over
  RITA's own vocabulary (work verbs, board names from `boards.json`,
  samples, peripherals). Anything naming a board, sample, or artifact is
  work; chat is the fallback. Wake with "hello Rita" (the name is config,
  renameable by voice).
- **Gates own verification.** The compiler and `west twister` decide
  success — `twister.json` is parsed, stdout is never scraped. Sim-first,
  always; bounded patch budgets; exhaustion is a reported outcome. The
  device tier stays **blocked on the bench milestone** and is never faked
  green.
- **Verification is find-or-write.** A static index over
  `samples/**/sample.yaml` + `tests/**/testcase.yaml` finds the suite that
  proves an intent; Claude judges fit in one bounded call; no match means
  Claude writes a proper ztest that twister gates like everything else.
- **The workspace is served over MCP.** `rita mcp-serve` exposes the index,
  board vocabulary, and bounded search/read tools so the claude-worker sees
  the checkout through structured tools.
- **PAUSE / RESUME / STOP** at safe checkpoints (hardware operations are
  atomic), with pausable sentence-chunked speech.
- **Two output channels.** Speech is ≤2 conversational sentences; code,
  diffs, logs, and paths go to the screen — enforced deterministically in
  the shell.
- **Thin supervisor + versioned modules.** Capabilities run as separately
  versioned child processes under `~/.rita/modules/` (JSON-RPC over stdio,
  handshake, crash isolation, drain-on-update).

## Quick start

```bash
pip install -e ".[dev]"
rita sync --workspace /path/to/zephyrproject   # index boards + samples/tests
rita talk                                      # "hello Rita, build blinky"
rita modules install --dev                     # register capability modules
rita mcp-serve --workspace ...                 # workspace MCP (needs .[mcp])
```

The suite runs headless with zero required dependencies — every external
process (`west`, twister, `claude -p`, MCP) sits behind a seam with fakes
and fixtures. Real builds need a Zephyr workspace + toolchain on your
machine.

## The pipeline

```
utterance ── WakeGate ── route() ──► work ──► RESOLVE ─► BUILD ─► SIM_TEST ─► DEVICE
                            │                (find-or-   (patch    (twister    (blocked on
                            └► chat/control   write)      ≤3)       ≤3)         bench)
```

## Documentation

- **[BRIEF.md](BRIEF.md)** — what RITA is and the order of work.
- **[Specs](docs/specs/)** — one spec per fix, with acceptance criteria.
- **[Decisions log](docs/DECISIONS-LOG.md)** — every compromise, on the record.
- **[CHANGELOG.md](CHANGELOG.md)** — versioned history.
- Legacy design docs (desktop-assistant heritage, still reachable via
  `rita run`): [architecture](docs/ARCHITECTURE.md),
  [security](docs/SECURITY.md), [modes](docs/MODES.md),
  [modularity](docs/MODULARITY.md), [worker protocol](docs/WORKER-PROTOCOL.md),
  [business capabilities](docs/BUSINESS-CAPABILITIES.md),
  [tech stack](docs/TECH-STACK.md), [roadmap](docs/ROADMAP.md).

## CLI

| Command | What it does |
|---|---|
| `rita talk` | Voice shell: wake word, grammar routing, managed tasks |
| `rita sync --workspace P` | Build `~/.rita/boards.json` + the verification index |
| `rita mcp-serve` | Serve the workspace MCP server over stdio |
| `rita modules [install --dev]` | List / install capability modules |
| `rita run "<goal>"` | Legacy desktop agent loop (screen + input control) |
| `rita doctor` / `plugins` / `doc` / `workflow` | Diagnostics, tools, docs, workflows |

Data and config live in `~/.rita/` (a legacy `~/.aica/` is migrated
automatically). The assistant's spoken name defaults to "Rita" and is
changeable by voice — it's config, not code.
