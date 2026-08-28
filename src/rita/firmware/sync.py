"""`rita sync`: build boards.json + the verification index into ~/.rita/.

Pure data extraction — no LLM anywhere. After a sync the router's vocabulary
(Fix 1) and the resolver (Fix 2) both read the generated files.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..home import boards_json_path
from .boards import build_boards_json
from .index import VerificationIndex


@dataclass(frozen=True)
class SyncResult:
    boards: int
    entries: int
    boards_path: str
    index_path: str
    mcp_config: str


def _write_mcp_config(ws: Path) -> str:
    """~/.rita/mcp.json: how the coding-agent CLI reaches the workspace MCP server.

    Module-invocation form (this interpreter, `-m rita`) so it works from
    any venv or packaged install regardless of PATH."""
    import sys

    from ..home import mcp_config_path

    p = mcp_config_path()
    p.write_text(json.dumps({"mcpServers": {"rita-workspace": {
        "command": sys.executable,
        "args": ["-m", "rita", "mcp-serve", "--workspace", str(ws)],
    }}}, indent=1))
    return str(p)


def sync_workspace(workspace: str | Path,
                   hw_map: str | Path | None = None) -> SyncResult:
    ws = Path(workspace)
    # Accept the workspace root (contains zephyr/) or the zephyr/ tree itself.
    if not (ws / "zephyr").is_dir():
        if (ws / "samples").is_dir() and (ws / "VERSION").is_file():
            ws = ws.parent
        else:
            raise ValueError(f"not a Zephyr workspace (no zephyr/ in {ws})")

    boards = build_boards_json(ws, hw_map=hw_map)
    bp = boards_json_path()
    bp.parent.mkdir(parents=True, exist_ok=True)
    bp.write_text(json.dumps(boards, indent=1))

    index = VerificationIndex.build(ws)
    ip = index.save()
    mcp = _write_mcp_config(ws)

    return SyncResult(boards=len(boards["boards"]), entries=len(index.entries),
                      boards_path=str(bp), index_path=str(ip), mcp_config=mcp)
