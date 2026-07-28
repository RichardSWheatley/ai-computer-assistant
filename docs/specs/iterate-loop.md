# Spec: The iterate loop belongs to the orchestrator (Fix 3)

## Problem

Claude must not own the loop. It does exactly **one step per invocation**:
given failure output, produce a patch (or, on request, scaffold an app /
write a test — Fix 2). The orchestrator decides what runs, where, and when
to stop. Gates decide success.

## Pipeline (`rita.firmware.pipeline.IteratePipeline`)

```
1. RESOLVE   — verification resolution (Fix 2); scaffold first if asked
2. STATIC    — CERBERUS static check; findings -> Claude patches (max N=3)
               (unconfigured -> reported as skipped, never silently green)
3. BUILD     — west build; compile errors -> Claude patches (max N)
4. SIM_TEST  — west twister -p native_sim until green (max N patch cycles)
5. DEVICE    — west twister --device-testing --hardware-map map.yaml
               BLOCKED until the bench milestone; never faked green
EVERY patch re-enters at STATIC. Budget exhausted at any stage -> STOP.
Report. Log in DECISIONS-LOG.  (See docs/specs/static-check.md.)
```

Rules (each enforced in code and covered by a test):

- **Sim-first, always.** No device attempt before sim is green. Iterations
  are seconds, not flash cycles.
- **Bounded retries at every stage** (`RitaConfig.max_patch_cycles`,
  default 3). Exhaustion is a **reported outcome**
  (`outcome="retries_exhausted"` with the surviving failures) — never
  hidden, never looped past.
- **Claude is never invoked without a concrete failure artifact.**
  `ClaudeWorker.patch(failure, workdir)` requires a non-empty
  `FailureArtifact`; the pipeline only constructs artifacts from parsed
  gate results.
- **`twister.json` is the gate result.** `parse_twister_json` is the only
  source of pass/fail truth; stdout is never scraped.
- **Board ports come from `west twister --generate-hardware-map`**, never
  hardcoded. The device stage without a map generates one first.
- Console-verified samples: `harness: console` regex lives in the suite
  yaml; stateful interaction goes through pytest-twister-harness (recorded
  in the index; the runner passes suites to twister unmodified).

## Seams

- `ZephyrRunner` protocol: `build`, `twister`, `generate_hardware_map`.
  `WestCli` is the real subprocess implementation (runs on the user's
  machine, cwd = workspace); `FakeWest` is scripted and copies fixture
  `twister.json` files.
- `ClaudeWorker` protocol: `complete` (fit/test authorship, Fix 2),
  `patch(failure, workdir)`, `scaffold(goal, board, dest)`.
  `ClaudeWorkerCli` shells out to `claude -p` with `--mcp-config` pointing
  at the workspace MCP server (Fix 2) and a bounded timeout. `FakeClaude`
  records every artifact it is handed.

## Report

`PipelineReport(goal, outcome, stages)` where each stage records
`(stage, outcome, detail, failures)`. Outcomes: `green`,
`retries_exhausted`, `blocked` (device tier), `failed` (infrastructure
error). The device stage appears in every report — as `blocked` until the
bench milestone flips `device_tier_enabled`.

## Acceptance criteria (each is a test)

- Green first try: no Claude involvement at all.
- Compile failure -> exactly one patch call (with the artifact) -> green.
- Persistent failure -> exactly `max_patch_cycles` patch calls, then
  `retries_exhausted` reported with the failure attached.
- Sim green precedes any device attempt; with the device tier disabled the
  device stage reports `blocked` and no device twister call happens.
- Device tier enabled without a hardware map: the map is generated first.
- The no-match path authors a test (Fix 2) and twister runs against it.
