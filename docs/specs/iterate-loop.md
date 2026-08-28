# Spec: The iterate loop belongs to the orchestrator (Fix 3)

## Problem

the coding agent must not own the loop. It does exactly **one step per invocation**:
given failure output, produce a patch (or, on request, scaffold an app /
write a test — Fix 2). The orchestrator decides what runs, where, and when
to stop. Gates decide success.

## Pipeline (`rita.firmware.pipeline.IteratePipeline`)

The flow, in the owner's words: **"Ask, code, static check, unit test with
TDD principles, …, iterate if needed, final test"** — where TDD means
*test every single function you write before you move on*, for its input
and output parameters, and every function restricts or validates those
parameters before executing.

```
1. RESOLVE    — the ask: router intake; pick the Zephyr suites that will
                be the final test (find-or-write, Fix 2); scaffold if asked
   (CODE)     — the coding agent codes to the goal under the parameter-contract rule
2. STATIC     — CERBERUS on the code; findings -> the coding agent patches (max N=3)
                (unconfigured -> reported as skipped, never silently green)
3. UNIT_TEST  — EVERY function gets host-run Unity tests of its
                input/output parameters (valid/boundary/invalid). A
                deterministic scan names any function without tests ->
                the coding agent adds them; then all tests must pass. (Not ztest.)
4. FINAL_TEST — the Zephyr samples/tests via twister on native_sim
5. DEVICE     — BLOCKED until the bench milestone; never faked green
EVERY patch re-enters at STATIC. Budget exhausted at any stage -> STOP.
Report. Log in DECISIONS-LOG. (See docs/specs/static-check.md.)
```

Rules (each enforced in code and covered by a test):

- **Sim-first, always.** No device attempt before sim is green. Iterations
  are seconds, not flash cycles.
- **Bounded retries at every stage** (`RitaConfig.max_patch_cycles`,
  default 3). Exhaustion is a **reported outcome**
  (`outcome="retries_exhausted"` with the surviving failures) — never
  hidden, never looped past.
- **the coding agent is never invoked without a concrete failure artifact.**
  `CoderWorker.patch(failure, workdir)` requires a non-empty
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
- `CoderWorker` protocol: `complete` (fit/test authorship, Fix 2),
  `patch(failure, workdir)`, `scaffold(goal, board, dest)`.
  `CoderCli` shells out to the coder command with `--mcp-config` pointing
  at the workspace MCP server (Fix 2) and a bounded timeout. `FakeCoder`
  records every artifact it is handed.

## Report

`PipelineReport(goal, outcome, stages)` where each stage records
`(stage, outcome, detail, failures)`. Outcomes: `green`,
`retries_exhausted`, `blocked` (device tier), `failed` (infrastructure
error). The device stage appears in every report — as `blocked` until the
bench milestone flips `device_tier_enabled`.

## Acceptance criteria (each is a test)

- Green first try: no the coding agent involvement at all.
- Compile failure -> exactly one patch call (with the artifact) -> green.
- Persistent failure -> exactly `max_patch_cycles` patch calls, then
  `retries_exhausted` reported with the failure attached.
- Sim green precedes any device attempt; with the device tier disabled the
  device stage reports `blocked` and no device twister call happens.
- Device tier enabled without a hardware map: the map is generated first.
- The no-match path authors a test (Fix 2) and twister runs against it.
