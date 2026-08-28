# Self-setup: RITA bootstraps herself and feeds the agent at runtime

The owner's verdict on the first-run experience: "why is there so much
crap I need to do ahead of time? Why wouldn't RITA ask the agent and
update the MD files and whatever else it needs at runtime?" Correct.
Every acquisition already exists behind a button; pressing the buttons
is RITA's job. Only three things genuinely need a human: picking the
workspace folder, typing the coding-agent command once, and completing
the agent's interactive login.

## 1. Auto-setup

- `supervisor.auto_setup()` runs the diagnostics and FIXES every fixable
  gap itself, as a managed task (pause/stop work; progress in the
  transcript/screen): register modules, install CERBERUS, install Unity,
  install the ARM toolchain (when the SDK's gcc version is known), and
  re-sync when mcp.json is stale. Each step reports start and result
  honestly; failures carry the tool's own detail and never stop the
  remaining steps.
- It ends with the setup report plus the human-only items that remain,
  named with where to do them.
- Routed phrases (deterministic grammar): "set yourself up",
  "finish setup", "get ready", "fix your setup".
- On GUI launch, when `auto_setup` (config, default ON) and fixable gaps
  exist, RITA announces what's missing and starts the task herself.
  The Settings page exposes the toggle.

## 2. Runtime agent context (the MD files)

- `firmware/agentmd.write_agent_context(dir, goal=..., board=..., ...)`
  writes `AGENTS.md` (the open agent-context convention — agent CLIs
  read it from their working directory) into every directory the agent
  works in: scaffolded app dirs and the authored-tests dir, refreshed on
  every pipeline run. Content is deterministic, from RITA's own data:
  the goal, the board's real facts (synced boards.json), the coding
  contract (every function restricts or validates its parameters), the
  relevant knowledge-pack notes, and the gate sequence the code must
  pass. Never written into upstream workspace directories.

## 3. Learned knowledge: ask once, remember as markdown

- A "how do I …" chat miss, with a coder configured, no longer dead-ends:
  RITA says she's asking the coding agent, runs the question as a managed
  task, saves the answer to `~/.rita/knowledge/learned/<slug>.md` (marked
  agent-authored, dated), and answers from that file forever after —
  `knowledge.summary_for`/`notes_for` include learned topics.

## Acceptance criteria

- auto_setup installs ONLY what's missing (present pieces untouched),
  reports each step, lists exactly the human-only leftovers, runs as a
  task, and is reachable by phrase and on launch (toggle honored).
- AGENTS.md lands in scaffold and authored dirs with board facts, the
  contract, and the goal; refreshed per run; absent from in-tree dirs.
- A knowledge miss asks the agent once, persists the markdown, and the
  next identical question answers with zero agent calls.
