# Spec: The CERBERUS static-check gate

## The flow

RITA's loop is: **ask → code → static check → unit test (TDD) → iterate →
final test.** CERBERUS is the static gate, sitting between Claude's code
and the compiler/twister gates:

```
RESOLVE (find-or-write / scaffold)
   └─> STATIC (CERBERUS) ──findings──> Claude patches (bounded) ──┐
   └─> BUILD  ──compile errors──> Claude patches (bounded) ───────┤
   └─> SIM_TEST (twister) ──failures──> Claude patches (bounded) ─┤
   └─> DEVICE (blocked on bench)                                  │
        every patch RE-ENTERS AT STATIC ◄─────────────────────────┘
```

Patched code must re-pass the static gate before rebuilding — a patch that
fixes a test but introduces a static finding never slips through. Claude's
roles stay narrow: it codes (scaffold, tests, patches) and plays whatever
part it has *inside* CERBERUS; it never grades its own work — CERBERUS,
the compiler, and twister do.

## Design

- `rita.firmware.static_check.StaticChecker` protocol:
  `check(target: Path) -> StaticResult(ok, findings)`. Findings are
  `FailureArtifact`s with `kind="static"` — the same concrete-artifact
  contract every other gate uses, so `claude.patch()` needs nothing new.
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

- Clean static run → stage green, no Claude involvement.
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
