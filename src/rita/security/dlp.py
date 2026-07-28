"""Outbound data-loss prevention: catch secrets before they leave the machine.

Scan any payload bound for the cloud / network for high-signal secrets (API
keys, tokens, private keys). Used as a last-line check at egress choke points;
either block the call or redact the matches. Conservative by design — high
precision so it doesn't mangle normal content.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PATTERNS = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "google_key": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "slack_token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer": re.compile(r"[Bb]earer\s+[A-Za-z0-9._\-]{20,}"),
}


@dataclass
class DLPResult:
    findings: list[str] = field(default_factory=list)
    redacted: str = ""

    @property
    def clean(self) -> bool:
        return not self.findings


def scan_outbound(text: str) -> DLPResult:
    if not text:
        return DLPResult(redacted=text or "")
    findings: list[str] = []
    redacted = text
    for name, pat in _PATTERNS.items():
        if pat.search(redacted):
            findings.append(name)
            redacted = pat.sub(f"[REDACTED:{name}]", redacted)
    return DLPResult(findings=findings, redacted=redacted)
