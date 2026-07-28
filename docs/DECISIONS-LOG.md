# Decisions log

Compromises, proxies, and deferred decisions — with the reason and what would
remove them. Newest first. (Required by the working rules in `CLAUDE.md`.)

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
  patches), which can consume static budget on code Claude just changed —
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

- **The supervisor uses in-process seams (WestCli/ClaudeWorkerCli) for
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
- **Real `west`/`claude -p` paths are `pragma: no cover`** here: this
  container has no Zephyr toolchain or claude CLI. The seams (`FakeWest`,
  `FakeClaude`) exercise the identical parsing/loop logic; the subprocess
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
  depends_on). Good enough because Claude judges fit on the top matches
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
