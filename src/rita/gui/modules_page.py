"""Modules page: the registry, visible — versions, pointers, CERBERUS."""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QListWidget,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

from .presenter import GuiPresenter


class ModulesPage(QWidget):
    sig_cerberus = Signal(str)
    sig_log = Signal(str)
    sig_done = Signal(object, str)      # (button, original label)

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

        # Gates & toolchain — acquisition lives here; every result is
        # APPENDED to the log below, named by tool, never overwritten.
        card = QFrame(objectName="card")
        cv = QVBoxLayout(card)
        cv.addWidget(QLabel("Gates & toolchain"))
        self.cerberus_status = QLabel("", objectName="dim")
        self.cerberus_status.setWordWrap(True)
        cv.addWidget(self.cerberus_status)
        row = QHBoxLayout()
        # One row, ONE style — an arbitrary blue box among plain ones
        # reads as broken, not as emphasis.
        self.cerberus_btn = QPushButton("Install / update CERBERUS")
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
        self.log = QPlainTextEdit(objectName="screenPane", readOnly=True)
        self.log.setPlaceholderText(
            "Install results appear here — and in the Chat screen pane.")
        self.log.setFixedHeight(120)
        cv.addWidget(self.log)
        v.addWidget(card)
        self.sig_cerberus.connect(self.cerberus_status.setText)
        self.sig_log.connect(self._append_log)
        self.sig_done.connect(self._install_done)
        self._refresh_cerberus()
        self.refresh()

    def _append_log(self, text: str) -> None:
        self.log.appendPlainText(text)
        # Mirror to the chat screen pane so a result is never lost to a
        # page switch.
        self.presenter.mirror_screen(text)

    def _install_done(self, button, label: str) -> None:
        button.setEnabled(True)
        button.setText(label)

    def _run_install(self, name: str, button, fn, start_msg: str) -> None:
        # A click must be UNMISTAKABLE: the button disables and says so
        # until its install finishes (restored on the Qt thread).
        original = button.text()
        button.setEnabled(False)
        button.setText("Installing…")
        self.sig_log.emit(f"{name}: {start_msg}")

        def run() -> None:
            try:
                res = fn()
                mark = "" if res.ok else " FAILED"
                self.sig_log.emit(f"{name}{mark}: {res.detail}")
            except Exception as exc:   # a raising installer must be SEEN
                import traceback

                tb = "".join(traceback.format_exception(exc)).strip()
                self.sig_log.emit(f"{name} install FAILED: "
                                  f"{type(exc).__name__}: {exc}\n"
                                  f"--- where ---\n{tb[-900:]}")
            finally:
                self.sig_done.emit(button, original)

        threading.Thread(target=run, daemon=True).start()

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

    @staticmethod
    def _cerberus_summary() -> str:
        from ..firmware.cerberus_setup import detect_cerberus

        clone = detect_cerberus()
        if clone:
            return (f"Installed at {clone} — Head 1 (94 MISRA/CERT checks) "
                    f"gates every piece of generated code, no API key needed.")
        return ("Not installed. Installing clones "
                "github.com/RichardSWheatley/cerberus into ~/.rita (needs git).")

    def _refresh_cerberus(self) -> None:
        self.cerberus_status.setText(self._cerberus_summary())

    def _install_unity(self) -> None:
        def fn():
            from ..firmware.unity import install_unity

            return install_unity()

        self._run_install("Unity", self.unity_btn, fn,
                          "installing (unit-test framework)…")

    def _install_toolchain(self) -> None:
        def fn():
            from ..firmware.toolchain import install_arm_gcc

            return install_arm_gcc()

        self._run_install("ARM toolchain", self.toolchain_btn, fn,
                          "downloading arm-none-eabi-gcc matched to your "
                          "Zephyr SDK — large, takes a while…")

    def _install_cerberus(self) -> None:
        def fn():
            from ..firmware.cerberus_setup import install_cerberus

            res = install_cerberus()
            self.sig_cerberus.emit(self._cerberus_summary())
            return res

        self._run_install("CERBERUS", self.cerberus_btn, fn, "installing…")
