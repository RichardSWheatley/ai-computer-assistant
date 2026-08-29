"""Suite-wide isolation: no test may touch the real ~/.rita.

Launch auto-setup made a stray real-home dependency an active hazard:
a window test that forgets to isolate RITA_HOME kicks off REAL installs
(git clones, downloads) into the developer's home from a background
thread — and a machine that already HAS ~/.rita content changes what
tests observe. Every test gets a private RITA_HOME; a test that needs
its own sets it later (its monkeypatch wins over this fixture's).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_rita_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("RITA_HOME",
                       str(tmp_path_factory.mktemp("rita-home")))
