"""Test authorship (Fix 2, step 3): no index match -> the coding agent writes the test.

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


_UNITY_PROMPT = """Write host-run Unity unit tests for this goal: {goal}

Test EVERY function below for its input and output parameters — valid
values, boundary values, and invalid values that the function must reject
(each function restricts or validates its parameters before executing):

{functions}

Return ONLY a JSON object mapping relative file paths to file contents.
Each test file MUST include "unity.h" (never ztest), define at least one
test_<function_name> test per function above, and provide a main() calling
UNITY_BEGIN/RUN_TEST/UNITY_END. Tests compile on the host with the sources
under test — no Zephyr, no hardware."""


def write_unity_tests(goal: str, functions, dest: str | Path,
                      complete: Complete) -> WrittenTest:
    """Unit-test authorship: every listed function must be covered.
    Deterministically validated before acceptance."""
    listing = "\n".join(f"- {f.name}  ({f.file}:{f.line})" for f in functions)
    raw = complete(_UNITY_PROMPT.format(goal=goal, functions=listing))
    try:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        files = json.loads(m.group(0) if m else raw)
    except Exception as exc:
        raise ValueError(f"unit-test writer returned unparseable output: {exc}") from exc
    if not isinstance(files, dict) or not files:
        raise ValueError("unit-test writer returned no files")
    corpus = "\n".join(str(v) for v in files.values())
    if "ztest" in corpus:
        raise ValueError("unit tests must be Unity host tests, not ztest")
    if "unity.h" not in corpus:
        raise ValueError("unit tests must include unity.h")
    uncovered = [f.name for f in functions if f"test_{f.name}" not in corpus]
    if uncovered:
        raise ValueError("functions without unit tests: " + ", ".join(uncovered))

    dest = Path(dest)
    written: list[str] = []
    for rel, content in files.items():
        rel_path = Path(rel)
        if rel_path.is_absolute() or ".." in rel_path.parts:
            raise ValueError(f"unsafe path from unit-test writer: {rel}")
        p = dest / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content))
        written.append(rel)
    return WrittenTest(dest=str(dest), test_id="unit",
                      files=tuple(sorted(written)))


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
