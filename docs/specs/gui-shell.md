# Spec: The GUI shell

## Problem

RITA's main interface is a **GUI application** that looks and behaves like a
native app — not a web browser, not a terminal. Nothing in the user path
runs via command line: pointing RITA at the Zephyr folder, syncing, module
management, and all conversation happen inside the GUI. The CLI remains a
developer tool only.

## Design

**Toolkit: PySide6 (Qt 6)** — native widget rendering, professional QSS
styling, PyInstaller-friendly, cross-platform for the later macOS/Linux
step. Optional extra `gui = ["PySide6"]`; the packaged app ships with it,
the test suite skips Qt-level tests without it.

### Presenter first (headless, fully tested)

All behavior lives in `rita.gui.presenter.GuiPresenter`, a plain-Python
layer over the existing `Supervisor` — the Qt view binds to it and stays
thin:

- `submit_text(text)` — typed input from the prompt bar. Surrounding
  quotes (straight or smart) are stripped: the user quotes commands, RITA
  routes the contents. Typed input needs **no wake word** (the shell's wake
  gate applies to voice); it flows through the same grammar router as
  speech. Handling runs on a worker thread; the UI never blocks.
- Callbacks (plain callables; the Qt layer connects them to signals):
  `on_user(text)`, `on_reply(speech)` (speech channel), `on_screen(text)`
  (screen channel — code/diffs/logs), `on_task(TaskSnapshot)`,
  `on_status(StatusInfo)`.
- `pause()`, `resume()`, `stop()` — the two persistent buttons (Fix 4) bind
  here; semantics via `make_control_handler` (speech pauses instantly,
  tasks suspend at the next safe checkpoint).
- A watcher thread announces task transitions: when a submitted pipeline
  task finishes, the transcript gets the spoken-style summary
  (`describe(report)`) and the screen channel gets the stage detail — a
  finished build reports itself without being asked.
- `sync(path)` — workspace pointing from the GUI; runs `sync_workspace`
  off-thread, persists `RitaConfig.workspace`, emits progress + a result
  line (boards, suites, Zephyr version — all read from the actual install).
- `status()` — workspace path, Zephyr version, module count, claude CLI
  presence: the GUI status bar's facts.

### The window

`RitaWindow` (dark, modern QSS theme — accent color, consistent radii and
spacing, system font, monospace code pane):

- Left sidebar: **Chat**, **Workspace**, **Modules**, **Settings**.
- Chat page: transcript (user entries + Rita's speech-channel replies),
  a separate read-only monospace **screen pane** for code/diffs/logs
  (Fix 5's two channels, visibly two panes), prompt bar with Send.
- **Persistent control bar: PAUSE and RESUME/STOP buttons** — always
  visible, per Fix 4. Button state reflects the task state machine
  ("pausing after current step…" → "paused").
- Workspace page: "Point RITA at your Zephyr workspace" folder picker,
  sync progress, last-sync summary; shown first when no workspace is
  configured (first-run flow).
- Modules page: discovered modules with current-version markers; install
  bundled modules button.
- Settings page: assistant name, patch budget, voice on/off,
  push-to-talk.

Entry points: `python -m rita.gui`; console script `rita-app` (windowed).

### MCP wiring (folded in — the claude-worker must reach the workspace)

`sync_workspace` additionally writes `~/.rita/mcp.json`:

```json
{"mcpServers": {"rita-workspace": {
  "command": "<sys.executable>",
  "args": ["-m", "rita", "mcp-serve", "--workspace", "<ws>"]}}}
```

`Supervisor._make_claude()` passes it to `ClaudeWorkerCli` when the file
exists — `claude -p` then sees the workspace through the MCP tools.

## Acceptance criteria (each is a test)

- A quoted command routes identically to its unquoted form.
- Typed input routes without any wake word; board/verb utterances become
  work, questions stay chat.
- Speech-channel text and screen-channel text arrive via separate
  callbacks; code never appears in `on_reply`.
- Pause during a running pipeline task drives PAUSING → PAUSED at the
  checkpoint; resume completes without rebuilding; stop reports partial
  stages (same guarantees as Fix 4, now via presenter methods).
- A completed task announces its outcome in the transcript unprompted.
- `sync(path)` from the presenter writes boards.json + index + mcp.json
  and updates the persisted config.
- `Supervisor` hands the mcp config to the claude-worker when present.
- Qt layer: constructing the window and wiring the presenter succeeds
  (smoke test, skipped when PySide6 isn't installed).
