"""The router's domain vocabulary: boards, samples, peripherals.

Board names come from boards.json — the synced one in ~/.rita/ when present,
else the packaged seed — so "anything naming a board is work" is grounded in
real data, not model judgment. Matching is phrase matching over normalized
text (aliases may contain spaces).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .model import normalize

# Before the first workspace sync there is no index; these seeds keep the
# router functional out of the box. `rita sync` supersedes them.
SAMPLE_SEED = ("blinky", "hello world", "hello_world", "button",
               "synchronization", "philosophers")
PERIPHERAL_SEED = ("led", "gpio", "uart", "i2c", "spi", "pwm", "adc",
                   "timer", "watchdog", "ble", "wifi", "ethernet",
                   "mspi", "psram", "qspi", "ospi", "flash", "dma")

_SEED_PATH = Path(__file__).resolve().parent.parent / "firmware" / "data" / "boards.seed.json"


def _phrase_in(phrase: str, norm_text: str) -> bool:
    return re.search(rf"(?:^| ){re.escape(phrase)}(?: |$)", norm_text) is not None


@dataclass(frozen=True)
class Vocabulary:
    # canonical board name -> every phrase that names it (canonical included)
    boards: dict[str, tuple[str, ...]] = field(default_factory=dict)
    samples: tuple[str, ...] = ()
    peripherals: tuple[str, ...] = ()

    @classmethod
    def from_boards_json(cls, data: dict, *, samples: tuple[str, ...] = SAMPLE_SEED,
                         peripherals: tuple[str, ...] = PERIPHERAL_SEED) -> "Vocabulary":
        boards: dict[str, tuple[str, ...]] = {}
        for name, info in data.get("boards", {}).items():
            phrases = {normalize(name)}
            phrases.update(normalize(a) for a in info.get("aliases", []))
            boards[name] = tuple(sorted(phrases, key=len, reverse=True))
        return cls(boards=boards, samples=tuple(normalize(s) for s in samples),
                   peripherals=tuple(normalize(p) for p in peripherals))

    @classmethod
    def seed(cls) -> "Vocabulary":
        return cls.from_boards_json(json.loads(_SEED_PATH.read_text()))

    @classmethod
    def load(cls) -> "Vocabulary":
        """The synced ~/.rita/boards.json when present, else the seed."""
        from ..home import boards_json_path

        p = boards_json_path()
        if p.exists():
            return cls.from_boards_json(json.loads(p.read_text()))
        return cls.seed()

    # --- lookups (over normalized text) ------------------------------------

    def find_board(self, norm_text: str) -> str | None:
        for name, phrases in self.boards.items():
            if any(_phrase_in(p, norm_text) for p in phrases):
                return name
        return None

    def find_sample(self, norm_text: str) -> str | None:
        for s in self.samples:
            if _phrase_in(s, norm_text):
                return s
        return None

    def find_peripheral(self, norm_text: str) -> str | None:
        for p in self.peripherals:
            if _phrase_in(p, norm_text):
                return p
        return None
