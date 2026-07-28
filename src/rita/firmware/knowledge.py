"""The Zephyr knowledge pack: shipped conventions, deterministically served.

Curated from the official docs (each topic cites its source + research
date). Retrieval is keyword matching over the index — no LLM anywhere.
The pack carries HOW-Zephyr-works knowledge; facts about the user's
install still come only from the workspace and SDK on disk.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Sequence

_ROOT = Path(__file__).resolve().parent / "data" / "knowledge"


@lru_cache(maxsize=1)
def _index() -> dict:
    return json.loads((_ROOT / "index.json").read_text())["topics"]


def list_topics() -> list[dict]:
    return [{"topic": name, **meta} for name, meta in _index().items()]


def get_topic(name: str) -> str | None:
    if name not in _index():
        return None
    path = _ROOT / f"{name}.md"
    return path.read_text() if path.exists() else None


def match_topics(terms: Sequence[str], limit: int = 3) -> list[str]:
    """Topics ranked by keyword overlap with the given terms. Pure data."""
    want = {t.lower() for t in terms if t}
    scored: list[tuple[int, str]] = []
    for name, meta in _index().items():
        keywords = {k.lower() for k in meta.get("keywords", [])}
        keywords.add(name.lower())
        score = len(want & keywords)
        if score > 0:
            scored.append((score, name))
    scored.sort(key=lambda sn: (-sn[0], sn[1]))
    return [name for _, name in scored[:limit]]


def summary_for(terms: Sequence[str]) -> str | None:
    """One matched topic's summary — for chat's how-do-I answers."""
    matched = match_topics(terms, limit=1)
    if not matched:
        return None
    meta = _index()[matched[0]]
    return f"{meta['title']}: {meta['summary']}"


def notes_for(terms: Sequence[str], max_chars: int = 6000) -> str:
    """A bounded knowledge block for prompt enrichment (scaffold / test
    authorship). Whole topics are included until the budget runs out."""
    parts: list[str] = []
    used = 0
    for name in match_topics(terms, limit=4):
        text = get_topic(name) or ""
        if used + len(text) > max_chars:
            remaining = max_chars - used
            if remaining < 200:
                break
            text = text[:remaining]
        parts.append(text.strip())
        used += len(text)
        if used >= max_chars:
            break
    return "\n\n---\n\n".join(parts)[:max_chars]
