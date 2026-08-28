# Spec: The modular installer

## Problem

RITA installs like a normal app: a Windows installer with **selectable
components**, a Start-menu shortcut that launches the GUI, and no command
line anywhere in the user path. (macOS/Linux packaging follows later.)

## Design

### Bundle (`packaging/rita.spec`, PyInstaller)

Two executables from one bundle:
- **`RitaApp.exe`** — windowed, launches the GUI (`rita.gui.app:main`).
- **`rita.exe`** — console, the developer CLI **and the module host**
  (modules are spawned as `rita.exe module-run <name>`).

Bundled data: the board seed and the Zephyr knowledge pack
(`rita/firmware/data/**`). PySide6 is collected; heavy optional backends
(voice models, torch) are not bundled — voice deps install as an installer
component and models download on first use.

### `module-run` (the packaged module entrypoint)

A frozen bundle has no `python -m`, so manifests cannot use it. New CLI
`rita module-run <name>` execs the named module's serve loop
(`rita.modules_impl.<name>`), and `modules install` writes entrypoints that
work in both worlds:

- frozen (`sys.frozen`): `[sys.executable, "module-run", "<name>"]`
- dev/venv: `[sys.executable, "-m", "rita", "module-run", "<name>"]`

Same registry, same manifests, same drain/update semantics either way.

### Installer (`packaging/installer.iss`, Inno Setup — modular)

Components:
- **Core + GUI** (required): the bundle, shortcuts, file layout.
- **Voice** (optional): marks voice modules for registration.
- **Workspace MCP** (optional): marks the MCP serving component.
- **Capability modules** (individually selectable): zephyr-runner,
  coder-worker, scaffold, voice-in, voice-out, cerberus, joulescope.

Post-install, the installer runs
`rita.exe modules install --only <selected>` — module **registration is
manifest-writing** into `%USERPROFILE%\.rita\modules\` (the registry's
native update mechanism: drop a version dir, point `current`). Uninstall
removes the app but leaves `~/.rita` user data (documented).

### CI (`.github/workflows/installer.yml`)

A `windows-latest` job (manual dispatch + tags) builds the bundle with
PyInstaller, compiles the installer with Inno Setup, and uploads
`RITA-Setup-<version>.exe` as an artifact — so a built installer is
downloadable without a local build. `packaging/build.ps1` is the same
recipe for a one-command local build on Windows.

### Honesty

This repo's CI authors and builds the installer; the final smoke run
(install → point at the workspace → build blinky) happens on a real
Windows machine — checklist in GETTING-STARTED.

## Acceptance criteria (each is a test, headless where possible)

- `rita module-run cerberus` speaks the module protocol end-to-end as a
  real child process (hello handshake + honest stub reply).
- `modules install --only …` writes manifests for exactly the selected
  modules, with interpreter-correct entrypoints; a registry launch of one
  succeeds.
- The PyInstaller spec and the .iss reference only files that exist, and
  the .iss component list covers every shipped module name.
- The CI workflow parses (yaml) and targets windows-latest with artifact
  upload.
