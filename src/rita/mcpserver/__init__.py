"""The workspace MCP server: how the coder-worker sees the Zephyr checkout.

Tool implementations are pure functions over the workspace (`tools.py`),
fully tested without the SDK; `server.py` binds them to the optional `mcp`
package (`pip install .[mcp]`) and serves over stdio.
"""
