# RITA in sections — the map, the bar, and the order of care

The owner's directive, verbatim intent: *no fastest-to-implement
mentality; break the program into modular sections; focus on one at a
time; master-level Python, GUI/UX and graphic design, professional
testing philosophy; take the time and get it right.*

This document is the working map. Each section names its code, its
job, its quality bar, and what "a deep pass" means for it. Work
proceeds **one section at a time**: a section is opened, brought to
its bar, closed with evidence — before the next is touched. Bug fixes
on the live product interrupt this order; nothing else does.

## The sections

### 1. Routing & language (`src/rita/routing/`, `src/rita/voice/loop.py`)
The deterministic front door: grammar tables, the wake gate, the
router, dispatch. **Bar:** every phrase RITA claims to understand is
in a table, covered by a test, and ambiguity resolves the same way
every time; raw text reaches handlers that carry payloads (paths,
URLs), normalized text is routing currency only.
**Deep pass:** exhaustive phrase-table review against the docs;
property-style tests (no utterance may route two ways); a written
grammar reference generated from the tables themselves.

### 2. Voice (`src/rita/voice/`, presenter's listen loop)
Capture, transcription, gating, speech. **Bar:** the mic button is the
single source of truth; nothing is transcribed that the user didn't
opt into; every backend failure surfaces by name; latency budgeted
and measured.
**Deep pass:** VAD-quality silence handling, device hot-unplug
behavior, an audio-path integration test with recorded fixtures.

### 3. GUI & design (`src/rita/gui/`)
The shell people actually touch. **Bar:** every interactive element
has visible rest/hover/pressed/disabled/checked states; every action
gives immediate feedback; every long operation shows progress and an
append-only log; keyboard flow works; the theme derives entirely from
tokens; screenshots in the README are renders of the real app.
**Deep pass:** a design-token audit (spacing scale, type scale, color
roles), consistent iconography, empty-states and first-run screens,
resize/DPI behavior, and a screenshot-diff harness so visual
regressions are caught by CI, not by the owner.

### 4. Gates & pipeline (`src/rita/firmware/`: pipeline, static_check,
unity, west, testwriter, resolution, index)
The deterministic verification machine. **Bar:** no stage may pass
without primary evidence (parsed twister.json, compiler exit, Unity
counts); budgets bounded; every failure artifact carries the log
excerpt that proves it; authored-vs-in-tree gating exact.
**Deep pass:** failure-artifact quality review, mutation-style tests
(break a gate, prove the pipeline notices), timing/size budgets.

### 5. Acquisition & environment (`toolchain.py`, `cerberus_setup.py`,
`unity.py`, `install_guard.py`, `workspace.py`, diagnostics)
Everything RITA installs or detects on the machine. **Bar:** search,
never assume; check before downloading; single-flight; staged swaps
that never destroy a working install; every failure carries the probe
evidence; TLS verified always.
**Deep pass:** a fault-injection suite (held dirs, read-only trees,
dead networks, truncated archives) run in CI.

### 6. Learning & agent seams (`src/rita/learning/`, `coder.py`,
`jsonio.py`, knowledge, agentmd, projects/planner)
Where the LLM plugs in — and where its output is contained. **Bar:**
every agent answer is validated deterministically before use or
storage; every stored fact carries provenance and re-validates; JSON
contract enforced with one retry and quoted evidence; prompts live in
code as named constants with their contracts stated.
**Deep pass:** a prompt-contract review (each prompt states its
schema and refusal path), fact-staleness lifecycle tests, toolset
sandboxing review.

### 7. Sessions & state (`learning/chats.py`, `core/tasks.py`,
supervisor, home layout, config)
Chats, tasks, persistence. **Bar:** every file RITA writes is
greppable, hand-fixable, and versioned in shape; concurrent access is
either locked or documented as human-speed-safe; nothing global that
should be per-chat.
**Deep pass:** a state-file schema doc, crash-recovery tests (kill
mid-task, relaunch, state coherent), the active-chat pointer made
per-call instead of ambient.

### 8. Packaging & release (`packaging/`, installer.iss, CI workflow)
What actually lands on the owner's machine. **Bar:** the artifact is
tested, not the source (frozen smoke gate); installers are idempotent
and skip what's present; every release carries its CHANGELOG entry
and a green CI run; screenshots regenerate with the build.
**Deep pass:** code signing (owner's purchase + CI wiring), installer
upgrade/downgrade matrix, artifact size budget.

## Testing philosophy (applies to every section)

1. **Tests are written first and fail first** — the count goes in the
   commit message. A test that never failed proves nothing.
2. **Test the artifact, not the source** — the frozen bundle gate
   stays mandatory before every release.
3. **Fakes at the seams, reality at the edges** — unit tests use the
   seam fakes; each section keeps at least one test against the real
   thing (a real archive, a real QEMU run, a real window render).
4. **A bug fixed is a test added** — every live failure from the
   owner's machine becomes a named regression test (the WinError 5
   family, the SDK-layout family, the JSON-prose family already are).
5. **Silence is failure** — anything that can fail must fail visibly,
   with the evidence in the message. "It didn't say anything" is a
   bug by definition.
6. **Isolation is enforced, not promised** — the autouse RITA_HOME
   fixture stays; no test may touch the real home or network unless
   it is explicitly an integration test and marked so.

## The order of care

Sections are opened in this order (chosen by product pain, the
owner reorders at will):

1. **GUI & design** — the owner sees it every day and has said so.
2. **Voice** — the most personal interface; trust is won or lost here.
3. **Acquisition & environment** — the source of most live failures.
4. **Learning & agent seams** — the growth direction.
5. **Gates & pipeline** — solid today; deepen evidence quality.
6. **Sessions & state** — de-globalize the remaining ambient state.
7. **Routing & language** — table review + generated reference.
8. **Packaging & release** — signing, upgrade matrix.

One section open at a time. Each closes with: its bar met, its deep
pass done, evidence in the CHANGELOG, and a section review note in
the DECISIONS-LOG.
