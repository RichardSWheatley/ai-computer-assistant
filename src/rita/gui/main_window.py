"""RitaWindow: the native shell around the headless presenter.

Layout: sidebar (Chat / Projects / Workspace / Modules / Settings) +
stacked pages.
The chat page shows the two output channels as two visible panes —
transcript (speech) and a monospace screen pane (code/diffs/logs) — with
the prompt bar below and the persistent PAUSE / RESUME / STOP control bar
(Fix 4's two buttons) always in reach. All presenter callbacks hop onto
the Qt thread via signals.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QPlainTextEdit,
                               QPushButton, QSplitter, QStackedWidget,
                               QStatusBar, QTextEdit, QVBoxLayout, QWidget)

from .presenter import GuiPresenter, StatusInfo, TaskSnapshot
from .theme import ACCENT, TEXT_DIM


class RitaWindow(QMainWindow):
    sig_user = Signal(str)
    sig_reply = Signal(str)
    sig_screen = Signal(str)
    sig_task = Signal(object)
    sig_status = Signal(object)

    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        name = presenter.sup.cfg.assistant_name
        self.setWindowTitle(f"RITA — {name}")
        self.resize(1180, 760)

        # Presenter callbacks -> Qt signals (thread-safe hop).
        presenter.on_user = self.sig_user.emit
        presenter.on_reply = self.sig_reply.emit
        presenter.on_screen = self.sig_screen.emit
        presenter.on_task = self.sig_task.emit
        presenter.on_status = self.sig_status.emit
        self.sig_user.connect(lambda t: self._transcript_add("You", t))
        self.sig_reply.connect(lambda t: self._transcript_add(name, t))
        self.sig_screen.connect(self._screen_add)
        self.sig_task.connect(self._task_update)
        self.sig_status.connect(self._status_update)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self._build_chat_page())
        from .projects_page import ProjectsPage
        from .workspace_page import WorkspacePage
        from .modules_page import ModulesPage
        from .settings_page import SettingsPage
        self.projects_page = ProjectsPage(presenter)
        self.workspace_page = WorkspacePage(presenter)
        self.modules_page = ModulesPage(presenter)
        self.settings_page = SettingsPage(presenter)
        self.pages.addWidget(self.projects_page)
        self.pages.addWidget(self.workspace_page)
        self.pages.addWidget(self.modules_page)
        self.pages.addWidget(self.settings_page)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._status_update(presenter.status())

        # First run: no workspace yet -> land on the Workspace page.
        if not presenter.sup.cfg.workspace:
            self._nav_buttons[2].click()

        # Voice was left on last session: start listening right away.
        if presenter.sup.cfg.voice_enabled:
            presenter.start_voice()

    # --- chrome ---------------------------------------------------------------

    def _build_sidebar(self) -> QWidget:
        bar = QWidget(objectName="sidebar")
        bar.setFixedWidth(190)
        v = QVBoxLayout(bar)
        v.setContentsMargins(10, 16, 10, 16)
        title = QLabel("RITA", objectName="title")
        subtitle = QLabel("Routing · Iteration\nTesting · Automation",
                          objectName="dim")
        v.addWidget(title)
        v.addWidget(subtitle)
        v.addSpacing(18)
        self._nav_buttons: list[QPushButton] = []
        group = QButtonGroup(bar)
        for i, label in enumerate(("Chat", "Projects", "Workspace", "Modules",
                                   "Settings")):
            b = QPushButton(label, objectName="navButton")
            b.setCheckable(True)
            b.clicked.connect(lambda _=False, idx=i: self.pages.setCurrentIndex(idx))
            group.addButton(b)
            v.addWidget(b)
            self._nav_buttons.append(b)
        self._nav_buttons[0].setChecked(True)
        v.addStretch(1)
        return bar

    def _build_chat_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)

        split = QSplitter(Qt.Orientation.Vertical)
        self.transcript = QTextEdit(readOnly=True)
        self.transcript.setPlaceholderText(
            "Say or type a command — put commands in quotes if you like.")
        self.screen_pane = QPlainTextEdit(objectName="screenPane", readOnly=True)
        self.screen_pane.setPlaceholderText(
            "Code, diffs, logs, and reports land here — never in speech.")
        split.addWidget(self.transcript)
        split.addWidget(self.screen_pane)
        split.setSizes([420, 220])
        v.addWidget(split, 1)

        # The persistent control bar (Fix 4's two buttons).
        controls = QHBoxLayout()
        self.task_label = QLabel("", objectName="dim")
        self.pause_btn = QPushButton("Pause", objectName="pause")
        self.resume_btn = QPushButton("Resume")
        self.stop_btn = QPushButton("Stop", objectName="stop")
        self.pause_btn.clicked.connect(self.presenter.pause)
        self.resume_btn.clicked.connect(self.presenter.resume)
        self.stop_btn.clicked.connect(self.presenter.stop)
        controls.addWidget(self.task_label, 1)
        controls.addWidget(self.pause_btn)
        controls.addWidget(self.resume_btn)
        controls.addWidget(self.stop_btn)
        v.addLayout(controls)

        prompt = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText('e.g.  "Rita, build blinky for the apollo510"')
        self.prompt.returnPressed.connect(self._send)
        send = QPushButton("Send", objectName="primary")
        send.clicked.connect(self._send)
        prompt.addWidget(self.prompt, 1)
        prompt.addWidget(send)
        v.addLayout(prompt)
        return page

    # --- slots ----------------------------------------------------------------

    def _send(self) -> None:
        text = self.prompt.text()
        self.prompt.clear()
        self.presenter.submit_text(text)

    def _transcript_add(self, who: str, text: str) -> None:
        from html import escape

        color = ACCENT if who != "You" else TEXT_DIM
        # Escape: this pane renders HTML, so an error naming <module> or a
        # diff containing <stdio.h> would otherwise vanish silently.
        body = escape(text).replace("\n", "<br/>")
        self.transcript.append(
            f'<p style="margin:6px 0"><b style="color:{color}">{escape(who)}'
            f"</b><br/>{body}</p>")

    def _screen_add(self, text: str) -> None:
        self.screen_pane.appendPlainText(text + "\n")

    def _task_update(self, snap: TaskSnapshot) -> None:
        pretty = {"PAUSING": "pausing after current step…",
                  "PAUSED": "paused",
                  "STOPPING": "stopping at the next safe point…",
                  "RUNNING": "running", "DONE": "done",
                  "STOPPED": "stopped", "FAILED": "failed"}
        self.task_label.setText(f"{snap.name}: {pretty.get(snap.state, snap.state)}")

    def _status_update(self, st: StatusInfo) -> None:
        ws = st.workspace or "no workspace — set one on the Workspace page"
        zephyr = f"Zephyr {st.zephyr_version}" if st.zephyr_version else "Zephyr ?"
        sdk = f"SDK {st.sdk_version}" if st.sdk_version else "SDK not found"
        coder = "coder ✓" if st.coder_cli else "coder not configured"
        self.status_bar.showMessage(
            f"{ws}   ·   {zephyr}   ·   {sdk}   ·   {st.modules} modules   ·   {coder}")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.presenter.close()
        super().closeEvent(event)
