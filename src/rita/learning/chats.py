"""Per-chat work areas: every chat can bind its own repo/workspace.

Each chat owns a directory under ~/.rita/chats/<id>/ holding chat.toml
(the binding: a local path, or a git URL RITA clones into the area
herself) plus that chat's synced data. Unbound chats fall back to the
global default workspace, so the single-workspace flow keeps working.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _root() -> Path:
    from ..home import chats_dir

    return chats_dir()


def _current_marker() -> Path:
    return _root() / "current"


def current_chat() -> str:
    """The active chat id (persisted across launches); chat-1 default."""
    m = _current_marker()
    if m.is_file():
        name = m.read_text().strip()
        if name:
            return name
    return "chat-1"


def set_current(chat_id: str) -> None:
    _root().mkdir(parents=True, exist_ok=True)
    _current_marker().write_text(chat_id)


def new_chat() -> str:
    """The next chat id, made current. New chats start unbound. The
    default current chat may have no directory yet — it still counts
    as taken, or "new chat" would hand back the one already open."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    taken = set(list_chats()) | {current_chat()}
    n = 1
    while f"chat-{n}" in taken or (root / f"chat-{n}").exists():
        n += 1
    (root / f"chat-{n}").mkdir()
    set_current(f"chat-{n}")
    return f"chat-{n}"


def list_chats() -> list[str]:
    """Existing chat ids, oldest first (chat-1, chat-2, …)."""
    root = _root()
    if not root.is_dir():
        return []
    out = [d.name for d in root.iterdir()
           if d.is_dir() and d.name.startswith("chat-")]
    return sorted(out, key=lambda n: int(n.split("-")[1])
                  if n.split("-")[1].isdigit() else 0)


def chat_area(chat_id: str | None = None) -> Path:
    return _root() / (chat_id or current_chat())


def _binding_file(chat_id: str | None) -> Path:
    return chat_area(chat_id) / "chat.toml"


def _git_clone(url: str, dest: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(["git", "clone", url, str(dest)],
                              capture_output=True, text=True, timeout=600,
                              stdin=subprocess.DEVNULL)
    except Exception as exc:
        return False, f"git clone failed to start: {exc}"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "git clone failed")[-300:]
    return True, f"cloned {url}"


def bind(spec: str, chat_id: str | None = None) -> tuple[str | None, str]:
    """Bind this chat to a repo/area: (workspace path, message).

    A git URL is cloned into the chat's own area; a local path is
    recorded as-is. A path that doesn't exist is refused honestly."""
    area = chat_area(chat_id)
    area.mkdir(parents=True, exist_ok=True)
    spec = spec.strip()
    if spec.startswith(("http://", "https://", "git@", "ssh://")) \
            or spec.endswith(".git"):
        dest = area / "repo"
        if not dest.exists():
            ok, note = _git_clone(spec, dest)
            if not ok:
                return None, f"I couldn't clone {spec}: {note}"
        path = str(dest)
    else:
        p = Path(spec).expanduser()
        if not p.is_dir():
            return None, (f"I can't find {spec} on this machine — the "
                          f"path doesn't exist, so this chat keeps its "
                          f"current workspace.")
        path = str(p)
    _binding_file(chat_id).write_text(
        f'repo = "{spec}"\npath = "{path}"\n'.replace("\\", "\\\\"))
    return path, (f"This chat now works in {path}. Say sync to map it, "
                  f"and everything I learn here stays with this chat.")


def bound_workspace(chat_id: str | None = None) -> str | None:
    """The chat's bound workspace path, re-validated — None = unbound."""
    f = _binding_file(chat_id)
    if not f.is_file():
        return None
    path = None
    for ln in f.read_text().splitlines():
        if ln.startswith("path"):
            raw = ln.split("=", 1)[1].strip().strip('"')
            path = raw.replace("\\\\", "\\")
    if path and Path(path).is_dir():
        return path
    return None
