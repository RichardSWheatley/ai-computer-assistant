"""Settings page: the spoken name and the budgets — config, not code."""

from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QFormLayout, QFrame, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

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
        self.budget = QSpinBox()
        self.budget.setRange(1, 10)
        self.budget.setValue(cfg.max_patch_cycles)
        form.addRow("Patch cycles per stage", self.budget)
        self.cerberus_edit = QLineEdit(cfg.cerberus_command or "")
        self.cerberus_edit.setPlaceholderText(
            "CERBERUS command (static gate) — leave empty to skip the stage")
        form.addRow("CERBERUS", self.cerberus_edit)
        self.voice = QCheckBox("Enable voice (wake word + speech)")
        form.addRow("", self.voice)
        note = QLabel("The device tier stays off until the bench milestone — "
                      "it is never faked green.", objectName="dim")
        note.setWordWrap(True)
        form.addRow("", note)
        save = QPushButton("Save", objectName="primary")
        save.clicked.connect(self._save)
        form.addRow("", save)
        v.addWidget(card)
        v.addStretch(1)

    def _save(self) -> None:
        sup = self.presenter.sup
        sup.cfg.assistant_name = self.name_edit.text().strip() or "Rita"
        sup.cfg.max_patch_cycles = self.budget.value()
        sup.cfg.cerberus_command = self.cerberus_edit.text().strip() or None
        save_rita_config(sup.cfg, sup.config_path)
        from ..routing.wake import WakeGate

        sup.shell.cfg = sup.cfg
        sup.shell.gate = WakeGate(sup.cfg.assistant_name)
