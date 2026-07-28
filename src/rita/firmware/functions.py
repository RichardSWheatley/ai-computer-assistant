"""Deterministic per-function coverage: every function gets tested.

The user's rule: test EVERY SINGLE FUNCTION you write — its input and
output parameters — before moving on. This scan makes that enforceable
without judgment: parse the authored C for function definitions, then name
any function that has no `test_<name>` in the unit-test sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# A C function DEFINITION at brace level 0: return type words, name, args,
# then an opening brace (not a ';' declaration). Deliberately simple —
# generated app code is conventional C, and false negatives get caught by
# CERBERUS/compilation anyway.
_FN_RE = re.compile(
    r"^[A-Za-z_][\w \t\*]*?[ \t\*]"          # return type-ish prefix
    r"([A-Za-z_]\w*)\s*"                      # function name
    r"\(([^;{)]|\([^)]*\))*\)\s*\{",          # (args) {
    re.MULTILINE)

_SKIP_NAMES = {"main", "if", "for", "while", "switch", "return", "sizeof"}


@dataclass(frozen=True)
class FunctionSig:
    name: str
    file: str
    line: int


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"),
                  text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def list_functions(src_dir: str | Path) -> list[FunctionSig]:
    """Every function defined in the authored .c files (main excluded;
    test files excluded — they are the coverage, not the covered)."""
    src_dir = Path(src_dir)
    out: list[FunctionSig] = []
    for c_file in sorted(src_dir.rglob("*.c")):
        if c_file.name.startswith("test_") or c_file.name == "unity.c":
            continue
        text = _strip_comments(c_file.read_text(errors="replace"))
        for m in _FN_RE.finditer(text):
            name = m.group(1)
            if name in _SKIP_NAMES:
                continue
            line = text[: m.start()].count("\n") + 1
            out.append(FunctionSig(name=name,
                                   file=c_file.relative_to(src_dir).as_posix(),
                                   line=line))
    return out


def untested_functions(src_dir: str | Path,
                       test_dir: str | Path) -> list[FunctionSig]:
    """Functions with no `test_<name>` anywhere in the unit-test sources."""
    functions = list_functions(src_dir)
    test_dir = Path(test_dir)
    corpus = ""
    if test_dir.is_dir():
        corpus = "\n".join(p.read_text(errors="replace")
                           for p in sorted(test_dir.rglob("*.c")))
    return [f for f in functions if f"test_{f.name}" not in corpus]
