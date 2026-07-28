"""Modules page: the registry, visible — versions, current pointers."""

from __future__ import annotations

from PySide6.QtWidgets import (QLabel, QListWidget, QPushButton, QVBoxLayout,
                               QWidget)

from .presenter import GuiPresenter


class ModulesPage(QWidget):
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
