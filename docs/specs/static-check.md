# Spec: The CERBERUS static-check gate

## The flow

RITA's loop is: **ask → code → static check → unit test (TDD) → iterate →
final test.** CERBERUS is the static gate, sitting between the coding agent's code
and the compiler/twister gates:

```
RESOLVE (find-or-write / scaffold)
   └─> STATIC (CERBERUS) ──findings──> the coding agent patches (bounded) ──┐
   └─> BUILD  ──compile errors──> the coding agent patches (bounded) ───────┤
   └─> SIM_TEST (twister) ──failures──> the coding agent patches (bounded) ─┤
   └─> DEVICE (blocked on bench)                                  │
        every patch RE-ENTERS AT STATIC ◄─────────────────────────┘
```

Patched code must re-pass the static gate before rebuilding — a patch that
fixes a test but introduces a static finding never slips through. the coding agent's
roles stay narrow: it codes (scaffold, tests, patches) and plays whatever
part it has *inside* CERBERUS; it never grades its own work — CERBERUS,
the compiler, and twister do.

## The real CERBERUS (pinned contract)

CERBERUS is **github.com/RichardSWheatley/cerberus** ("G.U.A.R.D.", Python
≥3.9): Head 1 *Sentinel* — 94 deterministic MISRA C:2012 / CERT C checks,
pure stdlib, **no API key**; Head 2 *Oracle* — LLM deep analysis (the coding agent's
seat inside CERBERUS, provider set by CERBERUS's own `CERBERUS_LLM_*` env); Head 3
*Executioner* — Unity test generation (`setup_unity.sh`).

- **Acquisition is part of RITA's install**: the repo is cloned to
  `~/.rita/cerberus` by the installer's CERBERUS component, the GUI's
  Install button (Modules page), or `rita cerberus install`. Needs git.
- **Invocation** (from the clone; it is not pip-installed):
  `python -m cerberus.cli scan <target>` — RITA's default gate,
  deterministic and keyless, matching the no-LLM-judges rule.
  `analyze --unity-dir <path>` is the opt-in deep mode
  (`RitaConfig.cerberus_deep`); its LLM credentials are CERBERUS's own env
  (`CERBERUS_LLM_*` / `its API-key environment variables`), passed through untouched.
- **Verdicts by exit code**: 0 = approve; 1 = request changes; 2 = block.
  Both non-zero verdicts gate (findings → the coding agent patches), with the
  verdict named in the artifact reason.
- Auto-detection order: explicit `cerberus_command` override → detected
  clone → skipped (visible, never silently green).

## Design

- `rita.firmware.static_check.StaticChecker` protocol:
  `check(target: Path) -> StaticResult(ok, findings)`. Findings are
  `FailureArtifact`s with `kind="static"` — the same concrete-artifact
  contract every other gate uses, so `coder.patch()` needs nothing new.
- `CerberusCli(command)` — the real adapter: runs the configured command
  with the target directory appended. Exit 0 = clean. Output contract:
  JSON `{"findings": [{"file", "line", "severity", "message"}]}` is
  parsed into artifacts; non-JSON output becomes a single finding with the
  raw text as the log (so any CLI shape works until the exact CERBERUS
  interface is wired).
- `FakeCerberus` — scripted results for tests.
- Config: `RitaConfig.cerberus_command` (string, e.g.
  `cerberus --json`). **Unconfigured → the STATIC stage reports
  `skipped: CERBERUS not configured` — visible, never silently green.**
- The `cerberus` module (`modules_impl/cerberus.py`) becomes a real
  wrapper: `start {command}` configures it, `check {target}` runs the
  gate over RPC; without a configured command it keeps its honest
  not-present answer.
- The GUI Settings page gets a CERBERUS command field.

## Acceptance criteria (each is a test)

- Clean static run → stage green, no the coding agent involvement.
- Findings → exactly one patch per finding round (artifact kind
  `static`, message included) → re-check → green.
- Persistent findings → `retries_exhausted` reported with the findings
  attached; BUILD never runs.
- A sim-test patch re-enters at STATIC (the checker runs again after the
  patch, before the rebuild).
- Unconfigured checker → stage `skipped` with the reason; pipeline
  continues to BUILD.
- `CerberusCli` against a real subprocess: JSON findings parsed with
  file/line; non-JSON output still yields a concrete artifact; exit 0
  passes.

## Scope: gates and patches apply to code RITA writes — never upstream

Discovered by self-test: running the static gate over an UNMODIFIED
in-tree sample means stock Zephyr code (which does not aim for MISRA)
can never build, and the patch loop would write into the user's zephyr
tree. Both violate the design.

- STATIC runs on RITA-authored code only: scaffolded applications and
  authored tests. `resolve → existing sample` without scaffold reports
  STATIC skipped: "unmodified in-tree sample — the static gate applies
  to code RITA writes".
- The patch loop NEVER targets upstream workspace code. A failing
  in-tree sample (build or twister) is reported as `failed` with the
  artifact and a detail naming it a workspace/environment issue — no
  patch attempts, no retries burned. Authored/scaffolded targets patch
  exactly as before.
- Defensive invariant: the pipeline refuses to hand the coder a patch
  target outside its own workdir or the applications root.
