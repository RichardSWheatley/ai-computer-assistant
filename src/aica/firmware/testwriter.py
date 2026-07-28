"""Test authorship (Fix 2, step 3): no index match -> Claude writes the test.

The contract is strict: the completion must return a JSON object mapping
relative paths to file contents, including a `testcase.yaml` that parses and
declares at least one test — so the result runs under twister like everything
else. Anything less is rejected, not patched over.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import yamlmini
from .fit import Complete

_PROMPT = """Write a Zephyr ztest suite that verifies this intent on board {board}:
{goal}

Return ONLY a JSON object mapping relative file paths to file contents. It MUST
include: "testcase.yaml" (twister metadata with a tests: section), "src/main.c"
(a ztest using <zephyr/ztest.h>), "CMakeLists.txt", and "prj.conf" (with
CONFIG_ZTEST=y). The suite must run under `west twister` unmodified."""


@dataclass(frozen=True)
class WrittenTest:
    dest: str
    test_id: str
    files: tuple[str, ...]


def write_ztest(goal: str, board: str, dest: str | Path,
                complete: Complete) -> WrittenTest:
    raw = complete(_PROMPT.format(goal=goal, board=board))
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        files = json.loads(m.group(0) if m else raw)
    except Exception as exc:
        raise ValueError(f"test writer returned unparseable output: {exc}") from exc
    if not isinstance(files, dict) or "testcase.yaml" not in files:
        raise ValueError("test writer output must include testcase.yaml")

    # Validate BEFORE writing anything: testcase.yaml must parse and declare
    # at least one test, or twister could never gate this work.
    try:
        meta = yamlmini.load(files["testcase.yaml"])
    except Exception as exc:
        raise ValueError(f"testcase.yaml does not parse: {exc}") from exc
    tests = meta.get("tests") if isinstance(meta, dict) else None
    if not isinstance(tests, dict) or not tests:
        raise ValueError("testcase.yaml declares no tests")
    test_id = next(iter(tests))

    dest = Path(dest)
    written: list[str] = []
    for rel, content in files.items():
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError(f"unsafe path from test writer: {rel}")
        p = dest / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        written.append(rel)
    return WrittenTest(dest=str(dest), test_id=str(test_id),
                       files=tuple(sorted(written)))
