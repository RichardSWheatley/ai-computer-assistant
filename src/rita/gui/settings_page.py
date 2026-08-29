"""Settings page: the spoken name and the budgets — config, not code."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QFrame,
                               QLabel, QLineEdit, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..config import save_rita_config
from .presenter import GuiPresenter


class SettingsPage(QWidget):
    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        cfg = presenter.sup.cfg
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)
        v.addWidget(QLabel("Settings", objectName="title"))

        card = QFrame(objectName="card")
        form = QFormLayout(card)
        self.name_edit = QLineEdit(cfg.assistant_name)
        form.addRow("Assistant name", self.name_edit)
        self.coder_edit = QLineEdit(cfg.coder_command or "")
        self.coder_edit.setPlaceholderText(
            "coding agent CLI — a command that takes a prompt and can edit "
            "files; empty = RITA can't code")
        form.addRow("Coding agent", self.coder_edit)
        login = QPushButton("Log in coding agent")
        login.setToolTip("Opens your agent's own login window — finish "
                         "the login there; RITA verifies with 'check setup'.")
        login.clicked.connect(lambda: self.presenter.login_coder())
        form.addRow("", login)
        self.budget = QSpinBox()
        self.budget.setRange(1, 10)
        self.budget.setValue(cfg.max_patch_cycles)
        form.addRow("Patch cycles per stage", self.budget)
        self.cerberus_edit = QLineEdit(cfg.cerberus_command or "")
        self.cerberus_edit.setPlaceholderText(
            "custom CERBERUS command — empty = use the installed clone")
        form.addRow("CERBERUS override", self.cerberus_edit)
        self.cerberus_deep = QCheckBox(
            "Deep mode: analyze (Oracle LLM + Unity heads) instead of scan")
        self.cerberus_deep.setChecked(cfg.cerberus_deep)
        form.addRow("", self.cerberus_deep)
        self.host_cc_edit = QLineEdit(cfg.host_cc or "")
        self.host_cc_edit.setPlaceholderText(
            "unit-test compiler — empty = host PATH, else your Zephyr SDK's gcc")
        form.addRow("C compiler", self.host_cc_edit)
        self.autosetup = QCheckBox(
            "Set up missing pieces automatically on launch")
        self.autosetup.setChecked(cfg.auto_setup)
        form.addRow("", self.autosetup)
        self.voice = QCheckBox("Turn the microphone on when RITA starts "
                               "(the 🎤 button in chat toggles it any time)")
        self.voice.setChecked(cfg.voice_enabled)
        form.addRow("", self.voice)
        self.wakeword = QCheckBox(
            'Require the wake word ("hello Rita") — hands-free mode')
        self.wakeword.setChecked(cfg.voice_wake_word)
        self.wakeword.setToolTip(
            "Off (default): the mic button is the gate — while it's on, "
            "everything you say is a command. On: RITA ignores speech "
            "until you say her name, and sleeps again after the awake "
            "window.")
        form.addRow("", self.wakeword)
        # WHICH microphone — the system default once transcribed the
        # whole living room as commands.
        from ..voice.mic import list_input_devices

        self.mic_combo = QComboBox()
        self.mic_combo.addItem("System default", None)
        for dev in list_input_devices():
            self.mic_combo.addItem(dev, dev)
        if cfg.voice_input_device:
            idx = self.mic_combo.findText(cfg.voice_input_device)
            if idx < 0:
                self.mic_combo.addItem(
                    f"{cfg.voice_input_device} (not detected right now)",
                    cfg.voice_input_device)
                idx = self.mic_combo.count() - 1
            self.mic_combo.setCurrentIndex(idx)
        form.addRow("Microphone", self.mic_combo)
        self.awake_secs = QSpinBox()
        self.awake_secs.setRange(0, 3600)
        self.awake_secs.setValue(cfg.voice_awake_seconds)
        self.awake_secs.setToolTip(
            "After waking, RITA listens this many seconds past the last "
            "real command, then sleeps until you say her name again "
            "(0 = stay awake). Keeps background talk from becoming "
            "commands.")
        form.addRow("Awake window (s)", self.awake_secs)
        note = QLabel("The device tier stays off until the bench milestone — "
                      "it is never faked green.", objectName="dim")
        note.setWordWrap(True)
        form.addRow("", note)
        save = QPushButton("Save", objectName="primary")
        save.clicked.connect(self._save)
        form.addRow("", save)
        check = QPushButton("Check setup")
        check.setToolTip("Test everything RITA needs and report what's "
                         "wrong — results appear on the Chat page.")
        # Same deterministic path as typing it: one code path, not two.
        check.clicked.connect(
            lambda: self.presenter.submit_text("check setup"))
        form.addRow("", check)
        v.addWidget(card)
        v.addStretch(1)

    def _save(self) -> None:
        sup = self.presenter.sup
        sup.cfg.assistant_name = self.name_edit.text().strip() or "Rita"
        sup.cfg.coder_command = self.coder_edit.text().strip() or None
        sup.cfg.max_patch_cycles = self.budget.value()
        sup.cfg.cerberus_command = self.cerberus_edit.text().strip() or None
        sup.cfg.cerberus_deep = self.cerberus_deep.isChecked()
        sup.cfg.host_cc = self.host_cc_edit.text().strip() or None
        sup.cfg.voice_enabled = self.voice.isChecked()
        sup.cfg.voice_wake_word = self.wakeword.isChecked()
        sup.shell.require_wake = sup.cfg.voice_wake_word
        sup.shell.awake = not sup.cfg.voice_wake_word
        device_changed = (sup.cfg.voice_input_device
                          != self.mic_combo.currentData())
        sup.cfg.voice_input_device = self.mic_combo.currentData()
        sup.cfg.voice_awake_seconds = self.awake_secs.value()
        sup.cfg.auto_setup = self.autosetup.isChecked()
        save_rita_config(sup.cfg, sup.config_path)
        # Apply voice live — no restart. start_voice reports honestly if
        # the deps are missing (and the config stays set for next launch).
        if sup.cfg.voice_enabled:
            started = (self.presenter.restart_voice() if device_changed
                       else self.presenter.start_voice())
            if not started:
                self.voice.setChecked(False)
        else:
            self.presenter.stop_voice()
        from ..routing.wake import WakeGate

        sup.shell.cfg = sup.cfg
        sup.shell.gate = WakeGate(sup.cfg.assistant_name)
