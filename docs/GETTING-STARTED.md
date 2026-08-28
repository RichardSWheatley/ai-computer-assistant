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
| Zephyr SDK installed | real-board builds **and** the unit-tier C compiler (the SDK ships gcc by default) | RITA's status bar shows "SDK \<version\>" when found |
| A coding-agent CLI | any installed CLI that takes a prompt and can edit files; RITA drives it for scaffolding, test-writing, and patches. Enter its command on the **Settings** page ("Coding agent") | RITA's status bar shows "coder ✓" |

Without a coding agent configured, RITA still routes, syncs, indexes, and
answers questions — it just can't author or patch code, and says so.

## 2. Install RITA

**Option 1 — the installer (recommended).** Download
`RITA-Setup-<version>.exe` (built by the `windows-installer` GitHub
Actions workflow — run it from the repo's Actions tab and grab the
artifact, or ask for a release build). Run it and pick your components:

- **Core + GUI** (always installed) — the app itself.
- **Voice** — wake-word listening and speech output modules.
- **Workspace MCP** — the local MCP server the coding agent uses to see
  your workspace (recommended: keep it).
- **Modules** — zephyr-runner (build/test/flash), coder-worker,
  scaffold, **CERBERUS** (the static gate — the installer clones
  github.com/RichardSWheatley/cerberus onto your machine; needs git on
  PATH), and a joulescope placeholder (honest stub until the bench
  milestone).

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
you like; RITA strips them and routes the contents. Turn on **Settings →
Enable voice** and RITA listens in the app: say **"hello Rita"** (or just
"Rita") to wake her, speak your command, and she answers out loud (at
most two sentences — code and logs stay on screen). Say "stop listening"
to put her back to sleep; the mic keeps waiting for the wake word. The
setting persists and re-arms on launch. Typed input never needs a wake
word. Routing is deterministic grammar over *your* board and
sample names — never an LLM guessing.

### Workflow examples

| You say | What RITA does |
|---|---|
| **"Rita, please build me an example for MSPI that communicates with a PSRAM on MSPI0 in hex mode."** | Codes the application in `<workspace>\applications\` (every function restricts or validates its input/output parameters) → **CERBERUS** static check → **unit tests**: every single function gets host-run Unity tests of its parameters — valid, boundary, invalid — all green before moving on → iterates as needed (every patch re-passes every gate) → **final test**: the relevant Zephyr samples/tests under twister → reports. |
| "build blinky" | Resolves `samples/basic/blinky` from the index, builds, twister-gates it. |
| "flash blinky to the apollo510" | Sim-first pipeline; the device step stays **blocked** until the bench milestone — RITA says so instead of pretending. |
| "run the samples" / "report on the last run" | Pipeline verbs, same gates. |
| "tell me about the apollo510" | Answers from your synced board data: vendor, arch, twister platform, supported peripherals, connected port. |
| "what zephyr version are we on" | Answers from your install's `zephyr/VERSION`. |
| "how do I add a devicetree overlay" | Answers from the shipped Zephyr knowledge pack (each topic cites the official docs). |
| "your name is now Vera" | Renames the assistant — it's config, persisted, and the wake word follows. |

### Handing off whole projects

The **Projects** page (or `"start a project: …"` / `"take on …"` in
chat) hands RITA a goal instead of a single command:

| You say | What RITA does |
|---|---|
| "start a project: build blinky for the apollo510" | The goal already routes as one command — RITA runs it herself, **no AI planning involved**. |
| "start a project: bring up the mspi psram example and characterize it" | An AI gets **one bounded call** to draft the item list — titles, commands, dependencies, estimates, milestones — as **pure data in RITA's own command grammar**. RITA validates every item by routing it, then **executes the items herself**, dependency-ordered, each work item through the full gates (CERBERUS → unit tests → final test). The AI schedules nothing and executes nothing. |
| "how is the project going" | Live status from the persisted project: items done, running, blocked, waiting on you. |

An item the AI phrases outside RITA's grammar is flagged **needs you** —
kept visible on the Projects page, never guessed at. An item whose
dependency failed is blocked by cascade and reported. Every transition is
persisted to `~\.rita\projects.json`, so a restart shows exactly where
things stand, and Pause/Stop work between items just like within one.

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
| `%USERPROFILE%\.rita\projects.json` | handed-off projects: every item's status, saved on every transition |
| `%USERPROFILE%\.rita\work\proj-N\item-M\` | per-item build output for project work items |
| `<workspace>\applications\` | applications RITA scaffolds for you (configurable in Settings) |

## 6. The gates: CERBERUS and per-function unit tests

Every piece of code the coding agent produces passes CERBERUS before it may build,
and every patch re-passes it. The default is CERBERUS's Head 1 — 94
deterministic MISRA C:2012 / CERT C checks, free, **no API key needed**.
If the installer's CERBERUS component didn't run (no git at install
time), use **Modules → Install / update CERBERUS** in the app. Settings
offers deep mode (`analyze`: the Oracle LLM head — the coding agent working inside
CERBERUS — plus Unity test generation), which uses your API key via
CERBERUS's own environment variables. Without CERBERUS installed the
static stage reports itself as skipped — visibly, never silently.

After CERBERUS, **every single function RITA writes gets unit-tested for
its input and output parameters** — valid values, boundaries, and invalid
values the function must reject (the coding contract requires every
function to restrict or validate its parameters before executing). These
are host-run **Unity** tests (the framework is cloned at install, like
CERBERUS). The compiler comes from your PATH when one is there, otherwise
**from your Zephyr SDK** — the SDK ships gcc by default (its LLVM bundle
is detected too), so no extra install is needed. A deterministic scan
fails the stage naming any function without tests.
Only when CERBERUS and the unit tier are both green does the **final
test** run: the relevant Zephyr samples/tests under twister.

## 7. What's deliberately not on yet

The **device tier** (real flashing, on-board twister, power measurement)
is blocked until the bench milestone: twister `hello_world` with
`--device-testing` passing on the real EVB, validating flash + serial +
harness in one shot. Until then RITA reports the device step as blocked —
it is never faked green. The Joulescope module stays an honest stub for
the same reason.

## 8. Troubleshooting

- **Status bar says "coder not configured"** — enter your coding-agent
  CLI's command on the Settings page ("Coding agent") and make sure that
  executable is installed and on PATH. RITA never assumes a vendor.
- **A work request answers "No coding agent is configured"** — same fix:
  Settings → Coding agent.
- **Sync finds 0 boards** — you probably picked a folder above or below
  the workspace; choose the folder that contains `zephyr/` (RITA also
  accepts `zephyr/` itself).
- **"SDK not found"** — set `ZEPHYR_SDK_INSTALL_DIR` or install the SDK
  in a standard location (`%PROGRAMFILES%`, home dir).
- **No speech / no mic** — the Voice component needs an output device and
  microphone; the first spoken turn downloads the Whisper model (one-time,
  needs network). If deps are missing, enabling voice tells you exactly
  which one. Voice can stay off — everything works typed.
- **You should NOT need to re-sync or reconfigure after an update** —
  your settings and synced workspace data live in `%USERPROFILE%\.rita`,
  which installs and uninstalls never touch. Run the new Setup right over
  the old install (no uninstall needed). If an old build corrupted the
  config, RITA now backs it up as `config.bad` and starts clean once.
- **A work request says "that pipeline isn't wired up yet" or asks for
  sync** — sync a workspace first (Workspace page).
- **A task ends "retries exhausted"** — that's RITA stopping at its patch
  budget and telling you, with the failing log in the screen pane. Raise
  the budget in Settings if you want more attempts.

## First smoke test on your machine (5 minutes)

1. Install → launch → status bar shows workspace/Zephyr/SDK/coder. 
2. Workspace page → point at `C:\zephyrproject` → Sync → boards + suites counted.
3. Type `"tell me about the apollo510"` → real board facts.
4. Type `"build blinky"` → watch the task run; green report lands in the transcript, details in the screen pane.
5. Click **Pause** mid-build → "pausing after current step…" → **Resume** → completes without rebuilding.
