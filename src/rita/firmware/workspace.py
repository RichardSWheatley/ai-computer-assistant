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


def read_sdk_info() -> dict | None:
    """The actual Zephyr SDK install, or None — never guessed.

    Discovery order (per the SDK docs): ZEPHYR_SDK_INSTALL_DIR, then
    zephyr-sdk-* under the standard locations. Version from the SDK's
    sdk_version file, else the directory name.
    """
    import os

    candidates: list[Path] = []
    env = os.environ.get("ZEPHYR_SDK_INSTALL_DIR")
    if env and Path(env).is_dir():
        env_path = Path(env)
        if env_path.name.startswith("zephyr-sdk"):
            candidates.append(env_path)
        else:  # parent dir holding several SDK versions
            candidates.extend(sorted(env_path.glob("zephyr-sdk-*")))
    if not candidates:
        roots = [Path.home(), Path.home() / ".local", Path.home() / ".local/opt",
                 Path("/opt"), Path("/usr/local")]
        pf = os.environ.get("PROGRAMFILES")
        if pf:
            roots.append(Path(pf))
        for root in roots:
            if root.is_dir():
                candidates.extend(sorted(root.glob("zephyr-sdk-*")))
    for sdk in candidates:
        if not sdk.is_dir():
            continue
        version_file = sdk / "sdk_version"
        if version_file.is_file():
            version = version_file.read_text().strip()
        else:
            version = sdk.name.removeprefix("zephyr-sdk-")
        return {"path": str(sdk), "version": version}
    return None


def read_workspace_info(workspace: str | Path) -> dict:
    ws = Path(workspace)
    zephyr_base = ws / "zephyr"
    return {
        "workspace": str(ws),
        "zephyr_base": str(zephyr_base),
        "zephyr_version": read_zephyr_version(zephyr_base),
        "sdk": read_sdk_info(),
    }
