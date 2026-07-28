"""boards.json generation: the board vocabulary, from the workspace itself.

Scans `zephyr/boards/**/board.yml` plus the sibling twister platform yaml
(identifier, arch, `supported:` peripherals) and merges the user's twister
hardware map for connected-port data. Ports and probes always come from the
generated map — never hardcoded.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import yamlmini

_STRIP_SUFFIXES = ("_evb", "_dk", "_devkitc", "_devkit", "_board")


def derive_aliases(name: str) -> list[str]:
    """Spoken-form aliases for a board id: apollo510_evb -> apollo510,
    'apollo 510', 'apollo510 evb', ..."""
    aliases: set[str] = set()
    base = name
    for suf in _STRIP_SUFFIXES:
        if base.endswith(suf):
            base = base[: -len(suf)]
            aliases.add(base)
    aliases.add(name.replace("_", " "))
    aliases.add(base.replace("_", " "))
    # "apollo510" -> "apollo 510" (letters/digits boundary, how people speak)
    spaced = re.sub(r"(?<=[a-z])(?=\d)", " ", base)
    if spaced != base:
        aliases.add(spaced)
    aliases.discard(name)
    return sorted(a for a in aliases if a)


def _load_hw_map(hw_map: str | Path | None) -> dict[str, dict]:
    """platform identifier -> connected-device info from twister's map.yaml."""
    if not hw_map or not Path(hw_map).exists():
        return {}
    data = yamlmini.load(Path(hw_map).read_text()) or []
    out: dict[str, dict] = {}
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("connected"):
            continue
        platform = str(entry.get("platform") or "")
        if not platform:
            continue
        info = {k: entry[k] for k in ("serial", "runner", "product", "probe_id")
                if entry.get(k) is not None}
        out[platform] = info
    return out


def build_boards_json(workspace: str | Path,
                      hw_map: str | Path | None = None) -> dict:
    ws = Path(workspace)
    connected = _load_hw_map(hw_map)
    boards: dict[str, dict] = {}
    for board_yml in sorted(ws.glob("zephyr/boards/**/board.yml")):
        try:
            meta = (yamlmini.load(board_yml.read_text()) or {}).get("board") or {}
        except Exception:
            continue
        name = str(meta.get("name") or board_yml.parent.name)
        entry: dict = {
            "name": name,
            "aliases": derive_aliases(name),
            "vendor": meta.get("vendor"),
            "arch": None,
            "twister_platform": name,
            "supported": [],
        }
        # Sibling twister platform yaml(s) carry identifier/arch/supported.
        for plat_yaml in sorted(board_yml.parent.glob("*.yaml")):
            try:
                plat = yamlmini.load(plat_yaml.read_text()) or {}
            except Exception:
                continue
            if not isinstance(plat, dict) or "identifier" not in plat:
                continue
            entry["twister_platform"] = str(plat["identifier"])
            entry["arch"] = plat.get("arch") or entry["arch"]
            supported = plat.get("supported") or []
            if isinstance(supported, str):
                supported = supported.split()
            entry["supported"] = sorted({*entry["supported"], *map(str, supported)})
        hw = connected.get(entry["twister_platform"])
        if hw:
            entry["connected"] = hw
        boards[name] = entry
    return {"workspace": str(ws), "boards": boards}
