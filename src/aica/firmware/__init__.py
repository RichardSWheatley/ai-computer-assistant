"""Zephyr-workspace capabilities: boards, verification index, iterate loop.

The workspace itself lives on the user's machine (path in ~/.rita/config);
this package only ever touches it through explicit paths and subprocess
seams, so everything here is testable against fixtures.
"""
