# PyInstaller spec: one bundle, two executables.
#   RitaApp.exe  - windowed GUI (the app users launch)
#   rita.exe     - console CLI + module host (`rita.exe module-run <name>`)
# Build (Windows):  pyinstaller packaging/rita.spec
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

SRC = Path(SPECPATH).parent / "src"


def bundle(pkg):
    """Collect a package PyInstaller cannot see: `mcp` is imported inside a
    function (so a frozen `rita.exe mcp-serve` would die), and the voice
    runtime ships native libraries its import needs."""
    try:
        return collect_all(pkg)
    except Exception:
        return [], [], []      # not installed in this build environment


extra_datas, extra_binaries, extra_hidden = [], [], []
for _pkg in ("mcp", "sounddevice", "faster_whisper", "ctranslate2",
             "huggingface_hub", "tokenizers", "pyttsx3", "certifi"):
    _d, _b, _h = bundle(_pkg)
    extra_datas += _d
    extra_binaries += _b
    extra_hidden += _h

datas = [
    (str(SRC / "rita/firmware/data/boards.seed.json"), "rita/firmware/data"),
    (str(SRC / "rita/firmware/data/knowledge"), "rita/firmware/data/knowledge"),
] + extra_datas

hiddenimports = [
    "rita.gui.app", "rita.gui.main_window", "rita.gui.workspace_page",
    "rita.gui.projects_page", "rita.gui.modules_page", "rita.gui.settings_page",
    "rita.modules_impl.voice_in", "rita.modules_impl.voice_out",
    "rita.modules_impl.zephyr_runner", "rita.modules_impl.coder_worker",
    "rita.modules_impl.scaffold", "rita.modules_impl.cerberus",
    "rita.modules_impl.joulescope",
    "rita.mcpserver.server", "rita.diagnostics",
] + extra_hidden

gui_a = Analysis(
    [str(Path(SPECPATH) / "launch_gui.py")],
    pathex=[str(SRC)],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch"],
)
cli_a = Analysis(
    [str(Path(SPECPATH) / "launch_cli.py")],
    pathex=[str(SRC)],
    binaries=extra_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["PySide6", "torch"],
)

MERGE((gui_a, "RitaApp", "RitaApp"), (cli_a, "rita", "rita"))

gui_pyz = PYZ(gui_a.pure)
gui_exe = EXE(gui_pyz, gui_a.scripts, [], exclude_binaries=True,
              name="RitaApp", console=False)
cli_pyz = PYZ(cli_a.pure)
cli_exe = EXE(cli_pyz, cli_a.scripts, [], exclude_binaries=True,
              name="rita", console=True)

coll = COLLECT(gui_exe, gui_a.binaries, gui_a.datas,
               cli_exe, cli_a.binaries, cli_a.datas,
               name="RITA")
