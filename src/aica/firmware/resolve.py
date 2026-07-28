"""Verification resolution (Fix 2): find-or-write, in that order.

1. Ask the index (pure data).  2. Claude judges fit among the index's top
matches.  3. No fit -> Claude writes a ztest, validated before acceptance.
The resolver never skips a step and never lets Claude schedule anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from .fit import Complete, judge_fit
from .index import IndexEntry, VerificationIndex
from .testwriter import WrittenTest, write_ztest


@dataclass(frozen=True)
class Resolution:
    method: Literal["existing", "written"]
    entry: IndexEntry | None = None      # method == "existing"
    written: WrittenTest | None = None   # method == "written"
    reason: str = ""


def resolve_verification(*, goal: str, board: str, terms: Sequence[str],
                         index: VerificationIndex, complete: Complete,
                         write_dir: str | Path,
                         workspace: str | Path | None = None,
                         limit: int = 10) -> Resolution:
    candidates = index.find(board, terms, limit=limit)
    if candidates:
        decision = judge_fit(goal, candidates, complete, workspace=workspace)
        if decision.entry is not None:
            return Resolution(method="existing", entry=decision.entry,
                              reason=decision.reason)
    written = write_ztest(goal, board, write_dir, complete)
    return Resolution(method="written", written=written,
                      reason="no indexed suite verifies this intent")
