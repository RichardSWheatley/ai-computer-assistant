"""Minimal YAML loading for Zephyr metadata files.

Uses pyyaml when installed (`pip install .[firmware]`); otherwise falls back
to a vendored subset parser that covers what sample.yaml / testcase.yaml /
board.yml / twister platform yaml / map.yaml actually use: nested mappings by
indentation, block lists (`- ` items, scalar or mapping), scalars (str, int,
bool), quoted strings, and comments. Anchors, flow style, and multi-line
scalars are NOT supported — pyyaml handles those rare files.
"""

from __future__ import annotations

from typing import Any


def load(text: str) -> Any:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _parse(text)


def _scalar(s: str) -> Any:
    s = s.strip()
    if not s:
        return None
    if s[0] in "\"'" and s[-1] == s[0] and len(s) >= 2:
        return s[1:-1]
    low = s.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~"):
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def _strip_comment(line: str) -> str:
    out, in_s, in_d = [], False, False
    for ch in line:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse(text: str) -> Any:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = _strip_comment(raw)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        lines.append((indent, line.strip()))
    value, consumed = _block(lines, 0, 0)
    if consumed != len(lines):
        raise ValueError(f"yamlmini: could not parse line {consumed + 1}")
    return value


def _block(lines: list[tuple[int, str]], pos: int, indent: int) -> tuple[Any, int]:
    if pos >= len(lines):
        return None, pos
    if lines[pos][1].startswith("- "):
        return _list_block(lines, pos, lines[pos][0])
    return _map_block(lines, pos, lines[pos][0])


def _list_block(lines, pos, indent) -> tuple[list, int]:
    items: list[Any] = []
    while pos < len(lines) and lines[pos][0] == indent and lines[pos][1].startswith("- "):
        content = lines[pos][1][2:].strip()
        if ":" in content and not content.startswith(("'", '"')):
            # "- key: value" opens an inline mapping item; following deeper
            # lines extend it.
            item: dict = {}
            k, _, v = content.partition(":")
            item[k.strip()] = _scalar(v) if v.strip() else None
            pos += 1
            while pos < len(lines) and lines[pos][0] > indent:
                sub, pos = _map_block(lines, pos, lines[pos][0])
                item.update(sub)
            items.append(item)
        else:
            items.append(_scalar(content))
            pos += 1
    return items, pos


def _map_block(lines, pos, indent) -> tuple[dict, int]:
    out: dict = {}
    while pos < len(lines) and lines[pos][0] == indent and not lines[pos][1].startswith("- "):
        key, sep, rest = lines[pos][1].partition(":")
        if not sep:
            raise ValueError(f"yamlmini: expected 'key:' at line {pos + 1}")
        key = _scalar(key)
        rest = rest.strip()
        pos += 1
        if rest:
            out[key] = _scalar(rest)
        elif pos < len(lines) and lines[pos][0] > indent:
            out[key], pos = _block(lines, pos, lines[pos][0])
        else:
            out[key] = None
    return out, pos
