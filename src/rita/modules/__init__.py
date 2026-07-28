"""Versioned module processes (Fix 6).

The supervisor is thin; every capability is a separately versioned child
process under ~/.rita/modules/<name>/<version>/ speaking newline JSON-RPC
over stdio — the same wire shape as the legacy worker protocol, upgraded
with a handshake, per-call timeouts, and async events.
"""
