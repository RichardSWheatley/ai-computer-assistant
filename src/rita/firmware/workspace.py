"""Facts about the ACTUAL Zephyr install — read, never assumed.

Everything RITA says about Zephyr (version, what's in the tree) comes from
the workspace it was given: the version from the checkout's
`zephyr/VERSION` file, boards/samples from the sync scan. A missing fact is
reported as missing, not invented.
"""

from __future__ import annotations

import re
from pathlib import Path

_FIELD_RE = re.compile(r"^\s*(VERSION_MAJOR|VERSION_MINOR|PATCHLEVEL|"
                       r"VERSION_TWEAK|EXTRAVERSION)\s*=\s*(\S*)\s*$")


def read_zephyr_version(zephyr_base: Path) -> str | None:
    """Parse zephyr/VERSION (the tree's own version file). None if absent."""
    vf = zephyr_base / "VERSION"
    if not vf.is_file():
        return None
    fields: dict[str, str] = {}
    for line in vf.read_text().splitlines():
        m = _FIELD_RE.match(line)
        if m:
            fields[m.group(1)] = m.group(2)
    try:
        version = (f"{int(fields['VERSION_MAJOR'])}."
                   f"{int(fields['VERSION_MINOR'])}."
                   f"{int(fields['PATCHLEVEL'])}")
    except (KeyError, ValueError):
        return None
    extra = fields.get("EXTRAVERSION", "")
    return f"{version}-{extra}" if extra else version


def read_workspace_info(workspace: str | Path) -> dict:
    ws = Path(workspace)
    zephyr_base = ws / "zephyr"
    return {
        "workspace": str(ws),
        "zephyr_base": str(zephyr_base),
        "zephyr_version": read_zephyr_version(zephyr_base),
    }
