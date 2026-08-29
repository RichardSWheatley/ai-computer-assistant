"""RITA tests her own GUI: a scripted user session against the REAL app.

Launches the actual RitaWindow (offscreen Qt) and drives it the way a
person does — clicks every navigation page, presses every button, types
commands, opens tabs, toggles the mic, saves settings — failing loudly
on any uncaught exception, any dead control, or any page that doesn't
respond. Screenshots of every step land in the output directory for
eyeball review. Runs before every release, locally and in CI (on the
Windows runner too):

    python packaging/gui_walk.py [--out DIR]
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["RITA_HOME"] = tempfile.mkdtemp(prefix="rita-walk-")

# Windows consoles are cp1252: printing ▸/✗ must never crash the very
# harness that exists to catch crashes (the rita CLI does the same).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(errors="replace")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
WS = REPO / "tests" / "fixtures" / "zephyr_ws"

_failures: list[str] = []
_steps: list[str] = []


def step(name: str) -> None:
    _steps.append(name)
    print(f"  ▸ {name}")


def fail(msg: str) -> None:
    _failures.append(msg)
    print(f"  ✗ {msg}")


def _excepthook(exc_type, exc, tb):
    fail(f"uncaught exception: {exc_type.__name__}: {exc}\n"
         + "".join(traceback.format_tb(tb))[-500:])


def pump(app, seconds: float = 0.15) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)


def wait_for(app, pred, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if pred():
            return True
        time.sleep(0.02)
    return False


def main(out_dir: str | None = None) -> int:
    sys.excepthook = _excepthook
    out = Path(out_dir or (REPO / "build" / "gui-walk"))
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtWidgets import QApplication

    from rita.config import RitaConfig
    from rita.firmware.cerberus_setup import InstallResult
    from rita.gui.main_window import RitaWindow
    from rita.gui.presenter import GuiPresenter
    from rita.gui.theme import QSS
    from rita.routing.model import Utterance
    from rita.supervisor import Supervisor
    from rita.voice.mic import FakeRecorder
    from rita.voice.tts import FakeTTS

    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)

    # Real supervisor, fixture workspace; auto-setup off (the walk
    # exercises controls, not downloads).
    home = Path(os.environ["RITA_HOME"])
    sup = Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                         auto_setup=False),
                     config_path=home / "config", tts=FakeTTS(),
                     workdir=home / "work")

    class WalkSTT:
        def transcribe(self, wav):
            return ""

    p = GuiPresenter(sup, poll_interval=0.02,
                     voice_backends=lambda: (FakeRecorder(), WalkSTT(),
                                             None))
    w = RitaWindow(p)
    w.resize(1180, 760)
    w.show()
    pump(app)

    # Spy on REPLY events: waiting for "the transcript grew" races the
    # user's own echo (it grew the transcript first on the slower
    # Windows runner) — assertions must run against RITA's reply text.
    replies: list[str] = []
    _orig_chat_event = p.on_chat_event

    def _spy(chat, kind, text):
        if kind == "reply":
            replies.append(text)
        _orig_chat_event(chat, kind, text)

    p.on_chat_event = _spy

    def shot(name: str) -> None:
        w.grab().save(str(out / f"{name}.png"))

    # --- 1. every navigation page opens -----------------------------------
    for idx, name in enumerate(("chat", "projects", "modules",
                                "settings")):
        step(f"open page: {name}")
        w._nav_buttons[idx].click()
        pump(app)
        if w.pages.currentIndex() != idx:
            fail(f"nav button {name} did not switch the page")
        shot(f"1-page-{name}")

    # --- 2. chat: type commands, get replies -------------------------------
    w._nav_buttons[0].click()
    pump(app)
    tab = w.chat_tabs.widget(0)
    for phrase, expects in (
            ("status", ("nothing is running", "still on it")),
            ("list your toolsets", ("toolset",)),
            ("what did you learn", ("learn", "facts")),
            ("tell me about the apollo510", ("apollo",)),
    ):
        step(f"type: {phrase!r}")
        before = len(replies)
        tab.prompt.setText(phrase)
        tab._send()
        if not wait_for(app, lambda: len(replies) > before):
            fail(f"no reply arrived for {phrase!r}")
            continue
        reply = replies[-1].lower()
        if not any(e in reply for e in expects):
            fail(f"reply to {phrase!r} lacks any of {expects}: "
                 f"{reply[:120]!r}")
    shot("2-chat-replies")

    # --- 3. tabs: open, isolate, bind --------------------------------------
    step("open a second chat tab")
    w._add_chat_tab_clicked()
    pump(app)
    if w.chat_tabs.count() < 2:
        fail("+ New chat did not open a tab")
    second = w.chat_tabs.widget(1)
    w.chat_tabs.setCurrentIndex(1)
    pump(app)
    repo = Path(os.environ["RITA_HOME"]) / "other-repo"
    repo.mkdir(exist_ok=True)
    step("bind the second tab to its own repo")
    second.bind_edit.setText(str(repo))
    second._bind()
    if not wait_for(app, lambda: str(repo) in second.workspace_label.text()):
        fail("binding a repo did not update the tab's workspace label")
    first = w.chat_tabs.widget(0)
    if str(repo) in first.workspace_label.text():
        fail("tab 1 leaked tab 2's workspace binding")
    shot("3-tabs")

    step("use the folder picker on the bind field")
    from rita.gui import pickers as _pickers

    picked = Path(os.environ["RITA_HOME"]) / "picked-repo"
    picked.mkdir(exist_ok=True)
    _orig_dlg = _pickers.QFileDialog.getExistingDirectory
    _pickers.QFileDialog.getExistingDirectory = staticmethod(
        lambda *a, **k: str(picked))
    try:
        second.bind_pick.click()
        pump(app)
        if second.bind_edit.text() != str(picked):
            fail("the bind folder picker did not fill the field")
    finally:
        _pickers.QFileDialog.getExistingDirectory = _orig_dlg

    step("Sync from the chat tab strip (no Workspace page any more)")
    before = len(replies)
    first = w.chat_tabs.widget(0)
    w.chat_tabs.setCurrentIndex(0)
    pump(app)
    first.sync_btn.click()
    if not wait_for(app, lambda: any("board" in r.lower()
                                     for r in replies[before:]), timeout=30):
        fail("the tab Sync button produced no boards/suites reply")
    shot("3b-tab-sync")

    step("close the second tab (the last one must survive)")
    w._close_chat_tab(1)
    pump(app)
    if w.chat_tabs.count() != 1:
        fail("closing the second tab did not remove it")
    w._close_chat_tab(0)
    if w.chat_tabs.count() != 1:
        fail("the last tab must never close")

    # --- 4. the mic button -------------------------------------------------
    w.chat_tabs.setCurrentIndex(0)
    pump(app)
    step("toggle the mic on")
    tab.mic_btn.setChecked(True)
    tab._mic_toggled()
    if not wait_for(app, lambda: "listening" in tab.mic_btn.text().lower()):
        fail("mic on did not switch the button to Listening…")
    step("Send turns the mic off")
    tab.prompt.setText("status")
    tab._send()
    if not wait_for(app, lambda: not p.voice_active):
        fail("Send did not stop the microphone")
    if not wait_for(app, lambda: "voice" in tab.mic_btn.text().lower()):
        fail("mic button did not return to Voice after Send")
    shot("4-mic")

    # --- 5. task controls: a live task, status, pause/stop ------------------
    import threading

    gate = threading.Event()

    def slow_task(ctl):
        ctl.checkpoint("RESOLVE")
        gate.wait(10)
        ctl.checkpoint("BUILD")
        return "walked"

    step("run a task; stage progress must stream")
    sup.manager.submit("walk task", slow_task)
    if not wait_for(app, lambda: "RESOLVE" in tab.screen_pane.toPlainText()):
        fail("stage progress did not stream into the screen pane")
    tab.prompt.setText("are you still working")
    tab._send()
    if not wait_for(app, lambda: "walk task"
                    in tab.transcript.toPlainText()):
        fail("'are you still working' did not report the live task")

    step("the Status button answers with the task's age")
    before = len(replies)
    tab.status_btn.click()
    if not wait_for(app, lambda: any("still on it" in r and "for "
                                     in r for r in replies[before:])):
        fail("the Status button did not report the live task with its age")
    gate.set()
    shot("5-progress")

    # --- 6. modules page: buttons show busy + results append ---------------
    w._nav_buttons[2].click()
    pump(app)
    mp = w.modules_page
    step("modules install button shows Installing… and reports")

    class R:
        ok = True
        detail = "walked install ok"

    mp._run_install("WALK", mp.unity_btn, lambda: R(), "walking…")
    if mp.unity_btn.isEnabled():
        fail("install button did not disable while running")
    if not wait_for(app, lambda: "walked install ok"
                    in mp.log.toPlainText()):
        fail("install result did not append to the modules log")
    if not wait_for(app, lambda: mp.unity_btn.isEnabled()):
        fail("install button did not re-enable")
    shot("6-modules")

    # --- 7. the intelligent manager routes a modify request -----------------
    import json as _json

    from rita.firmware.coder import FakeCoder

    step("the manager decides a board-less modify request")
    sup.cfg.applications_dir = str(home / "apps")
    sup._coder = FakeCoder(completions=[_json.dumps({
        "action": "modify", "board": "qemu_x86",
        "sample": "sample.basic.blinky",
        "goal": "add a log line to blinky",
        "why": "qemu_x86 runs on this machine"})])
    w.chat_tabs.setCurrentIndex(0)
    pump(app)
    before = len(replies)
    tab.prompt.setText("add a log line to the blinky example")
    tab._send()
    # The decision reply may be followed quickly by the task's own
    # announcements — find it among the replies, don't race the newest.
    def _decision():
        return next((r.lower() for r in replies[before:]
                     if "read that as" in r.lower()), None)

    if not wait_for(app, lambda: _decision() is not None):
        fail("the manager's decision never came back")
    else:
        decided = _decision()
        if "qemu_x86" not in decided:
            fail(f"decision reply lacks the board: {decided[:120]!r}")
        if "copy" not in decided:
            fail("the modify reply does not promise a copy")
    p.stop()          # the pipeline behind it isn't the walk's business
    pump(app, 0.3)
    shot("7-manager")

    # --- 8. settings: change + save round-trips ----------------------------
    w._nav_buttons[3].click()
    pump(app)
    sp = w.settings_page
    step("settings save round-trips")
    sp.awake_secs.setValue(90)
    sp._save()
    pump(app)
    from rita.config import load_rita_config

    back = load_rita_config(home / "config")
    if back.voice_awake_seconds != 90:
        fail("settings Save did not persist the awake window")
    shot("8-settings")

    # --- verdict ------------------------------------------------------------
    w.close()
    p.close()
    pump(app, 0.1)
    print(f"\nGUI walk: {len(_steps)} steps, {len(_failures)} failures; "
          f"screenshots in {out}")
    if _failures:
        for f in _failures:
            print(f"  FAIL: {f}")
        return 1
    print("GUI walk passed — every page opened, every control answered.")
    return 0


if __name__ == "__main__":
    out = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None
    raise SystemExit(main(out))
