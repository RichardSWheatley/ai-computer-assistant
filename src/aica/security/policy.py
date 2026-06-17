"""SecurityPolicy — one object that ties the defenses together.

Decides which actions need human confirmation, enforces egress, and DLP-checks
outbound payloads. The orchestrator's `confirm` callback and the egress choke
points consult this so policy lives in one auditable place.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .dlp import DLPResult, scan_outbound
from .egress import EgressPolicy

# Action tiers that always require explicit human confirmation.
_CONFIRM_TIERS = {"outward_facing", "destructive"}


@dataclass
class SecurityPolicy:
    egress: EgressPolicy = field(default_factory=EgressPolicy)
    confirm_tiers: set[str] = field(default_factory=lambda: set(_CONFIRM_TIERS))
    block_outbound_secrets: bool = True

    @classmethod
    def local_only(cls) -> "SecurityPolicy":
        return cls(egress=EgressPolicy.local_only())

    # -- action gating ------------------------------------------------------
    def needs_confirmation(self, tier: str, *, untrusted_context: bool = False) -> bool:
        """High-risk tiers always confirm; action-provenance binding: if the
        step follows freshly-ingested untrusted content, even local writes do."""
        if tier in self.confirm_tiers:
            return True
        if untrusted_context and tier == "local_write":
            return True
        return False

    # -- egress -------------------------------------------------------------
    def allow_egress(self, url: str) -> bool:
        return self.egress.allows(url)

    def guard_egress(self, url: str) -> None:
        self.egress.check(url)

    # -- outbound DLP -------------------------------------------------------
    def guard_outbound(self, text: str) -> DLPResult:
        """Scan (and redact) a payload bound off-machine. With
        block_outbound_secrets, callers should refuse to send when not clean."""
        result = scan_outbound(text)
        return result
