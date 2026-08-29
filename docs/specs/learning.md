# Learning layer: RITA learns the system instead of assuming it

## Why

The owner's verdict, delivered over a live failure: RITA is too reliant
on knowledge compiled into the program. Layouts rot (SDK 1.0 moved its
toolchains; the hardcoded release table rotted the week before), and
every rot became a support conversation. RITA has a coding agent — an
investigator that runs ON the user's machine and can search online.
Sync is where that gets used; the setup itself is a learning process.
And RITA must not assume Zephyr-only work.

## Behavior

- **Workspace kinds** (`firmware/workspace.workspace_kind`): `zephyr`
  when the directory contains `zephyr/` (or is the zephyr tree), else
  `generic`. The firmware machinery — CERBERUS, Unity, ARM toolchain,
  board sync, the iterate pipeline — applies only to Zephyr
  workspaces; modules, toolsets, learning, and chats apply everywhere.
- **Investigation** (`learning/investigate.investigate`): asks the
  agent a question with a strict-JSON schema; the prompt states it may
  read this machine and search online, and must change nothing. The
  answer is DATA: the caller's deterministic `validate` must confirm
  it (e.g. RITA runs the claimed compiler herself) or the claim is
  discarded with an honest note. Trust but verify — gates own truth.
- **Sync is a learning pass** (`presenter.sync` →
  `supervisor.discover_system`): after the deterministic sync, every
  gap RITA's own detection can't close becomes an investigation —
  the SDK's compiler when its layout defeats the search, qemu, and
  (for generic workspaces) how the repo is built and tested. Validated
  claims persist; failures are reported by name.
- **Machine facts** (`learning/facts`, `~/.rita/knowledge/machine/`):
  one markdown file per fact — title, `verified: agent+RITA <date>`,
  the evidence line, and a JSON body. Facts re-validate on every read
  (a fact whose path is gone returns None — the cue to re-investigate).
  The deterministic detectors USE the facts (`_sdk_arm_gcc`,
  `detect_qemu` fall back to them), and AGENTS.md carries them to the
  agent. "what did you learn" reports facts, learned answers, toolsets.
- **Toolsets** (`learning/toolsets`, `~/.rita/toolsets/<name>/`):
  "make a toolset that …" has the agent design a small tool as strict
  JSON; RITA writes the files herself (structural path invariant —
  nothing lands outside the toolset's directory), smoke-runs the
  command, registers only on exit 0 (failures are reported and the
  directory removed), and keeps a `toolset.md` manifest with
  provenance. "list your toolsets" / "use the <name> toolset [on …]"
  rerun them from disk — reuse is automation.
- **Per-chat areas** (`learning/chats`, `~/.rita/chats/<id>/`): each
  chat can bind its own repo/area — "use <path or git url> for this
  chat" (URLs are cloned into the chat's area by RITA); "start a new
  chat" / the New chat button opens the next unbound chat. Unbound
  chats use the global workspace, so the single-workspace flow keeps
  working. Work, boards facts, and the index follow the chat's
  binding; machine facts stay global (they describe the machine).

## Acceptance criteria

- A generic (non-Zephyr) workspace queues no firmware setup steps and
  gets an honest redirect from firmware work — never a broken pipeline.
- An unverifiable agent claim is never stored or used; the report says
  what was claimed and that RITA couldn't verify it.
- After discovery stores a fact, the deterministic detector resolves
  through it and a second discovery run asks the agent NOTHING.
- A toolset failing its smoke run is not registered and leaves nothing
  behind; escaping file paths are refused outright.
- Chat bindings persist across launches, re-validate their paths, and
  never break the unbound default flow.
