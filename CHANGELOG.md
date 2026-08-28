# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

## [0.22.4] - 2026-08-28

### Fixed
- Docs only: GETTING-STARTED still said unit tests compile "with your
  Zephyr SDK's ARM gcc" — corrected to the actual policy (Arm's
  standalone arm-none-eabi on the SDK's GCC branch, release verified
  online; the SDK's arm-zephyr-eabi never compiles, it only names the
  version; the 14.3.0-vs-14.3.1 branch note included). Also verified in
  passing: the installer's ToolchainPresent guard exists, and the full
  scaffold pipeline runs green with the REAL unit tier (Unity + RITA's
  downloaded ARM gcc + QEMU) inside the iterate loop.

## [0.22.3] - 2026-08-28

### Changed
- **The toolchain release is now VERIFIED online, not assumed** (the
  owner's call): before downloading, RITA probes developer.arm.com for
  the SDK's GCC branch (rel1–rel3, one-byte ranged GETs over the same
  two-stage TLS chain) and picks the newest release Arm actually
  publishes. A branch with nothing published is an honest failure
  naming what was probed; an unreachable probe falls back to the
  derived rel1 so offline machines still get a concrete download error
  rather than a blocked path. Explicit `--release` skips probing. Live
  check at development time: 14.3→14.3.rel1, 13.2→13.2.rel1,
  12.2→12.2.rel1 all verified against Arm's server.

## [0.22.2] - 2026-08-28

### Changed
- **The SDK's arm-zephyr-eabi-gcc is never used to compile unit tests**
  (the owner's rule: it is built FOR Zephyr, not a standalone compiler).
  It now only tells RITA which version to fetch; the unit tier always
  compiles with Arm's standalone arm-none-eabi release on the SAME GCC
  branch. Patch-level honesty stated everywhere it matters: Zephyr SDKs
  report X.Y.0 (built at the GCC tag), Arm's standalone builds report
  X.Y.1 (the branch snapshot) — same GCC X.Y branch; RITA matches on
  X.Y and says so (e.g. SDK gcc 14.3.0 → Arm GNU 14.3.rel1).

## [0.22.1] - 2026-08-28

### Fixed
Both halves of the owner's failed ARM toolchain install:

- **The WRONG version could be downloaded.** The release table topped
  out at gcc 14.2, so an SDK on gcc 14.3 silently fell back to a
  DEFAULT of 13.2.rel1 — a mismatched toolchain, the exact thing the
  one-toolchain rule forbids. Release names are now DERIVED from the
  SDK's gcc (`release_for` → `{maj}.{min}.rel1`; naming verified live
  against Arm's server incl. 14.3.rel1 on both hosts), and when the
  SDK's gcc version can't be read RITA REFUSES to guess and says so
  (explicit `rita toolchain install --release X.Y.rel1` remains the
  escape hatch). After extraction the installed gcc is verified against
  the SDK's version; a mismatch is a failure, never a success. The
  `check setup` ARM-toolchain line now states the SDK's gcc version and
  the release it maps to.
- **TLS verification failed in the frozen app** ("unable to get local
  issuer certificate"): frozen Python doesn't reliably see the Windows
  cert store and RITA shipped no CAs. Downloads now try system trust
  first (corporate/proxy CAs keep working), then RITA's bundled Mozilla
  CA set (certifi, now collected into the bundle — the smoke test
  asserts cacert.pem ships). If both fail, the error says a security
  product/proxy is likely intercepting HTTPS and its certificate
  belongs in Windows' store. Verification is never disabled.

## [0.22.0] - 2026-08-28

### Fixed
- **Found by self-test, before it reached the owner: "build <sample>"
  could never succeed with CERBERUS installed, and the patch loop could
  edit the user's Zephyr tree.** The pipeline ran the MISRA gate over
  UNMODIFIED in-tree samples (stock Zephyr code doesn't aim for MISRA →
  guaranteed retries-exhausted) and pointed patches at the sample's
  directory INSIDE the workspace. Now: gates and patches apply to code
  RITA writes — scaffolded applications and authored tests. An
  unmodified in-tree sample skips STATIC with the reason stated, and a
  failing one is reported as a workspace/environment issue with the
  artifact shown, never patched. A defensive invariant makes the
  pipeline refuse any patch target outside RITA's workdir or the
  applications root (`docs/specs/static-check.md`, Scope section).
- Legacy gate/patch tests that encoded the old behavior were moved to
  the authored-code path they were really about.

### Self-test session (full product, run before release)
The whole product was exercised end to end in development, as a user:
frozen-bundle toolchain download (real, 13.2.rel1), every release URL in
the table probed on Arm's server (all valid, both hosts), real CERBERUS
and Unity clones from the frozen exe, sync + full `check`, the real unit
tier (ThrowTheSwitch Unity + downloaded arm-none-eabi-gcc + QEMU, with a
deliberate failure correctly caught: 3 ran / 2 passed / 1 failed), and a
scripted GUI walk over every page and button — nav, chat commands,
rename, controls, work task, project handoff, settings save/login/voice,
workspace sync, modules installs with simulated failures. The one defect
found is the fix above; "build blinky" and a project handoff now finish
green in the same walk.

## [0.21.1] - 2026-08-28

### Fixed
- **The Modules page lost install errors.** All three install buttons
  reported into one shared one-line label under the CERBERUS heading —
  each message overwrote the last (the ARM toolchain error flashed and
  was replaced by CERBERUS text), and an installer that RAISED was
  silently swallowed. The card is now "Gates & toolchain" with an
  append-only log naming each tool; worker exceptions land in it as
  "<tool> install FAILED: …", every result is mirrored to the Chat
  screen pane so a page switch can't lose it, and buttons re-enable for
  a retry.

## [0.21.0] - 2026-08-28

### Added
- **RITA owns the coding-agent login — no terminal, ever.** New
  **Log in coding agent** button on the Settings page: RITA opens the
  agent's own interactive login flow in its own console window
  (`coder_login_command` override for CLIs with a distinct login
  subcommand; default is the agent run bare, which prompts its login),
  and `check setup` verifies afterward. Every auth-failure message —
  task failures and the live diagnostic — now points at that button
  instead of telling the user to run a terminal command, which violated
  the product's core rule.

## [0.20.2] - 2026-08-28

### Fixed
- **`rita check` crashed on Windows consoles** (cp1252): the new ARM
  toolchain guidance contains a `→`, and printing it raised
  UnicodeEncodeError before any output landed — the diagnostic died
  while printing the diagnostic. The CLI now reconfigures its streams
  with errors="replace" so unencodable characters degrade instead of
  crashing, reproduced and fixed under a forced cp1252 stream. The
  bundle smoke test also prints the frozen exe's stderr, so a crash
  there can never be invisible again.

## [0.20.1] - 2026-08-28

### Fixed
- Two toolchain-detection tests carried POSIX path-separator assumptions
  that only surface on Windows (Path() renders `/usr/bin/…` as
  `\usr\bin\…`); comparisons and fixture keys are now
  separator-independent. Test-only — no product change.

## [0.20.0] - 2026-08-28

### Changed
- **One toolchain: the unit tier compiles with Zephyr's ARM GCC**
  (`docs/specs/unit-tier-toolchain.md`), per the owner's rule — whatever
  compiler Zephyr uses, RITA uses, at the SAME gcc version. No more
  host-compiler hunting, no LLVM/MinGW suggestions. `find_compiler`
  resolves arm-none-eabi-gcc via the new `firmware/toolchain.py`
  (order: RITA's own install → PATH → GNUARMEMB_TOOLCHAIN_PATH → the
  SDK's arm-zephyr-eabi-gcc), preferring the candidate whose gcc version
  MATCHES the Zephyr SDK's, and surfacing a mismatch instead of hiding
  it. Unrelated native compilers on the machine are never picked up.
- **RITA installs the toolchain herself when missing** — `rita toolchain
  install`, a Modules-page button, and a presence-guarded installer step
  download the Arm GNU release matching the SDK's gcc version into
  `~/.rita/toolchains/` (same acquisition contract as CERBERUS/Unity).
  Verified for real: the download, extraction, and gcc --version check
  ran end to end in development.
- **Unit tests execute under qemu-system-arm** (ARM binaries can't run
  on a PC): compiled directly — no Zephyr headers, no CMake, no west —
  with `-mcpu=arm926ej-s --specs=rdimon.specs`, run on the versatilepb
  machine with semihosting, output parsed exactly as before. Proven end
  to end with RITA's own downloaded toolchain: 2 tests, 1 deliberate
  failure detected. QEMU comes from PATH or the Zephyr SDK's host tools;
  missing pieces are honest `unavailable` reasons naming the fix.
  `host_cc` remains an explicit native override (runs directly).
- Diagnostics gain an **ARM toolchain** check (resolved gcc, source,
  version match vs the SDK, and the QEMU used); the bundle smoke test
  requires the check to be present.

### Fixed
- The 4 red CI tests: they assumed the runner had no compiler, but
  GitHub's Windows runner ships clang. Discovery tests now monkeypatch
  their toolchain surface, and by design an unrelated native compiler
  can never be selected.

## [0.19.1] - 2026-08-28

### Fixed
- **The MCP check no longer passes a stale config.** It verified only
  that the named executable existed, so a config written by an older
  build (`RitaApp.exe -m rita`, or a relative workspace) reported OK
  while being unusable. Both forms are now flagged, naming Sync as the
  fix.
- **Windows host compiler discovery is correct and honest**: the Zephyr
  SDK's toolchains are cross compilers emitting ELF, which Windows
  cannot execute, so they are no longer offered as host compilers there.
  Well-known native install dirs (LLVM, MSYS2/MinGW, Chocolatey) are
  searched beyond PATH, and when nothing is found the message names what
  to install and why.
- **An agent that isn't logged in says so**: auth/OAuth failures in a
  task or a diagnostic now add "your coding agent is not logged in —
  run it once in a terminal and complete its login", instead of leaving
  the raw provider text to be decoded.
- **The transcript escapes HTML**: a message containing `<stdio.h>` or
  `<module>` previously vanished into the rendered markup.

## [0.19.0] - 2026-08-28

### Fixed
- **THE cause of "the coding agent exited 1": the MCP SDK's 2.x rename.**
  `mcp` 2.x renamed `FastMCP` to `MCPServer`; RITA imported the 1.x name,
  so `rita mcp-serve` died on startup, the agent that launches it failed,
  and it exited 1 with nothing on stderr. The server now resolves either
  class (the decorator API is identical), and `mcp_available()` reports
  whether the server can actually be CONSTRUCTED, not merely imported.
- **`mcp` and the voice runtime are collected into the bundle**
  (`collect_all`): both are imported dynamically, so PyInstaller never
  saw them — they were missing only in the packaged app.
- **A broken MCP no longer blocks coding**: `CoderCli` retries once
  without `--mcp-config` and records the fallback. Workspace tools are an
  enhancement, not a prerequisite for authoring code.
- **Coder failures quote everything**: argv, exit code, stdout tail AND
  stderr tail — the previous message discarded the output it mentioned.
- `mcp.json` stores an absolute workspace path (the agent launches the
  server from its own directory, not RITA's).

### Added
- **Diagnostics** (`docs/specs/diagnostics.md`): `rita.diagnostics`
  checks workspace, coding agent (including a real live invocation),
  MCP, voice, west, SDK, CERBERUS and Unity, each reporting the concrete
  finding. Say or type **"check setup"** (or the Settings page's *Check
  setup* button — same deterministic path) and the report lands in the
  screen pane. Also `rita check [--deep] [--require ...]`.
- **The packaged bundle is now smoke-tested before release**
  (`packaging/smoke_bundle.py`, run locally and in CI): it drives the
  BUILT executables through doctor → sync → mcp.json validation → MCP
  server boot → module install → self-check, and fails the build on any
  of them. Source tests cannot see bundle-only breakage; every failure
  reported from a real install so far was exactly that kind.

## [0.18.3] - 2026-08-28

### Fixed
- **The installer keeps what's already on the machine**: re-running
  Setup no longer re-downloads CERBERUS or Unity — it probes the same
  files the app's own detection uses (`~/.rita/cerberus/cerberus/cli.py`,
  the Unity sources) and skips the download steps when present. Updating
  those tools stays an explicit button on the Modules page. The wizard
  text says so.

## [0.18.2] - 2026-08-28

### Fixed
- **Packaged installs' mcp.json was unusable** — the real cause of the
  live "test writer returned unparseable output" failure: it launched
  the MCP server as `RitaApp.exe -m rita`, which a frozen GUI exe cannot
  interpret, so the coding agent's MCP startup failed and it exited with
  empty output. Frozen installs now point mcp.json at the bundled
  console CLI (`rita.exe mcp-serve`). Re-sync once after updating to
  rewrite the file.
- **The coder seam reports agent failures concretely**: an agent that
  exits nonzero or prints nothing raises "the coding agent (<cmd>)
  exited N — <stderr>" instead of handing empty output downstream to
  die as a JSON parse error.
- **Voice runtime ships in the installer** ("installs on first use" was
  impossible inside a frozen bundle): sounddevice, faster-whisper, and
  pyttsx3 are now bundled (torch stays excluded — not needed). The
  Whisper model still downloads on the first spoken turn. Missing-dep
  probing is eager, so failure lands at enable time ("Voice isn't
  available: missing voice packages: …"), never mid-listen.

## [0.18.1] - 2026-08-28

### Fixed
- **Windows launcher shims resolve now** — the real cause of the live
  "Task failed: FileNotFoundError [WinError 2]": npm/pip CLIs on Windows
  are `.cmd`/`.bat` shims, and CreateProcess doesn't search PATHEXT the
  way a shell does, so launching the configured coder command (or west /
  a custom CERBERUS command) by bare name failed even though it works in
  a terminal. Every external command now resolves its executable through
  `shutil.which` at invocation (`resolve_argv`), and a genuinely missing
  one fails naming the executable and pointing at Settings — never a
  bare WinError.

## [0.18.0] - 2026-08-28

### Added
- **The microphone lands in the app** (`docs/specs/voice-in-gui.md`):
  the Settings "Enable voice" checkbox is real now — persisted
  (`voice_enabled`), applied live, and re-armed on launch. Listening
  runs on a background thread inside the GUI: wake word ("hello Rita" /
  the configured name) → the same deterministic router as typed input →
  replies through the two-channel split (≤2 spoken sentences via the
  pausable speaker; code/logs to the screen pane). Heard speech is
  echoed in the transcript (🎤); utterances RITA ignored while asleep
  leave no trace. "stop listening"/"goodbye" put the wake gate back to
  sleep with the mic still armed. Missing voice deps are reported by
  name — the checkbox never silently pretends. 7 tests written first
  (7 failed) covering wake, sleep, stop phrases, thread stop, config
  round-trip, and honest unavailability.

### Fixed
- **A corrupt config no longer wedges the app**: a config written badly
  by an older build (raw Windows backslashes) is backed up to
  `config.bad` and RITA starts from defaults instead of crashing — one
  re-save in Settings recovers, no reinstall, no re-sync.

## [0.17.0] - 2026-08-28

### Changed
- **Vendor-neutral coding-agent seam**
  (`docs/specs/coding-agent-seam.md`): which CLI codes for RITA is now
  pure config data, like the assistant's spoken name. New
  `RitaConfig.coder_command` (+ "Coding agent" field in Settings); no
  vendor CLI name ships in the codebase. Unset means RITA answers work
  and project handoffs with an honest "no coding agent is configured —
  set it in Settings" message. `firmware/coder.py` owns the seam
  (`CoderWorker` / `CoderCli` / `FakeCoder`); the module is
  `coder-worker`; the status bar reports "coder ✓ / coder not
  configured" from the configured command, not a hardcoded lookup.
- The legacy cloud-planner path no longer ships a vendor client: a cloud
  planner/backend is injected or absent (local/mock only), the vendor
  SDK extra is gone, and the DLP/egress/sandbox defaults are
  vendor-neutral (generic secret patterns still redact and filter).
- Docs scrubbed to match; the repo working rules moved to
  `docs/WORKING-RULES.md`.

### Fixed
- **A failed task now reports its reason**: `task_summary` for a FAILED
  task includes the exception ("Task task-1 failed: …") instead of the
  bare state — exhaustion and failure are reported outcomes, never
  hidden.

## [0.16.3] - 2026-08-28

### Fixed
- **The installed RitaApp.exe crashed at launch** ("attempted relative
  import with no known parent package"): the PyInstaller spec fed the
  package modules (`rita/gui/app.py`, `rita/__main__.py`) in as
  top-level scripts, so their relative imports had no parent package.
  Both executables now start from `packaging/launch_gui.py` /
  `launch_cli.py` shims that import the package absolutely. Verified by
  building the bundle and running both executables (GUI offscreen).

## [0.16.2] - 2026-08-28

### Fixed
First run of the test suite on a real Windows machine (the installer
workflow) caught 10 failures — two real product bugs and a batch of
POSIX-only test assumptions:

- **Config files with Windows paths were unloadable**: the hand-written
  TOML serializer wrote `\` unescaped, so `workspace = "C:\zephyrproject"`
  produced a config `tomllib` rejects. Strings now escape `\` and `"`.
- **`cerberus_command` was mangled on Windows**: POSIX `shlex.split` eats
  path backslashes (`C:\tools` → `C:tools`). New `split_command()` splits
  non-POSIX on Windows and strips kept quotes.
- Unity failure lines with a `C:\` drive prefix (and CRLF endings) now
  parse — a failing unit test on Windows was previously reported green
  with its failure artifact lost.
- `ModuleHandle.alive` is False once the protocol stream has ended, even
  before the OS reaps the process (Windows EOF-vs-poll race in crash
  isolation).
- Test-suite portability: fake-command fixtures quote their paths, the
  explicit-compiler test uses a temp file instead of `/usr/bin/gcc`,
  path assertions compare `Path` objects, and the fake-SDK end-to-end
  compile test (a `/bin/sh` wrapper) is skipped on Windows with the
  reason stated.
- Installer workflow: `actions/checkout@v5` / `setup-python@v6` (Node 20
  deprecation).

## [0.16.1] - 2026-08-28

### Fixed
- The new Projects page is listed in the PyInstaller hidden imports
  alongside the other pages, so the bundled `RitaApp.exe` ships it.

## [0.16.0] - 2026-08-28

### Added
- **Projects: hand whole tasks off to RITA** (`docs/specs/projects.md`).
  "start a project: …" / "take on …" / "hand off …" route
  deterministically to a handoff (checked before verb matching, so
  "create a project to…" is never mistaken for scaffolding). A goal that
  already routes as a verb-grounded command becomes a one-item project
  RITA runs **with no AI involved**; a genuinely multi-step goal gets
  **one bounded AI call** that returns the plan as **pure data** — items
  phrased in RITA's own command grammar with dependencies, estimates,
  and milestones — validated by routing every command. Unroutable items
  are flagged `needs_user`, never guessed at; garbage or oversized plans
  are rejected loudly (`PlanError`). **RITA executes every item herself**
  through the full gate pipeline (CERBERUS → per-function unit tests →
  final test), dependency-ordered, with cascade blocking, per-item
  workdirs (`work/<proj>/<item>/`), pause/stop checkpoints between
  items, and every transition persisted to `~/.rita/projects.json`
  (restart-safe). The AI authors data; it never routes, schedules, or
  executes — same as everywhere else in RITA.
- **Projects page** in the GUI: a handoff box (feeds the same route as
  typing the command) and a live item list read from the persisted
  store. "how is the project going" answers with live counts in chat.
- 16 new tests (planner, store round-trip, runner completion/cascade/
  stop, routing, chat status); written first and confirmed failing
  (16 failed) before implementation. Full suite: 339 passed.

## [0.15.1] - 2026-07-28

### Changed
- **Unit-tier compiler discovery uses the Zephyr SDK** (it ships gcc by
  default; the LLVM bundle is detected as the non-default variant):
  order is explicit `host_cc` override (new config + Settings field) →
  host PATH compiler → SDK toolchain. No MinGW requirement — an
  SDK machine needs nothing extra. SDK builds link `-static`; if a
  cross-built binary can't execute on the host, the failure says so
  concretely instead of guessing either way.

## [0.15.0] - 2026-07-28

### Changed
- **The pipeline now matches the owner's flow exactly**: ask → code →
  CERBERUS → **unit test every single function** → iterate → **final
  test = the Zephyr samples/tests**. Stages are RESOLVE → STATIC →
  UNIT_TEST → FINAL_TEST → DEVICE (BUILD/SIM_TEST are gone as named
  stages; compiling is an internal detail of the final test).

### Added
- **Per-function unit tier** — the owner's TDD definition: every function
  written is tested for its **input and output parameters** (valid,
  boundary, invalid) before moving on, and the coding contract requires
  every function to **restrict or validate** its parameters before
  executing (rule stated verbatim in the scaffold brief).
- Host **Unity** runner (`rita.firmware.unity.HostUnity`): compiles
  unity.c + tests + sources with the host compiler, parses Unity output
  into concrete artifacts; honest `unavailable` when compiler/framework
  missing. Unity acquisition mirrors CERBERUS (`rita unity install`,
  installer hook, GUI button; CERBERUS's own `unity/` layout detected).
- Deterministic per-function coverage gate
  (`rita.firmware.functions`): scans authored C for function definitions
  and fails the stage naming any function without a `test_<name>` — no
  judgment calls. Unit-test authorship (`write_unity_tests`) validates
  full coverage and rejects ztest-shaped output.
- `FailureArtifact.kind` gains `"unit"`; sample-only runs report the unit
  stage `skipped: no authored code`. Knowledge topics `function-contracts`
  and `unity-testing` brief the coding agent.

## [0.14.0] - 2026-07-28

### Added
- **The real CERBERUS wired in** (github.com/RichardSWheatley/cerberus,
  "G.U.A.R.D."): acquisition is part of RITA's install —
  `rita cerberus install` clones it to `~/.rita/cerberus` (installer
  component runs it post-install; GUI Modules page has an Install/update
  button; needs git). The supervisor auto-detects the clone and wires the
  gate with zero config; an explicit `cerberus_command` still overrides.
- Adapter pinned to the CERBERUS contract: `python -m cerberus.cli scan`
  from the clone (argv + cwd support in `CerberusCli`); **exit 0 =
  approve, 1 = request changes, 2 = block** — both non-zero verdicts gate,
  named in the artifact reason. Default = Head 1 `scan` (94 deterministic
  MISRA/CERT checks, keyless — matching the no-LLM-judges rule);
  `cerberus_deep` opts into `analyze` (Oracle LLM — the coding agent's seat inside
  CERBERUS — + Unity heads) using CERBERUS's own env credentials.
- The cerberus RPC module falls back to the detected clone when no
  command is configured.
- Tested offline: real `git clone` of a local fixture repo, real
  subprocess verdicts both ways, end-to-end acquired-gate check.

## [0.13.0] - 2026-07-28

### Added
- **CERBERUS static-check gate** (`rita.firmware.static_check`): the flow
  is now ask → code → **STATIC** → build → twister → iterate → final
  test. A new STATIC stage sits between the coding agent's code and the compiler,
  and **every patch — static, compile, or test — re-enters at STATIC**,
  so patched code always re-passes the gate before rebuilding.
- `StaticChecker` seam: `CerberusCli` runs the configured command
  (`RitaConfig.cerberus_command`, also in GUI Settings) over the target;
  exit 0 = clean; JSON findings parse into `FailureArtifact(kind="static")`
  and any other output still yields a concrete artifact. Unconfigured →
  the stage reports `skipped` — visible, never silently green.
- The `cerberus` module is now a real RPC wrapper over the gate
  (`start {command}` / `check {target}`, v0.2.0), keeping its honest
  not-configured answer when unset.
- Spec: `docs/specs/static-check.md`; iterate-loop spec updated.

## [0.12.1] - 2026-07-28

### Added
- `docs/GETTING-STARTED.md`: the GUI-first user guide — installer +
  components, pointing RITA at the Zephyr folder, workflow examples (the
  MSPI/PSRAM utterance as the flagship), the two panes and two buttons,
  where things land, what's deliberately blocked, troubleshooting, and a
  5-minute smoke checklist. README links it as the primary path.

## [0.12.0] - 2026-07-28

### Added
- **Modular Windows installer** (`packaging/`): PyInstaller bundle with two
  executables — windowed `RitaApp.exe` (the app) and console `rita.exe`
  (dev CLI + module host) — and an Inno Setup installer with selectable
  components (core+GUI required; voice, workspace MCP, and each capability
  module individually selectable). Post-install, module registration is
  manifest-writing into `%USERPROFILE%\.rita\modules\` via
  `rita.exe modules install --only <selected>`. Start-menu/desktop
  shortcuts launch the GUI; uninstall leaves `~/.rita` user data.
- `rita module-run <name>`: hosts a capability module over stdio — the
  universal manifest entrypoint that works identically from a venv
  (`python -m rita module-run X`) and a frozen bundle (no `python -m`
  available). `modules install --only a,b` installs a subset.
- CI: `.github/workflows/installer.yml` builds the bundle and installer on
  windows-latest (manual dispatch or version tags) and uploads
  `RITA-Setup-<version>.exe` as an artifact; `packaging/build.ps1` is the
  same recipe for a local one-command build.
- Spec: `docs/specs/installer.md`.

## [0.11.0] - 2026-07-28

### Added
- **Zephyr knowledge pack** (`rita.firmware.knowledge` +
  `firmware/data/knowledge/`): ten curated topics researched from
  docs.zephyrproject.org (building apps, app locations, west commands,
  twister, ztest, devicetree overlays, **MSPI**, **PSRAM over MSPI**,
  flash/debug, SDK), each citing its source and research date. Retrieval
  is deterministic keyword matching — no LLM. Facts about the user's
  install still come only from the workspace.
- MCP tools `zephyr_howto(topic)` + `list_topics` — the coder-worker's
  source for conventions; chat answers "how do I…" questions from topic
  summaries.
- Scaffold/test-writer prompts are enriched with matched topic notes
  (bounded), so e.g. an MSPI/PSRAM request carries the mspi + psram
  recipes.
- **RITA knows where to build**: `RitaConfig.applications_dir` (default
  `<workspace>/applications`); scaffolded apps land there under a slug of
  the request — beside `zephyr/`, never in it.
- Routing: `mspi`, `psram`, `qspi`, `ospi`, `flash`, `dma` peripherals and
  `example`/`sample`/`test` artifacts; "build me an example …" (artifact,
  no existing sample named) upgrades deterministically to scaffold — the
  flagship utterance "build me an example for MSPI that communicates with
  a PSRAM on MSPI0 in hex mode" routes to scaffold with mspi/psram terms.
- **SDK awareness from the actual install**: `read_sdk_info`
  (`ZEPHYR_SDK_INSTALL_DIR`, standard locations, `sdk_version` file; absent
  = reported, not guessed) in `workspace_info`, boards facts, and the GUI
  status bar.
- Spec: `docs/specs/zephyr-knowledge.md`.

## [0.10.0] - 2026-07-28

### Added
- **The GUI** (`rita.gui`, `rita-app`, `python -m rita.gui`): a native
  PySide6/Qt app — dark modern theme, sidebar (Chat / Workspace / Modules /
  Settings), chat transcript (speech channel) + monospace screen pane
  (code/diffs/logs, per Fix 5), prompt bar (typed commands may be quoted;
  no wake word needed when typing), and the **persistent PAUSE and
  RESUME/STOP buttons** from the Fix 4 spec. Pointing RITA at the Zephyr
  folder, syncing, module install, and settings (assistant name, budgets)
  all happen inside the GUI. First run lands on the Workspace page.
- All GUI behavior lives in a headless `GuiPresenter` (fully tested without
  a display; the Qt view is a thin binding, itself smoke-tested offscreen):
  quote stripping, typed routing, channel separation, pause/stop
  semantics, unprompted task-completion announcements, workspace sync.
- `RouterShell.handle_typed`: typed input routes without a wake word (a
  leading "Rita," still strips off).
- **MCP wiring completed**: `sync` now writes `~/.rita/mcp.json`
  (interpreter-anchored `rita mcp-serve` invocation) and the supervisor
  hands it to the coder-worker — the coder command actually reaches the
  workspace MCP server now.
- Sync accepts either the workspace root or the `zephyr/` folder itself.
- New optional extra `gui = ["PySide6-Essentials"]`; `TaskManager.tasks()`.
- Spec: `docs/specs/gui-shell.md`.

## [0.9.0] - 2026-07-28

### Added
- **Zephyr facts come from the actual install** (`rita.firmware.workspace`):
  the version is parsed from the checkout's `zephyr/VERSION` file
  (EXTRAVERSION honored; a missing file is reported, never guessed) and
  recorded in `boards.json` alongside a sync timestamp.
- MCP tool `workspace_info`: version, workspace path, board and indexed-
  suite counts served to the coder-worker.
- Chat answers workspace questions deterministically from synced data:
  "tell me about the apollo510" describes the real board (vendor, arch,
  twister platform, supported peripherals, connected port); "what zephyr
  version" answers from the install. No LLM, no invention.

## [0.8.0] - 2026-07-28

### Changed
- **The project is now RITA** — Routing, Iteration, Testing, Automation.
  Package `aica` -> `rita`; CLI `rita` (an `aica` alias script remains for
  one release); dist name `rita`; docs and specs swept. `llm/router.py`
  (model selection) renamed to `llm/model_router.py`, freeing "router" for
  the intent router.
- Env vars: `RITA_LOCAL_ONLY`, `RITA_SANDBOX`, `RITA_NO_NETWORK`,
  `RITA_GRAPH_*` — legacy `AICA_*` names still honored/set for one release.
  The keyring service name stays `aica` on purpose (renaming would orphan
  stored secrets).
- Config/data live in `~/.rita/` (introduced in 0.1.1; a legacy `~/.aica/`
  is migrated automatically, including `boards.json`).

## [0.7.0] - 2026-07-28

### Added
- **Fix 6 — supervisor + versioned module processes** (`aica.modules`,
  `aica.supervisor`): capabilities run as separately versioned child
  processes under `~/.rita/modules/<name>/<version>/` with language-agnostic
  manifests (entrypoint argv, capabilities, max_instances, min_supervisor,
  exclusivity keys) and a `current` pointer file. Updates = drop a dir +
  flip the pointer; running instances drain on their version; rollback =
  flip back.
- Module IPC: the worker wire shape upgraded with a mandatory `hello`
  handshake (protocol + version verified at launch), enforced per-call
  timeouts, and async events (progress/checkpoint/log) demultiplexed by a
  per-handle reader thread.
- Registry: instance caps and exclusive resource claims (zephyr-runner per
  serial port, joulescope max 1); crash isolation — a dead module fails its
  call with the stderr tail and the supervisor keeps working.
- Shipped modules: voice-in, voice-out, zephyr-runner, coder-worker,
  scaffold; cerberus + joulescope as honest stubs. `modules` CLI
  (list / `install --dev`).
- `Supervisor`: thin shell owning the router, TaskManager, PAUSE/STOP,
  output channels, and the registry; `talk` now runs through it (wake word
  + grammar routing + managed pipeline tasks).
- Spec: `docs/specs/supervisor-modules.md`.

## [0.6.0] - 2026-07-28

### Added
- **Fix 5 — two output channels** (`aica.ui.channels.split_response`):
  every response splits into speech (≤2 conversational sentences) and
  screen (the full artifact, byte-for-byte). The shell strips fenced code,
  diffs, inline code, URLs, paths, and symbol-heavy lines from the TTS path
  unconditionally — the deterministic strip is the guarantee, whatever the
  model returns. Code-only responses speak a fallback sentence.
- `VoiceLoop` enforces the split on both handler paths and hands the screen
  channel to an `on_screen` sink; `PausableSpeaker.say` is non-blocking so
  the first sentence plays while the rest streams.
- Spec: `docs/specs/output-channels.md`.

## [0.5.0] - 2026-07-28

### Added
- **Fix 4 — PAUSE / RESUME / STOP** (`aica.core.tasks`): `TaskManager` +
  `TaskControl.checkpoint` state machine. PAUSE suspends at the next safe
  checkpoint (hardware operations stay atomic — checkpoints exist only
  between pipeline stages); RESUME continues exactly where execution
  blocked, so a task paused after BUILD resumes into twister **without
  rebuilding**. STOP cancels at a safe boundary and reports partial
  results; the manager survives and keeps accepting tasks. Crashes are
  FAILED, not fatal.
- `PausableSpeaker` (`aica.voice.tts`): sentence-chunked speech with
  instant pause (engine stop + kept position), resume-from-position, and
  queue-flushing stop.
- `make_control_handler`: the router's control words (pause / resume /
  stop) drive the manager and speaker.
- Spec: `docs/specs/pause-stop.md`.

## [0.4.0] - 2026-07-28

### Added
- **Fix 3 — the iterate loop belongs to the orchestrator**
  (`aica.firmware.pipeline.IteratePipeline`): RESOLVE -> BUILD -> SIM_TEST
  -> DEVICE with bounded patch budgets (`max_patch_cycles`) at every stage;
  a sim patch re-enters at BUILD; exhaustion is a reported outcome, never
  hidden. Sim-first always; the DEVICE stage is blocked on the bench
  milestone and never faked green; hardware maps are generated, never
  hardcoded.
- `parse_twister_json` (`twister_results.py`): twister.json is the only
  gate truth — never scraped stdout. Failures become `FailureArtifact`s
  (kind, reason, log excerpt, file hints).
- `ZephyrRunner` seam: `WestCli` real subprocess impl (runs where Zephyr is
  installed) + scripted `FakeWest` over fixture twister.json files.
- `CoderWorker` seam: `CoderCli` (the coder command + workspace
  `--mcp-config`, bounded timeout) + recording `FakeCoder`. `patch()`
  requires a concrete failure artifact — enforced, tested.
- `handle_work_dispatch`: Fix 1 work dispatches now drive the pipeline.
- Fixture twister results (pass / build-fail / test-fail).
- Spec: `docs/specs/iterate-loop.md`.

## [0.3.0] - 2026-07-28

### Added
- **Fix 2 — verification resolution** (`aica.firmware`): static index of
  `samples/**/sample.yaml` + `tests/**/testcase.yaml` (platform_allow,
  filter, harness, depends_on, tags) built at `sync`, saved to
  `~/.rita/verification-index.json`. Pure data, no LLM. Board-compat
  filtering + term ranking in `find()`.
- `boards.json` generation from `boards/**/board.yml` + twister platform
  yamls, merged with the twister hardware map; derived spoken aliases feed
  the Fix 1 router after the first sync.
- Fit judge (`judge_fit`): the coding agent judges fit ONLY — one bounded call over
  the index's top matches; cannot introduce non-candidates.
- Test writer (`write_ztest`): no match -> the coding agent authors a ztest with a
  validated `testcase.yaml` so twister gates it like everything else.
- `resolve_verification`: the find-or-write pipeline entry.
- **Workspace MCP server** (`aica.mcpserver`, `mcp-serve` CLI): stdio server
  exposing find_verification / board_info / list_boards / sample_lookup /
  read_workspace_file / grep_workspace — read-only, workspace-rooted,
  traversal-guarded. `mcp` SDK is an optional extra.
- Vendored YAML-subset parser (`yamlmini`) with pyyaml fallback
  (`.[firmware]` extra) to keep zero required deps.
- `sync` CLI command; fixture Zephyr workspace for hermetic tests.
- Spec: `docs/specs/verification-resolution.md`.

## [0.2.0] - 2026-07-28

### Added
- **Fix 1 — grammar-first routing** (`aica.routing`): a pure, table-driven
  router over domain vocabulary (work verbs, board names from boards.json,
  samples, peripherals). Anything naming a board/sample/artifact is work;
  interrogatives and unmatched utterances fall back to chat — inverted from
  the old LLM-guesses-intent design.
- Wake grammar as stage zero (`WakeGate`): greeting + name within 0.5 s
  (word timestamps), bare name, one-utterance wake+command; greeting with a
  pause and no name is not a wake event.
- `RouterShell` in the voice loop: wake -> route -> handlers; the assistant's
  spoken name is config data, renameable by voice, persisted across restart.
- Packaged board-vocabulary seed (`firmware/data/boards.seed.json`) so
  routing works before the first workspace sync.
- STT word-timestamp support: `Utterance` value type,
  `WhisperSTT.transcribe_utterance`, scriptable `FakeSTT`.
- Spec: `docs/specs/project-work-routing.md`.

## [0.1.1] - 2026-07-28

### Added
- RITA process scaffolding per the directive: `BRIEF.md`, the working rules,
  `docs/DECISIONS-LOG.md`, `docs/specs/`.
- `aica.home`: the `~/.rita/` data root (`RITA_HOME` override), path
  constants, and one-shot `~/.aica/` migration (incl. `boards.json`).
- `RitaConfig` persisted at `~/.rita/config` (TOML): assistant spoken name
  (default "Rita"), Zephyr workspace path, hardware map, iterate-loop
  budgets, device-tier gate.

### Changed
- Audio, screenshot, and sandbox paths moved from cwd-relative `.aica/…` to
  the `~/.rita/` home.

## [0.1.0]

- AICA MVP skeleton: agent loop, plugins, voice I/O, worker protocol, docs.
