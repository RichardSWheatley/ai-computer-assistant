"""Security layer.

The central principle: the agent has a TRUSTED control plane (the user's goal +
this system's policy) and an UNTRUSTED data plane (everything it perceives —
screen, email, web, files, tool outputs). Untrusted content is data to reason
about, never instructions to obey. This package enforces that boundary plus
egress control, outbound DLP, and injection detection. See docs/SECURITY.md.
"""
