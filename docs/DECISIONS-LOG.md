# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `docs/WORKING-RULES.md`.)

## 2026-08-28 — One toolchain (unit tier = Zephyr's gcc)

- **The host-compiler unit tier is gone** (it lasted one day): compiling
  unit tests with a PC compiler meant a second toolchain with different
  int widths, alignment, and libc than the firmware's. The owner's rule
  stands: whatever compiler Zephyr uses, RITA uses — version-matched to
  the SDK's gcc, mismatches surfaced.
- **QEMU is unavoidable**: ARM binaries cannot execute on the PC. The
  proven recipe (arm926ej-s + rdimon semihosting on versatilepb) runs
  Unity directly with no Zephyr/west/CMake involvement; the emulator
  comes from PATH or the Zephyr SDK's host tools. Cost: unit runs are
  seconds, not milliseconds.
- **The toolchain download is ~150 MB once**, keyed to the SDK's gcc
  version from a release table (`RELEASES`); unknown versions fall back
  to a documented default and the diagnostic says so.
- `host_cc` stays as a native escape hatch (runs binaries directly) —
  used by RITA's own test suite for speed and available to developers,
  never chosen automatically.

## 2026-08-28 — Verify the artifact, not the source

- **Bundle-only breakage was invisible to the whole test suite.** Four
  user-facing failures in a row (entry-point crash, unusable mcp.json,
  missing voice runtime, dead MCP server) existed only in the packaged
  app, because source tests import from the source tree and CI only
  checked that the build command exited 0. `packaging/smoke_bundle.py`
  now drives the built executables end to end, locally and in CI, and
  fails the build. New rule: a packaging change is not done until the
  bundle smoke test has run against a real build.
- **The MCP SDK is a moving dependency.** 2.x renamed the server class;
  we support both names rather than pinning, and `mcp_available()`
  probes constructability so a future rename degrades to an honest
  "workspace tools unavailable" instead of killing the coding agent.

## 2026-08-28 — Voice runtime bundled (supersedes "not bundled")

- **Voice deps ship in the installer now.** The Phase C decision to
  install them on first use assumed a pip-capable runtime; a frozen
  bundle has none, so the checkbox could never work on a real install.
  Cost: a larger installer (faster-whisper/CTranslate2; torch is NOT
  needed and stays excluded). The Whisper model download remains
  first-use.

## 2026-08-28 — Voice in the GUI

- **Fixed 5-second listen chunks, no VAD.** Wake latency is bounded by
  the chunk length and a wake word straddling a chunk boundary can be
  missed once — the long-logged fixed-window compromise, now user-facing.
  A VAD-segmented recorder remains the hardening path.
- **Whisper downloads its model on first spoken turn** (one-time,
  network) — kept out of the installer for size, same as the other voice
  runtime deps.
- **A TTS engine that fails to construct degrades to listening-only**
  (replies stay on screen) rather than blocking voice input.

## 2026-08-28 — Vendor-neutral coder seam

- **No coding agent ships configured.** Out of the box RITA cannot code
  until the user enters a command in Settings — the honest cost of
  keeping vendor names out of the codebase entirely (the owner's call).
  The status bar and work replies say exactly what to do.
- **The coder CLI calling convention is fixed, not negotiated**
  (`<cmd> <prompt> --output-format text [--mcp-config …]
  [--permission-mode acceptEdits]`). Agents with a different surface
  need a shim script; a per-flag mapping table would be config bloat
  ahead of a demonstrated second agent.
- **The legacy cloud planner/backend is injection-only now** — the
  built-in vendor client and its SDK extra are deleted, not renamed:
  an API client cannot be de-vendored honestly.

## 2026-08-28 — Windows CI

- **The SDK end-to-end unit-compile test is skipped on Windows.** Its
  fake SDK gcc is a `/bin/sh` wrapper, which Windows cannot execute; a
  real Windows fake would need an actual PE binary. Discovery of the
  SDK's `.exe` toolchain names is still tested everywhere. Removed if we
  ever ship a tiny prebuilt echo-compiler fixture for Windows.
- **Windows verification is CI-only.** The dev container is Linux, so
  Windows behavior is proven by running the installer workflow's test
  job on a windows runner, not locally.

## 2026-08-28 — Projects (handoff + planning + execution)

- **`quick_plan` requires a verb-grounded route** (`verb` /
  `verb+entity`), not `entity_only`: "bring up blinky and document the
  board" merely *mentions* a known sample and must go to the planner,
  while "build blinky for the apollo510" runs directly. The proxy: a
  verb-grounded compound goal ("build blinky and document the board")
  still quick-plans as one item. Removed by conjunction splitting in the
  grammar if it ever bites in practice.
- **One bounded planning call, no repair loop.** A garbage or oversized
  plan is a loud `PlanError` back to the user ("rephrase or break it
  up"), not a re-prompt cycle — consistent with bounded-retries, but a
  single retry with the parse error quoted would be a reasonable
  hardening later.
- **The Projects page polls the store on a 1 s QTimer** instead of a
  presenter push channel. The store is a small JSON file and the page is
  a view over persisted truth (what a restart would show), so polling is
  honest and simple; a push signal would remove the (invisible) 1 s lag.
- **Item estimates/milestones are carried, not enforced.** They're
  display data from the plan; RITA doesn't schedule against wall-clock
  time. A real scheduler would need its own spec.

## 2026-07-28 — Per-function unit tier

- **The owner's TDD definition is adopted verbatim**: code to the goal,
  then test every single function (input/output parameters) before moving
  on — not test-first ceremony. Unit tests are host Unity, never ztest;
  the Zephyr suites are the final test.
- **Function discovery is a regex over conventional C** (brace-level
  definitions; main and test files excluded). Exotic C (K&R, heavy
  macro-generated definitions) could evade it — CERBERUS and compilation
  still see everything, and the scan can only under-count, never
  fake-cover.
- **The unit-tier compiler comes from PATH or the Zephyr SDK** (the SDK
  ships gcc by default; LLVM optional) — no MinGW requirement. Caveat
  kept honest: SDK toolchains are cross compilers, so SDK-built test
  binaries link `-static` and a binary the host can't execute produces a
  concrete failure naming the fix (native gcc/clang) rather than an
  assumption in either direction. A native PATH compiler is preferred
  when present because its output always runs.
- The knowledge-pack citation test now accepts any http source (SEI CERT
  and ThrowTheSwitch joined docs.zephyrproject.org as cited sources).

## 2026-07-28 — Real CERBERUS wiring

- **Default gate = `scan` (Head 1), not `analyze`.** Head 1 is
  deterministic and keyless — the RITA-philosophy fit; the Oracle LLM +
  Unity heads are opt-in (`cerberus_deep`) because they add cost, latency,
  and an LLM judgment layer the user should choose deliberately.
- **Exit codes are the authoritative contract** (0/1/2 per the CERBERUS
  README); JSON summary filenames are undocumented upstream, so stdout
  JSON is parsed opportunistically and raw text still yields a concrete
  artifact. Tighten when upstream documents the summary file.
- **Acquisition is `git clone --depth 1` into ~/.rita/cerberus**, updated
  by ff-only pull. Missing git is an honest failure surfaced in the
  installer log and retryable from the GUI.

## 2026-07-28 — CERBERUS gate

- **The adapter's exact CERBERUS interface is provisional.** The tool is
  the owner's and lives online; until its invocation/output contract is
  provided, `CerberusCli` runs a configured command with the target dir
  appended and accepts JSON findings or raw text (exit code is the
  verdict). Wiring the precise contract is a config/adapter tweak, not a
  pipeline change. One patch per finding-round uses the first finding —
  matching the one-step-per-invocation rule; batching findings into one
  artifact is a tuning option.
- **STATIC re-entry applies to every patch** (including compile/test
  patches), which can consume static budget on code the coding agent just changed —
  intentional: the gate's judgment outranks iteration speed.

## 2026-07-28 — Installer (Phase C)

- **The installer is authored + CI-built here, smoke-run on the target
  machine.** This container is Linux; the windows-latest workflow produces
  the artifact, and GETTING-STARTED carries the real-machine checklist.
- **Voice runtime deps are not bundled** (faster-whisper/torch would
  multiply installer size); the Voice component registers the modules and
  the runtime installs on first use. Revisit if offline installs matter.
- **No custom icon yet** — shortcuts use the exe default. A designed .ico
  is cosmetic backlog, not scope-widening.

## 2026-07-28 — Zephyr knowledge pack (Phase B)

- **The pack is a snapshot** (researched 2026-07-28 against the "latest"
  docs); each topic cites its source URL so staleness is auditable.
  Refreshing it is a re-research task, not a code change. It carries
  conventions only — install facts stay workspace-derived.
- **"build me an example/app" upgrades to scaffold** via a deterministic
  rule (build verb + artifact token + no named existing sample). Logged
  because "build" is genuinely ambiguous in English; the rule is table
  logic, not semantic judgment, per Fix 1.
- **hex-mode PSRAM specifics**: in-tree memc coverage centers on quad
  APS6404L; hex-mode parts follow the same memc-over-MSPI shape (Ambiq
  bindings support hex IO). The psram topic says exactly that rather than
  overclaiming an in-tree hex driver.

## 2026-07-28 — GUI shell (Phase A)

- **PySide6 (Qt 6) over web-view frameworks** — the requirement is a
  native-looking app, not a browser; Qt renders native widgets, styles
  cleanly via QSS, and packages with PyInstaller for the installer phase.
  `PySide6-Essentials` keeps the dependency slim.
- **Presenter-first architecture**: every GUI behavior is a plain-Python
  `GuiPresenter` tested headless; the Qt layer only binds signals. The Qt
  window itself is verified with `QT_QPA_PLATFORM=offscreen` in CI —
  pixel-level polish still needs a sighted pass on the target machine.
- **Voice in the GUI is config-gated but not yet threaded into the Qt
  loop** (the presenter speaks via PausableSpeaker when a TTS is wired);
  full in-window mic capture lands with the packaged voice component.

## 2026-07-28 — Workspace facts (post-rename)

- **The packaged boards seed is bootstrap vocabulary only.** It exists so
  the router can match board names before the first `rita sync`; every
  fact RITA *states* (board metadata, Zephyr version) comes from the
  synced workspace data, and the synced `boards.json` supersedes the seed
  for routing too. A missing fact (no `zephyr/VERSION`) is reported as
  missing, never guessed.

## 2026-07-28 — Phase 7 (rename)

- **Keyring service name stays `aica`** — renaming it would orphan every
  secret users already stored. Revisit only with a migration that copies
  entries forward.
- **Legacy `AICA_*` env names are honored (and the sandbox sets both
  marker spellings) for one release** so external workers keep working;
  drop in 0.9.
- **Historical CHANGELOG/DECISIONS entries keep their original `aica.*`
  module paths** — they describe the code as it was at that version.

## 2026-07-28 — Phase 6 (Fix 6)

- **The supervisor uses in-process seams (WestCli/CoderCli) for
  pipeline work by default**; module processes are launched via the
  registry when installed. Full module-backed pipeline wiring (a
  ZephyrRunner proxy over RPC) is a hardening step for the packaged
  install — the protocol, registry, drain, caps, and crash isolation are
  all in and tested against real child processes.
- **One in-flight request per handle** (events stream independently).
  The smallest concurrency model that supports checkpoints and progress;
  request pipelining can come later without a wire change.
- **`docs/ACCESS.md` (laptop access beyond the workspace) is deferred**
  until a capability actually needs it — the enumerated-permission rule is
  stated in the spec so nothing lands implicitly.

## 2026-07-28 — Phase 5 (Fix 5)

- **The speech strip is deliberately over-aggressive** (drops any token
  with a code-file extension, any mostly-symbol line). A false positive
  costs a slightly clipped sentence; a false negative reads code aloud —
  the spec calls that a test failure, so the bias is one-directional by
  design.

## 2026-07-28 — Phase 4 (Fix 4)

- **A chunk aborted mid-speech replays in full on RESUME** (position is the
  chunk index, not a character offset). Chunks are single sentences, so the
  repetition is at most one sentence — simpler and more robust than
  intra-utterance offsets, which pyttsx3 cannot honor anyway.
- **The <300 ms PAUSE guarantee is architectural** (chunk boundaries +
  immediate engine stop), proven deterministically with a blocking fake.
  Real pyttsx3 stop latency on the target OS gets measured at first bench;
  if it misbehaves, the fallback is shorter chunks.

## 2026-07-28 — Phase 3 (Fix 3)

- **A sim-test patch re-enters at BUILD** (the directive's "goto 2") even
  though twister rebuilds internally: a patch can break the compile, and a
  `west build` catches that in seconds without burning a twister cycle.
- **`WestCli` ignores twister's exit code on purpose** — `twister.json` is
  parsed as the gate result either way, per the never-scrape-stdout rule.
- **Real `west`/the coder command paths are `pragma: no cover`** here: this
  container has no Zephyr toolchain or coding-agent CLI. The seams (`FakeWest`,
  `FakeCoder`) exercise the identical parsing/loop logic; the subprocess
  implementations run on the target machine. First bench milestone
  (docs/BENCH-PLAN.md, still to be scheduled) validates them for real.

## 2026-07-28 — Phase 2 (Fix 2)

- **twister `filter:` expressions are recorded, not evaluated.** Evaluating
  them needs a devicetree/Kconfig context only twister has — and twister is
  the gate anyway. The index may therefore over-offer candidates; the fit
  judge and twister itself weed those out.
- **`yamlmini` subset parser** covers block mappings/lists/scalars only.
  Real workspaces with exotic YAML (anchors, flow style) need
  `pip install .[firmware]` (pyyaml is tried first when present). Chosen to
  keep the zero-required-deps rule.
- **Index ranking is bag-of-words term overlap** (tags/id/name/description/
  depends_on). Good enough because the coding agent judges fit on the top matches
  anyway; smarter ranking is a hardening option, not a widening need.

## 2026-07-28 — Phase 1 (Fix 1)

- **Untimed wake proxy.** When the STT backend provides no word timestamps,
  the 500 ms greeting→name rule degrades to greeting-immediately-followed-by-
  name adjacency within one utterance. Removed when all shipped STT paths
  emit word timings (WhisperSTT already does via `word_timestamps=True`).
- **Fixed-window MicRecorder blurs inter-utterance pauses.** "hello" + 1 s
  pause + "Rita" across two recordings never wakes (correct); within one
  recording, word timestamps catch it. A VAD-segmented recorder would sharpen
  this but is out of scope (scope rule: harden, don't widen).
- **Chat fallback is a canned reply for now.** Wiring a real chat model into
  the fallback arrives with the supervisor's module wiring (Fix 6); routing
  correctness doesn't depend on it.

## 2026-07-28 — Phase 0

- **`RitaConfig` writes TOML by hand** (no `tomli-w` dependency). The config
  is a flat table of scalars, so a 15-line serializer keeps the
  zero-required-deps rule. Removed if the config ever needs nesting.
- **Legacy `~/.aica/` migration copies, never moves.** Safer for users with
  both versions installed during the transition; the old dir can be deleted
  manually after verifying. Revisit at the Phase 7 rename.
