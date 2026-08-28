"""Workspace MCP tool implementations: read-only, workspace-rooted, bounded.

The coder-worker queries the Zephyr checkout through these instead of
groping the filesystem: the verification index, board vocabulary, sample
lookup, bounded reads, and bounded search. Every path is resolved against
the workspace root and rejected if it escapes.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import asdict
from pathlib import Path

from ..firmware.boards import build_boards_json
from ..firmware.index import VerificationIndex

_MAX_FILE_BYTES = 65536
_MAX_GREP_FILE_BYTES = 512 * 1024
_SKIP_DIRS = {".git", ".west", "build", "twister-out", "__pycache__"}


class WorkspaceTools:
    def __init__(self, workspace: str | Path,
                 index: VerificationIndex | None = None,
                 boards: dict | None = None) -> None:
        self.workspace = Path(workspace).resolve()
        self.index = index or VerificationIndex.build(self.workspace)
        self.boards = boards or build_boards_json(self.workspace)["boards"]

    # --- path safety --------------------------------------------------------

    def _safe(self, rel: str) -> Path:
        p = Path(rel)
        if p.is_absolute():
            raise ValueError(f"absolute paths are not allowed: {rel}")
        resolved = (self.workspace / p).resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ValueError(f"path escapes the workspace: {rel}")
        return resolved

    # --- tools --------------------------------------------------------------

    def workspace_info(self) -> dict:
        from ..firmware.workspace import read_workspace_info

        info = read_workspace_info(self.workspace)
        info["boards"] = len(self.boards)
        info["indexed_suites"] = len(self.index.entries)
        return info

    def list_topics(self) -> list[dict]:
        from ..firmware import knowledge

        return knowledge.list_topics()

    def zephyr_howto(self, topic: str) -> str | None:
        from ..firmware import knowledge

        return knowledge.get_topic(topic)

    def find_verification(self, board: str, query: str, limit: int = 10) -> list[dict]:
        terms = query.replace(",", " ").split()
        return [asdict(e) for e in self.index.find(board, terms, limit=limit)]

    def board_info(self, name: str) -> dict | None:
        return self.boards.get(name)

    def list_boards(self, supports: str | None = None) -> list[dict]:
        out = list(self.boards.values())
        if supports:
            out = [b for b in out if supports in b.get("supported", [])]
        return out

    def sample_lookup(self, name: str) -> dict | None:
        want = name.lower()
        for e in self.index.entries:
            if want in e.id.lower() or want == e.name.lower():
                suite_dir = self.workspace / e.path
                yaml_name = "sample.yaml" if e.kind == "sample" else "testcase.yaml"
                yaml_text = (suite_dir / yaml_name).read_text()
                readme = ""
                if e.readme_path:
                    readme = (self.workspace / e.readme_path).read_text()[:_MAX_FILE_BYTES]
                return {"id": e.id, "path": e.path, "yaml": yaml_text,
                        "readme": readme}
        return None

    def read_workspace_file(self, path: str, max_bytes: int = _MAX_FILE_BYTES) -> str:
        p = self._safe(path)
        if not p.is_file():
            raise ValueError(f"not a file in the workspace: {path}")
        return p.read_text(errors="replace")[:max_bytes]

    def grep_workspace(self, pattern: str, glob: str | None = None,
                       max_results: int = 50) -> list[dict]:
        rx = re.compile(pattern)
        hits: list[dict] = []
        for p in sorted(self.workspace.rglob("*")):
            if len(hits) >= max_results:
                break
            if not p.is_file() or any(part in _SKIP_DIRS for part in p.parts):
                continue
            rel = p.relative_to(self.workspace).as_posix()
            if glob and not fnmatch.fnmatch(p.name, glob) \
                    and not fnmatch.fnmatch(rel, glob):
                continue
            if p.stat().st_size > _MAX_GREP_FILE_BYTES:
                continue
            try:
                text = p.read_text(errors="strict")
            except (UnicodeDecodeError, OSError):
                continue  # binary or unreadable
            for lineno, line in enumerate(text.splitlines(), 1):
                if rx.search(line):
                    hits.append({"path": rel, "lineno": lineno,
                                 "line": line.strip()[:400]})
                    if len(hits) >= max_results:
                        break
        return hits
