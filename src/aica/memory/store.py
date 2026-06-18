"""A simple, persistent memory store with keyword recall and a RAG hook.

Namespaced records (facts / preferences / episodic) persisted as JSON. Recall is
keyword-overlap by default; pass an `embedder` (text -> vector) to switch to
semantic cosine recall without changing callers. Satisfies the MemoryStore
Protocol in core.interfaces (remember / recall).
"""

from __future__ import annotations

import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass, field

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class MemoryRecord:
    key: str
    value: str
    namespace: str = "facts"
    ts: float = field(default_factory=time.time)


class MemoryStore:
    def __init__(self, path: str | None = None, embedder=None) -> None:
        self.path = path
        self.embedder = embedder           # optional callable(text) -> list[float]
        self.records: list[MemoryRecord] = []
        self._vectors: dict[str, list[float]] = {}
        self._load()

    # -- write --------------------------------------------------------------
    def remember(self, key: str, value: str, namespace: str = "facts") -> None:
        # upsert by (namespace, key)
        self.records = [r for r in self.records
                        if not (r.key == key and r.namespace == namespace)]
        rec = MemoryRecord(key=key, value=value, namespace=namespace)
        self.records.append(rec)
        if self.embedder is not None:
            self._vectors[self._vkey(rec)] = self.embedder(value)
        self._persist()

    # -- read ---------------------------------------------------------------
    def recall(self, query: str, k: int = 5, namespace: str | None = None) -> list[str]:
        pool = [r for r in self.records
                if namespace is None or r.namespace == namespace]
        if not pool:
            return []
        if self.embedder is not None:
            qv = self.embedder(query)
            scored = [(_cosine(qv, self._vectors.get(self._vkey(r), [])), r)
                      for r in pool]
        else:
            qt = _tokens(query)
            scored = [(len(qt & _tokens(r.key + " " + r.value)), r) for r in pool]
        scored.sort(key=lambda s: s[0], reverse=True)
        return [r.value for score, r in scored if score > 0][:k]

    def all(self, namespace: str | None = None) -> list[MemoryRecord]:
        return [r for r in self.records
                if namespace is None or r.namespace == namespace]

    # -- persistence --------------------------------------------------------
    def _vkey(self, rec: MemoryRecord) -> str:
        return f"{rec.namespace}::{rec.key}"

    def _persist(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            json.dump([asdict(r) for r in self.records], f, indent=2)

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path) as f:
                data = json.load(f)
            self.records = [MemoryRecord(**d) for d in data]
            if self.embedder is not None:
                for r in self.records:
                    self._vectors[self._vkey(r)] = self.embedder(r.value)
        except Exception:
            self.records = []
