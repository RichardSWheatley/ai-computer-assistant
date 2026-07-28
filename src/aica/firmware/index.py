"""The static verification index (Fix 2, step 1): pure data, no LLM.

Built at workspace sync from `zephyr/samples/**/sample.yaml` and
`zephyr/tests/**/testcase.yaml`. `find()` filters by board compatibility and
ranks by term overlap — the resolver asks the index first, and only then asks
Claude to judge fit among what the index returned.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

from . import yamlmini


@dataclass(frozen=True)
class IndexEntry:
    id: str                          # e.g. "sample.basic.blinky"
    kind: Literal["sample", "test"]
    path: str                        # workspace-relative dir of the suite
    name: str
    description: str
    platform_allow: tuple[str, ...]  # empty = allowed everywhere
    integration_platforms: tuple[str, ...]
    filter: str | None               # recorded, not evaluated (twister's job)
    harness: str | None
    depends_on: tuple[str, ...]
    tags: tuple[str, ...]
    readme_path: str | None


def _as_tuple(v) -> tuple[str, ...]:
    if v is None:
        return ()
    if isinstance(v, str):
        return tuple(v.split())
    return tuple(str(x) for x in v)


def _parse_suite_yaml(ws: Path, yaml_path: Path, kind: str) -> list[IndexEntry]:
    try:
        data = yamlmini.load(yaml_path.read_text())
    except Exception:
        return []  # a malformed metadata file must not sink the whole index
    if not isinstance(data, dict):
        return []
    meta = data.get("sample") or {}
    common = data.get("common") or {}
    suite_dir = yaml_path.parent
    readme = next((p for p in (suite_dir / "README.rst", suite_dir / "README.md")
                   if p.exists()), None)
    entries = []
    for test_id, spec in (data.get("tests") or {}).items():
        spec = spec or {}
        merged = {**common, **spec}
        entries.append(IndexEntry(
            id=str(test_id),
            kind=kind,  # type: ignore[arg-type]
            path=suite_dir.relative_to(ws).as_posix(),
            name=str(meta.get("name") or test_id),
            description=str(meta.get("description") or ""),
            platform_allow=_as_tuple(merged.get("platform_allow")),
            integration_platforms=_as_tuple(merged.get("integration_platforms")),
            filter=merged.get("filter"),
            harness=merged.get("harness"),
            depends_on=_as_tuple(merged.get("depends_on")),
            tags=_as_tuple(merged.get("tags")),
            readme_path=readme.relative_to(ws).as_posix() if readme else None,
        ))
    return entries


def _platform_matches(allowed: str, board: str) -> bool:
    # "nrf52840dk/nrf52840" matches board "nrf52840dk" or the full platform.
    return allowed == board or allowed.split("/")[0] == board


class VerificationIndex:
    def __init__(self, entries: Sequence[IndexEntry]) -> None:
        self.entries: tuple[IndexEntry, ...] = tuple(entries)

    @staticmethod
    def build(workspace: str | Path) -> "VerificationIndex":
        ws = Path(workspace)
        entries: list[IndexEntry] = []
        for yaml_path in sorted(ws.glob("zephyr/samples/**/sample.yaml")):
            entries.extend(_parse_suite_yaml(ws, yaml_path, "sample"))
        for yaml_path in sorted(ws.glob("zephyr/tests/**/testcase.yaml")):
            entries.extend(_parse_suite_yaml(ws, yaml_path, "test"))
        return VerificationIndex(entries)

    def compatible(self, board: str) -> list[IndexEntry]:
        return [e for e in self.entries
                if not e.platform_allow
                or any(_platform_matches(a, board) for a in e.platform_allow)]

    def find(self, board: str, terms: Sequence[str], limit: int = 10) -> list[IndexEntry]:
        """Board-compatible entries ranked by term overlap; zero-score dropped."""
        want = {t.lower() for t in terms if t}
        scored: list[tuple[int, IndexEntry]] = []
        for e in self.compatible(board):
            hay = {t.lower() for t in e.tags}
            hay.update(t.lower() for t in e.id.replace(".", " ").split())
            hay.update(e.name.lower().split())
            hay.update(e.description.lower().strip(".").split())
            hay.update(t.lower() for t in e.depends_on)
            score = len(want & hay)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda se: (-se[0], se[1].id))
        return [e for _, e in scored[:limit]]

    # --- persistence (~/.rita/verification-index.json) ----------------------

    def save(self, path: str | Path | None = None) -> Path:
        from ..home import verification_index_path

        p = Path(path) if path else verification_index_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"entries": [asdict(e) for e in self.entries]},
                                indent=1))
        return p

    @staticmethod
    def load(path: str | Path | None = None) -> "VerificationIndex":
        from ..home import verification_index_path

        p = Path(path) if path else verification_index_path()
        data = json.loads(p.read_text())
        entries = []
        for d in data.get("entries", []):
            for k in ("platform_allow", "integration_platforms", "depends_on", "tags"):
                d[k] = tuple(d[k])
            entries.append(IndexEntry(**d))
        return VerificationIndex(entries)
