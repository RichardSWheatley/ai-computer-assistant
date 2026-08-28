# The coding-agent seam: vendor-neutral, command-as-config

RITA drives an external coding-agent CLI for exactly four jobs — scaffold,
write tests, judge fit, patch failures. It never routes, never schedules
tests, never grades its own work. Which CLI that is must be **config
data**, like the assistant's spoken name — the codebase names no vendor.

## Behavior

- `RitaConfig.coder_command: str | None` — the command line RITA prepends
  to every agent invocation (e.g. a CLI that accepts
  `<cmd> <prompt> --output-format text [--mcp-config <file>]
  [--permission-mode acceptEdits]`). Split with the cross-platform
  `split_command` (Windows paths survive).
- Unset (the default) means **RITA cannot code**: work and project
  handoffs are answered with an honest "no coding agent is configured —
  set the command in Settings" message, never a crash, never a silent
  skip. Chat, sync, boards, knowledge, and status all still work.
- `firmware/coder.py` owns the seam: `CoderWorker` Protocol,
  `CoderCli` (subprocess, bounded timeout, requires an explicit command),
  `FakeCoder` for tests. The patch invariant is unchanged: a patch call
  REQUIRES a concrete `FailureArtifact`.
- The `coder-worker` module hosts the same seam behind RPC; it reads the
  command from the user's config at startup.
- The status bar reports the seam honestly: configured + resolvable →
  "coder ✓"; otherwise "coder not configured".
- The legacy cloud-planner path loses its built-in vendor client: a cloud
  planner is injected or absent (local/mock only). No SDK import remains.

## Acceptance criteria

- Supervisor with no `coder_command` and no injected worker answers work
  and handoff dispatches with the configuration message (no task starts).
- `coder_command = "python C:\\tools\\agent.py"`-style strings split into
  argv correctly on both platforms and reach `CoderCli.command`.
- Status reflects configuration: unset → not available; set to a
  resolvable command → available.
- Injected workers (tests, module processes) bypass the config exactly as
  before.
- `grep -ri` for the previous vendor names over the tracked tree is empty.
