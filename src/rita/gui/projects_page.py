"""Projects page: hand a goal to RITA, watch her work the plan.

The handoff box feeds the same deterministic route as typing
"start a project: <goal>" in chat — no separate code path. The item list
is a live view over the persisted ProjectStore, refreshed on a timer, so
it shows exactly what a restart would reload.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QPushButton, QVBoxLayout, QWidget)

from .presenter import GuiPresenter

_STATUS_MARK = {
    "pending": "·", "running": "▶", "done": "✓", "answered": "✓",
    "blocked": "✗", "needs_user": "?", "stopped": "■",
}


class ProjectsPage(QWidget):
    def __init__(self, presenter: GuiPresenter) -> None:
        super().__init__()
        self.presenter = presenter
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(14)
        v.addWidget(QLabel("Projects", objectName="title"))
        v.addWidget(QLabel(
            "Hand RITA a goal. She runs it directly if it's a single "
            "command; otherwise an AI drafts the item list and RITA "
            "executes every item through her gates — the AI never runs "
            "anything.", objectName="dim"))

        row = QHBoxLayout()
        self.goal = QLineEdit()
        self.goal.setPlaceholderText(
            "e.g.  bring up the mspi psram example and characterize it")
        self.goal.returnPressed.connect(self._hand_off)
        hand = QPushButton("Hand off to RITA", objectName="primary")
        hand.clicked.connect(self._hand_off)
        row.addWidget(self.goal, 1)
        row.addWidget(hand)
        v.addLayout(row)

        self.header = QLabel("", objectName="dim")
        v.addWidget(self.header)
        self.listing = QListWidget()
        v.addWidget(self.listing, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(1000)
        self.refresh()

    def _hand_off(self) -> None:
        goal = self.goal.text().strip()
        if not goal:
            return
        self.goal.clear()
        # Same deterministic route as typing it in chat.
        self.presenter.submit_text(f"start a project: {goal}")

    def refresh(self) -> None:
        from ..projects.model import ProjectStore

        projects = ProjectStore().all()
        if not projects:
            self.header.setText("No projects yet.")
            self.listing.clear()
            return
        p = projects[-1]
        done = sum(1 for i in p.items if i.status in ("done", "answered"))
        self.header.setText(
            f"{p.id} — {p.goal}   ({done}/{len(p.items)} complete)")
        lines = []
        for i in p.items:
            mark = _STATUS_MARK.get(i.status, "·")
            extra = f"   — {i.note}" if i.status in ("blocked", "needs_user") \
                and i.note else ""
            est = f"  [{i.estimate}]" if i.estimate else ""
            lines.append(f"{mark}  {i.title}{est}   ({i.status}){extra}")
        current = [self.listing.item(n).text()
                   for n in range(self.listing.count())]
        if lines != current:
            self.listing.clear()
            self.listing.addItems(lines)
