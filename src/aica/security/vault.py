"""Secret vault — keep credentials in the OS keychain, never in prompts/config.

Secrets (model API keys, Graph tokens) live here, accessed only by the trusted/
privileged side. Configs and prompts hold *references* like ``vault:GRAPH_TOKEN``
that resolve to the secret at the point of use — so a credential is never placed
in a prompt, a screenshot, or the sandboxed worker's environment (the sandbox
already scrubs env). This is the secret-isolation principle: injected code can't
read what it never receives.

Backends: the OS keychain via ``keyring`` (preferred, guarded) with an in-memory
fallback for dev/CI. Both expose the same interface.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

SERVICE = "aica"
_REF_PREFIX = "vault:"


@runtime_checkable
class VaultBackend(Protocol):
    def set(self, name: str, value: str) -> None: ...
    def get(self, name: str) -> str | None: ...
    def delete(self, name: str) -> None: ...


class MemoryBackend:
    """Process-local store — for dev/CI only (not persisted)."""

    def __init__(self) -> None:
        self._d: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        self._d[name] = value

    def get(self, name: str) -> str | None:
        return self._d.get(name)

    def delete(self, name: str) -> None:
        self._d.pop(name, None)


class KeyringBackend:  # pragma: no cover - needs the keyring package + a backend
    def __init__(self, service: str = SERVICE) -> None:
        import keyring  # type: ignore
        self._keyring = keyring
        self.service = service

    def set(self, name: str, value: str) -> None:
        self._keyring.set_password(self.service, name, value)

    def get(self, name: str) -> str | None:
        return self._keyring.get_password(self.service, name)

    def delete(self, name: str) -> None:
        try:
            self._keyring.delete_password(self.service, name)
        except Exception:
            pass


def _default_backend() -> VaultBackend:
    try:  # pragma: no cover - depends on environment
        return KeyringBackend()
    except Exception:
        return MemoryBackend()


class SecretVault:
    def __init__(self, backend: VaultBackend | None = None) -> None:
        self.backend = backend or _default_backend()

    def set(self, name: str, value: str) -> None:
        self.backend.set(name, value)

    def get(self, name: str) -> str | None:
        return self.backend.get(name)

    def delete(self, name: str) -> None:
        self.backend.delete(name)

    def exists(self, name: str) -> bool:
        return self.get(name) is not None

    def resolve(self, value: str | None) -> str | None:
        """Resolve a 'vault:NAME' reference to its secret; pass plain values through.

        Raises KeyError if a referenced secret is missing — fail loud rather than
        silently sending an empty credential.
        """
        if not value or not value.startswith(_REF_PREFIX):
            return value
        name = value[len(_REF_PREFIX):]
        secret = self.get(name)
        if secret is None:
            raise KeyError(f"secret not found in vault: {name}")
        return secret


def is_ref(value: str | None) -> bool:
    return bool(value) and value.startswith(_REF_PREFIX)
