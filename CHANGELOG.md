# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow semver.

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
  `cerberus_deep` opts into `analyze` (Oracle LLM — Claude's seat inside
  CERBERUS — + Unity heads) using CERBERUS's own env credentials.
- The cerberus RPC module falls back to the detected clone when no
  command is configured.
- Tested offline: real `git clone` of a local fixture repo, real
  subprocess verdicts both ways, end-to-end acquired-gate check.

## [0.13.0] - 2026-07-28

### Added
- **CERBERUS static-check gate** (`rita.firmware.static_check`): the flow
  is now ask → code → **STATIC** → build → twister → iterate → final
  test. A new STATIC stage sits between Claude's code and the compiler,
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
- MCP tools `zephyr_howto(topic)` + `list_topics` — the claude-worker's
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
  hands it to the claude-worker — `claude -p` actually reaches the
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
  suite counts served to the claude-worker.
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
- Shipped modules: voice-in, voice-out, zephyr-runner, claude-worker,
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
- `ClaudeWorker` seam: `ClaudeWorkerCli` (`claude -p` + workspace
  `--mcp-config`, bounded timeout) + recording `FakeClaude`. `patch()`
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
- Fit judge (`judge_fit`): Claude judges fit ONLY — one bounded call over
  the index's top matches; cannot introduce non-candidates.
- Test writer (`write_ztest`): no match -> Claude authors a ztest with a
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
- RITA process scaffolding per the directive: `BRIEF.md`, `CLAUDE.md`,
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
