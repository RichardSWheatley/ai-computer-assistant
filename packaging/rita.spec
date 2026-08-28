# PyInstaller spec: one bundle, two executables.
#   RitaApp.exe  - windowed GUI (the app users launch)
#   rita.exe     - console CLI + module host (`rita.exe module-run <name>`)
# Build (Windows):  pyinstaller packaging/rita.spec
# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

SRC = Path(SPECPATH).parent / "src"

datas = [
    (str(SRC / "rita/firmware/data/boards.seed.json"), "rita/firmware/data"),
    (str(SRC / "rita/firmware/data/knowledge"), "rita/firmware/data/knowledge"),
]

hiddenimports = [
    "rita.gui.app", "rita.gui.main_window", "rita.gui.workspace_page",
    "rita.gui.projects_page", "rita.gui.modules_page", "rita.gui.settings_page",
    "rita.modules_impl.voice_in", "rita.modules_impl.voice_out",
    "rita.modules_impl.zephyr_runner", "rita.modules_impl.coder_worker",
    "rita.modules_impl.scaffold", "rita.modules_impl.cerberus",
    "rita.modules_impl.joulescope",
    "rita.mcpserver.server",
]

gui_a = Analysis(
    [str(Path(SPECPATH) / "launch_gui.py")],
    pathex=[str(SRC)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch"],
)
cli_a = Analysis(
    [str(Path(SPECPATH) / "launch_cli.py")],
    pathex=[str(SRC)],
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
