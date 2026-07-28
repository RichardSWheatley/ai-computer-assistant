"""stdio MCP server binding (`rita mcp-serve`).

Thin: every tool delegates to `WorkspaceTools`, which is where the tests
live. Needs the optional `mcp` extra; without it this module still imports,
and `serve()` explains what to install.
"""

from __future__ import annotations

import json
from pathlib import Path

from .tools import WorkspaceTools

SERVER_NAME = "rita-workspace"


def mcp_available() -> bool:
    try:
        import mcp  # type: ignore  # noqa: F401

        return True
    except ImportError:
        return False


def build_server(workspace: str | Path):  # pragma: no cover - exercised via SDK
    """Construct the FastMCP server over a workspace (requires the mcp extra)."""
    from mcp.server.fastmcp import FastMCP  # type: ignore

    tools = WorkspaceTools(workspace)
    srv = FastMCP(SERVER_NAME)

    @srv.tool()
    def workspace_info() -> str:
        """Facts about this Zephyr install: version (from zephyr/VERSION),
        workspace path, board and suite counts."""
        return json.dumps(tools.workspace_info())

    @srv.tool()
    def find_verification(board: str, query: str, limit: int = 10) -> str:
        """Ranked samples/tests from the verification index that could verify
        an intent on a board. Query = peripheral/subsystem terms."""
        return json.dumps(tools.find_verification(board, query, limit))

    @srv.tool()
    def board_info(name: str) -> str:
        """A board's vocabulary entry: platform id, arch, supported
        peripherals, connected port info."""
        return json.dumps(tools.board_info(name))

    @srv.tool()
    def list_boards(supports: str = "") -> str:
        """All known boards, optionally filtered to those supporting a
        peripheral (e.g. 'adc')."""
        return json.dumps(tools.list_boards(supports or None))

    @srv.tool()
    def sample_lookup(name: str) -> str:
        """A sample/test suite's path, twister yaml, and README text."""
        return json.dumps(tools.sample_lookup(name))

    @srv.tool()
    def read_workspace_file(path: str, max_bytes: int = 65536) -> str:
        """Read a file inside the workspace (bounded; relative paths only)."""
        return tools.read_workspace_file(path, max_bytes)

    @srv.tool()
    def grep_workspace(pattern: str, glob: str = "", max_results: int = 50) -> str:
        """Regex-search workspace files; returns path/lineno/line hits."""
        return json.dumps(tools.grep_workspace(pattern, glob or None, max_results))

    return srv


def serve(workspace: str | Path) -> int:  # pragma: no cover - blocking stdio loop
    if not mcp_available():
        print("The MCP server needs the optional extra: pip install '.[mcp]'")
        return 2
    build_server(workspace).run()  # stdio transport by default
    return 0
