# BRIEF — What this project is becoming

This repository started as **AICA** (AI Computer Assistant). Per the RITA
directive it is being redirected into **RITA** — **R**outing, **I**teration,
**T**esting, **A**utomation.

## The reframe (get this right before touching code)

RITA is **not an LLM agent**. It is a **deterministic orchestrator** with a
speech front end that drives firmware development on a **Zephyr workspace**
(pre-installed on the user's machine; its path is config, not code).

- **the coding agent (the coder command) is the coding agent** — one capability among several.
  It authors applications when asked (scaffold), writes tests when none exist,
  judges verification fit, and produces patches from failure output. It does
  **not** route, does not decide when tests run, and does not judge its own
  success.
- **The orchestrator owns all control flow.** Routing is deterministic grammar
  matching (chat is the fallback). The iterate loop's steps, budgets, and stop
  conditions belong to the orchestrator.
- **Gates own all verification.** The compiler, twister (its `twister.json`,
  never scraped stdout), and — when the bench milestone lands — device runs
  and power numbers. We never trust the coding agent's output; we trust the gates.

## The flow

**Ask, code, static check, unit test with TDD principles, …, iterate if
needed, final test.** the coding agent codes to the goal; CERBERUS statically checks
it; every single function is unit-tested (host Unity) for its input and
output parameters — every function restricts or validates them before
executing; iteration re-passes every gate; the final test is the Zephyr
samples/tests tier.

## The fixes, in mandated order of work

1. **Fix 1** — Grammar-first router + wake grammar; chat as fallback.
2. **Fix 2** — Verification resolution (index → fit-judge → write-the-test),
   served to the coder-worker over an MCP server on the workspace.
3. **Fix 3** — The iterate loop belongs to the orchestrator (sim-first,
   bounded retries, exhaustion is a reported outcome).
4. **Fix 4** — PAUSE and RESUME/STOP controls.
5. **Fix 5** — Two output channels (speech ≤2 sentences; code/diffs/logs to
   screen only), enforced deterministically in the shell.
6. **Fix 6** — Thin supervisor + versioned module processes.
7. **Rename** — the project, package, CLI, and data dir (`~/.rita/`) become
   RITA. The assistant's spoken name is config data, not code.

The device tier (real boards, `west flash`, power measurement) is **blocked on
the bench milestone** (`docs/BENCH-PLAN.md`, first milestone: twister
`hello_world` with `--device-testing` on the real EVB). It is never faked
green.

## Standing rule

Do not widen scope beyond the fixes. When in doubt, harden what exists instead
of widening. See `docs/WORKING-RULES.md` for the working process every change follows.
