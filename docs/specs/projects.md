# Spec: Projects — task handoff, AI planning, RITA execution

## The idea

RITA is an AI **assistant**: you hand her tasks. She either figures them
out herself, or queries an AI to create the list of items and a project
schedule — **and then RITA goes and completes the tasks, not the AI.**

The division of labor is the same one the whole system is built on, one
level up: an LLM may *author the plan*, but the plan is **data**, validated
deterministically, and only RITA's orchestrator executes it — every item
through her own gates (CERBERUS → unit tests → final test).

## Flow

```
HANDOFF   "start a project: <goal>"  (voice, prompt bar, or Projects page)
   │
DECIDE    goal routes directly through the grammar?  ── yes ─► single item,
   │ no                                                 no AI involved
PLAN      ONE bounded the coder command call. Strict JSON contract:
          items = [{title, command, depends_on, estimate, milestone}]
          Every `command` MUST be phrased in RITA's own grammar.
   │
VALIDATE  deterministic: each command is routed with the real router.
          work-routable -> executable; knowledge/chat -> answerable;
          unroutable -> flagged needs_user (kept, never guessed at).
   │
EXECUTE   RITA works the items herself, dependency-ordered, each through
          the full pipeline. Progress persists (~/.rita/projects.json);
          PAUSE/STOP work mid-project; every item outcome is announced.
   │
REPORT    done / blocked / needs-you summary. Blocked is reported,
          never looped past — same rule as every gate.
```

## Design

- `rita.projects.model` — `ProjectItem(id, title, command, depends_on,
  status, note)`, statuses `pending|running|done|blocked|needs_user|
  answered|stopped`; `Project(id, goal, items, created_at)`;
  `ProjectStore` at `~/.rita/projects.json` (load/save on every
  transition — restart-safe).
- `rita.projects.planner` — `plan_project(goal, complete, vocab)`:
  one bounded call, JSON parsed, **validated by routing every command**;
  size-capped; unparseable output rejected loudly. `quick_plan(goal,
  vocab)` first: a goal that routes as work becomes a one-item project
  with no AI call at all ("figures it out herself").
- `rita.projects.runner` — `run_project(project, store, make_pipeline,
  chat, ctl)`: dependency-ordered walk; work items run an IteratePipeline
  (own workdir per item); chat/knowledge items get their deterministic
  answer recorded; an item whose dependency is blocked is blocked too
  (cascade, reported); `ctl.checkpoint` between items so PAUSE/STOP apply
  at item boundaries on top of the in-item stage checkpoints. Returns
  `ProjectResult(outcome: completed|partial|blocked, counts)`.
- **Supervisor**: `hand_off(goal)` → plan → store → announce the item
  list → submit the whole project as ONE TaskManager task (so the
  existing pause/resume/stop and the GUI task watcher just work).
  Router gains `kind="project"`: "start/create/plan a project …" and
  "take on …" phrases. Chat answers "how is the project going" from the
  store (deterministic).
- **GUI**: a Projects page — handoff box, live item list with statuses,
  and the same persistent Pause/Stop bar.
- Honesty rules: no coding-agent CLI and a plan is needed → say so; items that
  need capabilities RITA doesn't have yet → `needs_user`, listed in the
  report, never silently dropped.

## Acceptance criteria (each is a test)

- A work-routable goal becomes a one-item project with zero AI calls.
- The planner's items are each routed; a plan containing an unroutable
  item keeps it as `needs_user`; garbage output is rejected.
- A 3-item project executes in order through real (fake-gated) pipelines,
  the store updating at every transition.
- A blocked item (retries exhausted) blocks its dependents; independent
  items still complete; the result is `partial` with the blockage named.
- Chat items get answered and recorded, not executed.
- PAUSE mid-project suspends at a safe boundary and RESUME continues
  without redoing completed items; STOP reports what finished.
- The store survives restart: a reloaded project shows the same statuses.
- "start a project: …" routes as `kind="project"` and hand_off announces
  the plan; project status is queryable in chat.
