"""Render REAL app screenshots into docs/img/ — reproducibly.

The pictures in the README are grabs of the actual GUI (offscreen Qt
render, isolated RITA_HOME, fixture workspace), not mockups. Re-run
after a GUI change:

    python packaging/screenshots.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RITA_HOME"] = tempfile.mkdtemp(prefix="rita-shots-")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
OUT = REPO / "docs" / "img"
WS = REPO / "tests" / "fixtures" / "zephyr_ws"


def main() -> None:
    from PySide6.QtWidgets import QApplication

    from rita.config import RitaConfig
    from rita.gui.main_window import RitaWindow
    from rita.gui.presenter import GuiPresenter
    from rita.gui.theme import QSS
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    OUT.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         auto_setup=False),
                     config_path=Path(os.environ["RITA_HOME"]) / "config",
                     tts=FakeTTS(),
                     workdir=Path(os.environ["RITA_HOME"]) / "work")
    p = GuiPresenter(sup)
    w = RitaWindow(p)
    w.resize(1180, 760)

    # Seed the first chat with a real-looking exchange (actual product
    # phrasing) so the shot shows the two output channels.
    tab = w.chat_tabs.widget(0)
    tab.transcript_add("You", "Rita, build hello world for the qemu_x86")
    tab.transcript_add(
        "Rita", "Started build for qemu_x86. Say pause or stop any time; "
                "I'll report when the gates finish.")
    tab.transcript_add(
        "Rita", "Task task-1 finished: green — CERBERUS clean, 2 unit "
                "tests passed under QEMU, twister suite passed.")
    tab.screen_add("[STATIC] green: CERBERUS scan clean (94 checks)\n"
                   "[UNIT_TEST] green: 2 passed under qemu-system-arm\n"
                   "[FINAL_TEST] green: twister sample.basic.helloworld")

    # A second tab bound to its own repo shows per-chat workspaces.
    other = Path(os.environ["RITA_HOME"]) / "sensor-firmware"
    other.mkdir(parents=True, exist_ok=True)
    w._add_chat_tab_clicked()
    second = w.chat_tabs.widget(1)
    p.set_active_chat(second.chat_id)
    sup.bind_chat(str(other))
    second.refresh_workspace()
    second.transcript_add(
        "Rita", f"This chat now works in {other}. Say sync to map it, and "
                f"everything I learn here stays with this chat.")
    w.chat_tabs.setCurrentIndex(0)

    # Offscreen still needs show() + a few event passes for layout.
    w.show()
    for _ in range(5):
        app.processEvents()
    w.grab().save(str(OUT / "chat-tabs.png"))

    for idx, name in ((3, "modules.png"), (4, "settings.png")):
        w.pages.setCurrentIndex(idx)
        app.processEvents()
        w.grab().save(str(OUT / name))
    print(f"wrote {', '.join(x.name for x in sorted(OUT.glob('*.png')))} "
          f"to {OUT}")
    w.close()
    p.close()


if __name__ == "__main__":
    main()
