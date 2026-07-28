"""Default-deny network egress policy.

The agent may only reach an explicit allowlist of hosts (your model endpoint,
Microsoft Graph, etc.). Even a successful prompt injection cannot exfiltrate to
an attacker-controlled server, because the destination isn't allowed. In
local-only mode the allowlist is empty — nothing leaves the machine.

This is a policy object; wire it into every outbound call site (web fetch, cloud
planner, Graph client) so there is one choke point. Subdomains of an allowed
host are permitted; everything else is denied.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

# Sensible defaults for an assistant that uses Claude + Microsoft 365.
DEFAULT_ALLOW = {
    "api.anthropic.com",
    "graph.microsoft.com",
    "login.microsoftonline.com",
}


@dataclass
class EgressPolicy:
    allow: set[str] = field(default_factory=lambda: set(DEFAULT_ALLOW))
    default_deny: bool = True

    @classmethod
    def local_only(cls) -> "EgressPolicy":
        return cls(allow=set(), default_deny=True)

    def _host(self, url: str) -> str:
        host = urlparse(url).hostname or ""
        return host.lower().rstrip(".")

    def allows(self, url: str) -> bool:
        host = self._host(url)
        if not host:
            return False
        for allowed in self.allow:
            a = allowed.lower()
            if host == a or host.endswith("." + a):
                return True
        return not self.default_deny

    def check(self, url: str) -> None:
        """Raise PermissionError if the URL is not permitted."""
        if not self.allows(url):
            raise PermissionError(f"egress denied by policy: {url}")
