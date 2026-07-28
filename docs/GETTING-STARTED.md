# Getting started with RITA

RITA is a desktop app: install it, point it at your Zephyr workspace, and
talk to it — typed or spoken. Nothing here requires a command line; the
few commands shown are for building the installer itself or for
developers.

## 1. What you need on the machine

| Requirement | Why | Check |
|---|---|---|
| Windows 10/11 (64-bit) | first-supported OS (macOS/Linux later) | — |
| A working Zephyr workspace | RITA operates **on** it; it learns your boards, samples, and Zephyr version from this folder | `west build` already works for you in it |
| Zephyr SDK installed | real-board builds | RITA's status bar shows "SDK \<version\>" when found |
| Claude Code CLI, logged in | RITA's coding agent (`claude -p`) for scaffolding, test-writing, and patches | RITA's status bar shows "claude ✓" |

Without the `claude` CLI, RITA still routes, syncs, indexes, and answers
questions — it just can't author or patch code.

## 2. Install RITA

**Option 1 — the installer (recommended).** Download
`RITA-Setup-<version>.exe` (built by the `windows-installer` GitHub
Actions workflow — run it from the repo's Actions tab and grab the
artifact, or ask for a release build). Run it and pick your components:

- **Core + GUI** (always installed) — the app itself.
- **Voice** — wake-word listening and speech output modules.
- **Workspace MCP** — the local MCP server the coding agent uses to see
  your workspace (recommended: keep it).
- **Modules** — zephyr-runner (build/test/flash), claude-worker,
  scaffold, plus cerberus/joulescope placeholders (honest stubs until
  their tool/hardware is present).

The installer registers your selected modules under
`%USERPROFILE%\.rita\` and puts **RITA** in the Start menu. Uninstalling
never touches your `%USERPROFILE%\.rita` data or your Zephyr workspace.

**Option 2 — build the installer yourself once** (PowerShell, from a repo
checkout): `powershell -File packaging\build.ps1` → produces
`dist\installer\RITA-Setup-<version>.exe`.

## 3. First run: point RITA at your Zephyr folder

Launch **RITA** from the Start menu. On first run it opens the
**Workspace** page:

1. Click **Browse…** and choose your workspace folder — the one that
   *contains* `zephyr/` (e.g. `C:\zephyrproject`). Choosing the `zephyr`
   folder itself also works; RITA figures it out.
2. Optionally add a twister hardware map (`map.yaml`) if you have boards
   connected.
3. Click **Sync workspace**.

Sync reads *your actual install* — boards (with spoken aliases), every
sample and test suite's metadata, and the Zephyr version from
`zephyr/VERSION` — and wires the coding agent to see the workspace
through RITA's local MCP server. The status bar now shows your workspace,
Zephyr version, and SDK. **Re-sync after `west update`.**

## 4. Talking to RITA

Type into the prompt bar on the **Chat** page — put commands in quotes if
you like; RITA strips them and routes the contents. With Voice enabled,
say **"hello Rita"** (or just "Rita") to wake her; typed input never
needs a wake word. Routing is deterministic grammar over *your* board and
sample names — never an LLM guessing.

### Workflow examples

| You say | What RITA does |
|---|---|
| **"Rita, please build me an example for MSPI that communicates with a PSRAM on MSPI0 in hex mode."** | Scaffolds a new application in `<workspace>\applications\`, briefing the coding agent with the shipped MSPI + PSRAM recipes (devicetree overlay with `mspi-io-mode`, `CONFIG_MSPI`/memc Kconfig, timing notes) → CERBERUS static check → finds or writes the verifying test → builds → runs twister on `native_sim` → reports. Every patch re-passes the static gate first. |
| "build blinky" | Resolves `samples/basic/blinky` from the index, builds, twister-gates it. |
| "flash blinky to the apollo510" | Sim-first pipeline; the device step stays **blocked** until the bench milestone — RITA says so instead of pretending. |
| "run the samples" / "report on the last run" | Pipeline verbs, same gates. |
| "tell me about the apollo510" | Answers from your synced board data: vendor, arch, twister platform, supported peripherals, connected port. |
| "what zephyr version are we on" | Answers from your install's `zephyr/VERSION`. |
| "how do I add a devicetree overlay" | Answers from the shipped Zephyr knowledge pack (each topic cites the official docs). |
| "your name is now Vera" | Renames the assistant — it's config, persisted, and the wake word follows. |

### The two panes and the two buttons

Conversation stays in the transcript — **at most two spoken sentences per
reply**. Code, diffs, logs, and reports always land in the monospace
screen pane below; RITA never reads code aloud. The **Pause** and
**Resume/Stop** buttons are always visible: Pause halts speech instantly
and suspends the running task at the next safe checkpoint ("pausing after
current step…" → "paused" — flashing and measurements are never
interrupted mid-operation); Resume continues exactly where it stopped (a
task paused after its build goes straight into twister, no rebuild); Stop
cancels at a safe boundary and reports what completed.

## 5. Where things land

| Path | Contents |
|---|---|
| `%USERPROFILE%\.rita\config` | your settings (assistant name, workspace, budgets) |
| `%USERPROFILE%\.rita\boards.json` + `verification-index.json` | synced facts about *your* workspace |
| `%USERPROFILE%\.rita\modules\` | installed capability modules (versioned; updates drop a folder and flip `current`) |
| `%USERPROFILE%\.rita\work\task-N\` | each task's build output — `twister.json` in there is the gate verdict |
| `<workspace>\applications\` | applications RITA scaffolds for you (configurable in Settings) |

## 6. What's deliberately not on yet

The **device tier** (real flashing, on-board twister, power measurement)
is blocked until the bench milestone: twister `hello_world` with
`--device-testing` passing on the real EVB, validating flash + serial +
harness in one shot. Until then RITA reports the device step as blocked —
it is never faked green. Cerberus and Joulescope modules are honest stubs
for the same reason.

## 7. Troubleshooting

- **Status bar says "claude CLI missing"** — install/log in to Claude
  Code; RITA finds it on PATH.
- **Sync finds 0 boards** — you probably picked a folder above or below
  the workspace; choose the folder that contains `zephyr/` (RITA also
  accepts `zephyr/` itself).
- **"SDK not found"** — set `ZEPHYR_SDK_INSTALL_DIR` or install the SDK
  in a standard location (`%PROGRAMFILES%`, home dir).
- **No speech / no mic** — the Voice component needs an output device and
  microphone; the first spoken turn downloads the Whisper model (one-time,
  needs network). Voice can stay off — everything works typed.
- **A work request says "that pipeline isn't wired up yet" or asks for
  sync** — sync a workspace first (Workspace page).
- **A task ends "retries exhausted"** — that's RITA stopping at its patch
  budget and telling you, with the failing log in the screen pane. Raise
  the budget in Settings if you want more attempts.

## First smoke test on your machine (5 minutes)

1. Install → launch → status bar shows workspace/Zephyr/SDK/claude. 
2. Workspace page → point at `C:\zephyrproject` → Sync → boards + suites counted.
3. Type `"tell me about the apollo510"` → real board facts.
4. Type `"build blinky"` → watch the task run; green report lands in the transcript, details in the screen pane.
5. Click **Pause** mid-build → "pausing after current step…" → **Resume** → completes without rebuilding.
