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
                               QStatusBar, QTabWidget, QTextEdit,
                               QToolButton, QVBoxLayout, QWidget)

from .presenter import GuiPresenter, StatusInfo, TaskSnapshot
from .theme import ACCENT, TEXT_DIM


class ChatTab(QWidget):
    """One chat: its own transcript, screen pane, prompt, controls, and
    its own workspace strip — chats are tabs, not a single lane."""

    def __init__(self, presenter: GuiPresenter, chat_id: str) -> None:
        super().__init__()
        self.presenter = presenter
        self.chat_id = chat_id
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 18, 18, 18)
        v.setSpacing(12)

        # THIS chat's workspace: shown and bindable right here.
        top = QHBoxLayout()
        self.workspace_label = QLabel("", objectName="dim")
        self.bind_edit = QLineEdit()
        self.bind_edit.setPlaceholderText(
            "path or git URL for THIS chat — empty keeps the global "
            "workspace")
        bind_btn = QPushButton("Use for this chat")
        bind_btn.clicked.connect(self._bind)
        top.addWidget(self.workspace_label, 1)
        top.addWidget(self.bind_edit, 1)
        top.addWidget(bind_btn)
        v.addLayout(top)

        split = QSplitter(Qt.Orientation.Vertical)
        self.transcript = QTextEdit(readOnly=True)
        self.transcript.setPlaceholderText(
            "Say or type a command — put commands in quotes if you like.")
        self.screen_pane = QPlainTextEdit(objectName="screenPane",
                                          readOnly=True)
        self.screen_pane.setPlaceholderText(
            "Code, diffs, logs, and reports land here — never in speech.")
        split.addWidget(self.transcript)
        split.addWidget(self.screen_pane)
        split.setSizes([420, 220])
        v.addWidget(split, 1)

        controls = QHBoxLayout()
        self.task_label = QLabel("", objectName="dim")
        pause = QPushButton("Pause", objectName="pause")
        resume = QPushButton("Resume")
        stop = QPushButton("Stop", objectName="stop")
        pause.clicked.connect(presenter.pause)
        resume.clicked.connect(presenter.resume)
        stop.clicked.connect(presenter.stop)
        controls.addWidget(self.task_label, 1)
        controls.addWidget(pause)
        controls.addWidget(resume)
        controls.addWidget(stop)
        v.addLayout(controls)

        prompt_row = QHBoxLayout()
        # The MIC BUTTON is the gate: on = everything you say is a
        # command (no wake word); Send turns it off.
        self.mic_btn = QPushButton("🎤", objectName="micButton")
        self.mic_btn.setCheckable(True)
        self.mic_btn.setToolTip(
            "Microphone on/off. While on, everything you say is a "
            "command — no wake word needed. Send turns it off. Pick "
            "WHICH microphone on the Settings page.")
        self.mic_btn.clicked.connect(self._mic_toggled)
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText(
            'e.g.  "build blinky for the apollo510"')
        self.prompt.returnPressed.connect(self._send)
        send = QPushButton("Send", objectName="primary")
        send.clicked.connect(self._send)
        prompt_row.addWidget(self.mic_btn)
        prompt_row.addWidget(self.prompt, 1)
        prompt_row.addWidget(send)
        v.addLayout(prompt_row)
        self.refresh_workspace()

    def _mic_toggled(self) -> None:
        if self.mic_btn.isChecked():
            self.presenter.set_active_chat(self.chat_id)
            if not self.presenter.start_voice():
                self.mic_btn.setChecked(False)
        else:
            self.presenter.stop_voice()

    def _send(self) -> None:
        # Sending typed input means you're TYPING now — the mic goes off.
        self.presenter.stop_voice()
        text = self.prompt.text()
        self.prompt.clear()
        self.presenter.set_active_chat(self.chat_id)
        self.presenter.submit_text(text)

    def _bind(self) -> None:
        target = self.bind_edit.text().strip()
        if not target:
            return
        self.bind_edit.clear()
        self.presenter.set_active_chat(self.chat_id)
        self.presenter.submit_text(f"use {target} for this chat")

    def refresh_workspace(self) -> None:
        self.workspace_label.setText(self.presenter.chat_info(self.chat_id))

    def transcript_add(self, who: str, text: str) -> None:
        from html import escape

        color = ACCENT if who != "You" else TEXT_DIM
        # Escape: this pane renders HTML, so an error naming <module> or
        # a diff containing <stdio.h> would otherwise vanish silently.
        body = escape(text).replace("\n", "<br/>")
        self.transcript.append(
            f'<p style="margin:6px 0"><b style="color:{color}">{escape(who)}'
            f"</b><br/>{body}</p>")

    def screen_add(self, text: str) -> None:
        self.screen_pane.appendPlainText(text + "\n")


class RitaWindow(QMainWindow):
    sig_chat_event = Signal(str, str, str)   # chat id, kind, text
    sig_task = Signal(object)
    sig_status = Signal(object)
    sig_voice = Signal(bool)                 # microphone state

    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        name = presenter.sup.cfg.assistant_name
        self.setWindowTitle(f"RITA — {name}")
        self.resize(1180, 760)

        # Presenter callbacks -> Qt signals (thread-safe hop). Every
        # chat event arrives tagged with its owning chat and lands in
        # that chat's TAB, not whichever one is focused.
        presenter.on_chat_event = self.sig_chat_event.emit
        presenter.on_task = self.sig_task.emit
        presenter.on_status = self.sig_status.emit
        presenter.on_voice = self.sig_voice.emit
        self.sig_chat_event.connect(self._chat_event)
        self.sig_task.connect(self._task_update)
        self.sig_status.connect(self._status_update)
        self.sig_voice.connect(self._voice_state)

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

        # Launching RITA IS the setup: fix every fixable gap unprompted.
        presenter.maybe_auto_setup()

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
        from ..learning import chats

        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(6, 6, 6, 6)
        self.chat_tabs = QTabWidget()
        newbtn = QToolButton()
        newbtn.setText("＋ New chat")
        newbtn.setToolTip("Open another chat — each one can have its own "
                          "repo/workspace.")
        newbtn.clicked.connect(self._add_chat_tab_clicked)
        self.chat_tabs.setCornerWidget(newbtn)
        self._tabs_by_chat: dict[str, ChatTab] = {}
        for cid in (chats.list_chats() or [chats.current_chat()]):
            self._open_tab(cid)
        current = chats.current_chat()
        if current in self._tabs_by_chat:
            self.chat_tabs.setCurrentWidget(self._tabs_by_chat[current])
        self.chat_tabs.currentChanged.connect(self._tab_changed)
        v.addWidget(self.chat_tabs)
        return page

    # --- chat tabs ------------------------------------------------------------

    def _open_tab(self, chat_id: str) -> ChatTab:
        tab = self._tabs_by_chat.get(chat_id)
        if tab is None:
            tab = ChatTab(self.presenter, chat_id)
            self._tabs_by_chat[chat_id] = tab
            self.chat_tabs.addTab(tab, chat_id)
        return tab

    def _add_chat_tab_clicked(self) -> None:
        cid = self.presenter.new_chat()
        self.chat_tabs.setCurrentWidget(self._open_tab(cid))

    def _tab_changed(self, idx: int) -> None:
        tab = self.chat_tabs.widget(idx)
        if isinstance(tab, ChatTab):
            self.presenter.set_active_chat(tab.chat_id)
            tab.refresh_workspace()

    def _voice_state(self, active: bool) -> None:
        # One microphone, shown consistently on every tab's button.
        for tab in self._tabs_by_chat.values():
            tab.mic_btn.setChecked(active)

    def _active_tab(self) -> ChatTab:
        tab = self.chat_tabs.currentWidget()
        if isinstance(tab, ChatTab):
            return tab
        return next(iter(self._tabs_by_chat.values()))

    def _chat_event(self, chat_id: str, kind: str, text: str) -> None:
        tab = self._open_tab(chat_id)
        if kind == "user":
            tab.transcript_add("You", text)
        elif kind == "reply":
            tab.transcript_add(self.presenter.sup.cfg.assistant_name, text)
            tab.refresh_workspace()      # bindings change via phrases
        elif kind == "screen":
            tab.screen_add(text)

    # --- legacy single-chat surface (delegates to the active tab) -------------

    @property
    def transcript(self):
        return self._active_tab().transcript

    @property
    def screen_pane(self):
        return self._active_tab().screen_pane

    @property
    def prompt(self):
        return self._active_tab().prompt

    @property
    def task_label(self):
        return self._active_tab().task_label

    def _send(self) -> None:
        self._active_tab()._send()

    def _transcript_add(self, who: str, text: str) -> None:
        self._active_tab().transcript_add(who, text)

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
