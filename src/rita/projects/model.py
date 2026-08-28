"""Project data + the restart-safe store (~/.rita/projects.json).

Every status transition is saved immediately, so a project survives a
restart mid-run and the GUI/chat can always answer "how is it going".
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# pending -> running -> done | blocked        (work items, gated)
#            answered                          (chat/knowledge items)
#            needs_user                        (unroutable: flagged, never guessed)
#            stopped                           (user stopped mid-item)
ITEM_STATUSES = ("pending", "running", "done", "blocked", "answered",
                 "needs_user", "stopped")


@dataclass
class ProjectItem:
    id: str
    title: str
    command: str                  # phrased in RITA's own grammar
    depends_on: list[str] = field(default_factory=list)
    status: str = "pending"
    note: str = ""
    estimate: str = ""
    milestone: str = ""


@dataclass
class Project:
    id: str
    goal: str
    items: list[ProjectItem] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(
        timezone.utc).isoformat(timespec="seconds"))


class ProjectStore:
    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            from ..home import rita_home

            path = rita_home() / "projects.json"
        self.path = Path(path)
        self._projects: dict[str, Project] = {}
        if self.path.exists():
            data = json.loads(self.path.read_text())
            for p in data.get("projects", []):
                items = [ProjectItem(**i) for i in p.pop("items", [])]
                self._projects[p["id"]] = Project(items=items, **p)

    def new_id(self) -> str:
        return f"proj-{len(self._projects) + 1}"

    def save(self, project: Project) -> None:
        self._projects[project.id] = project
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"projects": [asdict(p) for p in self._projects.values()]},
            indent=1))

    def get(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    def all(self) -> list[Project]:
        return list(self._projects.values())
