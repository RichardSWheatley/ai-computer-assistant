"""Modules page: the registry, visible — versions, pointers, CERBERUS."""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget,
                               QPushButton, QVBoxLayout, QWidget)

from .presenter import GuiPresenter


class ModulesPage(QWidget):
    sig_cerberus = Signal(str)

    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)
        v.addWidget(QLabel("Modules", objectName="title"))
        v.addWidget(QLabel(
            "Capabilities run as separately versioned processes. Updates drop "
            "a new version and flip the pointer; running work drains on the "
            "old version.", objectName="dim"))
        self.listing = QListWidget()
        v.addWidget(self.listing, 1)
        install = QPushButton("Install bundled modules", objectName="primary")
        install.clicked.connect(self._install)
        v.addWidget(install)

        # CERBERUS — the static gate; the repo is part of RITA's install.
        card = QFrame(objectName="card")
        cv = QVBoxLayout(card)
        cv.addWidget(QLabel("CERBERUS static gate"))
        self.cerberus_status = QLabel("", objectName="dim")
        self.cerberus_status.setWordWrap(True)
        cv.addWidget(self.cerberus_status)
        row = QHBoxLayout()
        self.cerberus_btn = QPushButton("Install / update CERBERUS",
                                        objectName="primary")
        self.cerberus_btn.clicked.connect(self._install_cerberus)
        self.unity_btn = QPushButton("Install / update Unity")
        self.unity_btn.clicked.connect(self._install_unity)
        self.toolchain_btn = QPushButton("Install ARM toolchain")
        self.toolchain_btn.setToolTip(
            "Downloads arm-none-eabi-gcc matching your Zephyr SDK's gcc "
            "version — the unit tier compiles with it.")
        self.toolchain_btn.clicked.connect(self._install_toolchain)
        row.addWidget(self.cerberus_btn)
        row.addWidget(self.unity_btn)
        row.addWidget(self.toolchain_btn)
        row.addStretch(1)
        cv.addLayout(row)
        v.addWidget(card)
        self.sig_cerberus.connect(self.cerberus_status.setText)
        self._refresh_cerberus()
        self.refresh()

    def refresh(self) -> None:
        self.listing.clear()
        reg = self.presenter.sup.registry
        found = reg.discover()
        if not found:
            self.listing.addItem("No modules installed yet.")
            return
        for name, versions in found.items():
            current = reg.current(name)
            marks = ", ".join(f"{v} (current)" if v == current else v
                              for v in versions)
            self.listing.addItem(f"{name}   —   {marks}")

    def _install(self) -> None:
        from ..modules.install import dev_install

        dev_install()
        self.refresh()

    def _refresh_cerberus(self) -> None:
        from ..firmware.cerberus_setup import detect_cerberus

        clone = detect_cerberus()
        if clone:
            self.cerberus_status.setText(
                f"Installed at {clone} — Head 1 (94 MISRA/CERT checks) gates "
                f"every piece of generated code, no API key needed.")
        else:
            self.cerberus_status.setText(
                "Not installed. Installing clones "
                "github.com/RichardSWheatley/cerberus into ~/.rita (needs git).")

    def _install_unity(self) -> None:
        from ..firmware.unity import install_unity

        self.unity_btn.setEnabled(False)
        self.sig_cerberus.emit("Installing Unity (unit-test framework)…")

        def run() -> None:
            try:
                res = install_unity()
                self.sig_cerberus.emit(res.detail)
            finally:
                self.unity_btn.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _install_toolchain(self) -> None:
        from ..firmware.toolchain import install_arm_gcc

        self.toolchain_btn.setEnabled(False)
        self.sig_cerberus.emit("Downloading the ARM toolchain (matching "
                               "your Zephyr SDK's gcc)… this is large.")

        def run() -> None:
            try:
                res = install_arm_gcc()
                self.sig_cerberus.emit(res.detail)
            finally:
                self.toolchain_btn.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()

    def _install_cerberus(self) -> None:
        from ..firmware.cerberus_setup import install_cerberus

        self.cerberus_btn.setEnabled(False)
        self.sig_cerberus.emit("Installing CERBERUS…")

        def run() -> None:
            try:
                res = install_cerberus()
                self.sig_cerberus.emit(res.detail)
            finally:
                self.cerberus_btn.setEnabled(True)

        threading.Thread(target=run, daemon=True).start()
