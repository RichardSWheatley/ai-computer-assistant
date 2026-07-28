"""Shipped module processes: thin RPC wrappers over the capability seams.

Each file is runnable (`python -m aica.modules_impl.<name>`) and serves the
module protocol via aica.modules.runtime. Heavy backends stay lazy — a
module only imports its engine when a call arrives.
"""
