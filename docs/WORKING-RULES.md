# Working rules for this repository

Read `BRIEF.md` first, then the RITA directive's specs under `docs/specs/`.

## Process — every change follows this, no exceptions

1. **Spec first.** Behavior changes get a spec in `docs/specs/<name>.md`
   (or an update to one) with explicit acceptance criteria.
2. **Failing tests before code.** Write the tests, run them, and **confirm
   they fail** (record the failure count in the commit message), then
   implement to green. The full suite must be green before a phase is done.
3. **Version + changelog on every change.** Bump the version in
   `pyproject.toml` and add a `CHANGELOG.md` entry.
4. **Log compromises.** Any shortcut, proxy, or deferred decision goes in
   `docs/DECISIONS-LOG.md` with the reason and what would remove it.

## Architecture rules

- The orchestrator owns control flow; gates own verification. The coding
  agent (the configured `coder_command` CLI) codes when asked — it never
  routes, never schedules tests, never grades its own work.
- Routing is deterministic matching over domain vocabulary; chat is the
  fallback. No LLM guesses intent.
- Twister's `twister.json` is the gate result. Parse it; never scrape stdout.
- Bounded retries at every stage; exhaustion is a **reported** outcome,
  never hidden, never looped past.
- Sim-first, always. The device tier is blocked on the bench milestone and
  is never faked green.
- Hardware ports come from `west twister --generate-hardware-map`, never
  hardcoded.
- The assistant's spoken name is config data (`~/.rita/config`), not code.
- Zero required dependencies: heavy backends are optional extras, lazily
  imported; every external process (west, twister, the coder CLI, MCP) sits
  behind a Protocol seam with a Fake and fixtures so the suite runs headless.

## Scope

Do not widen scope beyond the directive's fixes. When in doubt, harden what
exists instead of widening.

## Sections — depth over speed

The program is mapped into modular sections in
[`SECTIONS.md`](SECTIONS.md), each with its own quality bar and deep-pass
definition. Work opens **one section at a time** and closes it with its
bar met and evidence recorded — never a fastest-to-implement pass across
many. Live-product bug fixes interrupt this order; nothing else does.
