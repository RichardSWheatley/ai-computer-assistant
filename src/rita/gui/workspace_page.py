"""Workspace page: point RITA at the Zephyr folder — inside the GUI."""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from .presenter import GuiPresenter


class WorkspacePage(QWidget):
    sig_result = Signal(str)

    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)

        v.addWidget(QLabel("Workspace", objectName="title"))
        v.addWidget(QLabel(
            "Point RITA at your Zephyr workspace — the folder that contains "
            "zephyr/ (e.g. C:\\zephyrproject). Everything RITA knows about "
            "your boards, samples, and Zephyr version comes from this "
            "folder.", objectName="dim"))

        card = QFrame(objectName="card")
        cv = QVBoxLayout(card)
        row = QHBoxLayout()
        self.path_edit = QLineEdit(presenter.sup.cfg.workspace or "")
        self.path_edit.setPlaceholderText(r"C:\zephyrproject")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(self.path_edit, 1)
        row.addWidget(browse)
        cv.addLayout(row)

        row2 = QHBoxLayout()
        self.map_edit = QLineEdit(presenter.sup.cfg.hardware_map or "")
        self.map_edit.setPlaceholderText(
            "optional: twister hardware map (map.yaml) for connected boards")
        row2.addWidget(self.map_edit, 1)
        cv.addLayout(row2)

        self.sync_btn = QPushButton("Sync workspace", objectName="primary")
        self.sync_btn.clicked.connect(self._sync)
        cv.addWidget(self.sync_btn)
        self.result = QLabel("", objectName="dim")
        self.result.setWordWrap(True)
        cv.addWidget(self.result)
        v.addWidget(card)
        v.addStretch(1)
        self.sig_result.connect(self.result.setText)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Zephyr workspace folder")
        if path:
            self.path_edit.setText(path)

    def _sync(self) -> None:
        path = self.path_edit.text().strip()
        if not path:
            self.result.setText("Choose a folder first.")
            return
        hw_map = self.map_edit.text().strip() or None
        self.sync_btn.setEnabled(False)
        self.sig_result.emit("Syncing — indexing boards, samples, and tests…")

        def run() -> None:
            try:
                res = self.presenter.sync(path, hw_map=hw_map)
                st = self.presenter.status()
                self.sig_result.emit(
                    f"Synced {res.boards} boards and {res.entries} suites. "
                    f"Zephyr {st.zephyr_version or 'version unknown'}. "
                    f"The claude-worker now sees this workspace over MCP.")
            except Exception as exc:
                self.sig_result.emit(f"Sync failed: {exc}")
            finally:
                self.sync_btn.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()
