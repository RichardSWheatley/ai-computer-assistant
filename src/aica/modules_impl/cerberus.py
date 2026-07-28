"""cerberus module — HONEST STUB.

The CERBERUS analysis tool is external and not present in this install.
The manifest is real so the registry/protocol path is exercised, but start
reports the truth instead of faking capability.
"""

from __future__ import annotations

from ..modules.runtime import serve

_NOT_PRESENT = {"ok": False,
                "error": "CERBERUS is not present on this machine; "
                         "install it and update this module"}


def start(params, emit):
    return dict(_NOT_PRESENT)


def status(params, emit):
    return dict(_NOT_PRESENT)


if __name__ == "__main__":  # pragma: no cover - exercised as a child process
    serve(name="cerberus", version="0.1.0",
          handlers={"start": start, "status": status})
