"""Secret vault: store/get/delete, reference resolution, and Graph integration."""

import pytest

from aica.business.graph import GraphClient
from aica.security.vault import MemoryBackend, SecretVault, is_ref


def _vault():
    return SecretVault(backend=MemoryBackend())


def test_set_get_delete_exists():
    v = _vault()
    assert not v.exists("GRAPH_TOKEN")
    v.set("GRAPH_TOKEN", "secret-123")
    assert v.exists("GRAPH_TOKEN") and v.get("GRAPH_TOKEN") == "secret-123"
    v.delete("GRAPH_TOKEN")
    assert not v.exists("GRAPH_TOKEN")


def test_resolve_reference_and_passthrough():
    v = _vault()
    v.set("GRAPH_TOKEN", "secret-123")
    assert is_ref("vault:GRAPH_TOKEN") and not is_ref("plain")
    assert v.resolve("vault:GRAPH_TOKEN") == "secret-123"
    assert v.resolve("plain-value") == "plain-value"
    assert v.resolve(None) is None


def test_resolve_missing_secret_fails_loud():
    with pytest.raises(KeyError):
        _vault().resolve("vault:NOPE")


def test_graph_client_resolves_token_reference():
    v = _vault()
    v.set("GRAPH_TOKEN", "real-bearer")
    g = GraphClient(token="vault:GRAPH_TOKEN", session=object(), vault=v)
    assert g.token == "real-bearer"   # reference resolved, not stored raw
