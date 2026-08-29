"""Status echoes the last agent-activity line with its age. The owner's
live trace: a task 4m32s in still said 'done so far: just started' —
true (stage checkpoints are coarse) but useless while the agent is
mid-step. The narration RITA already streams is the fine-grained truth;
status must quote its latest line and how old it is."""

from __future__ import annotations

import re
import threading
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"


def make_supervisor(tmp_path):
    from rita.config import RitaConfig
    from rita.supervisor import Supervisor
    from rita.voice.tts import FakeTTS

    return Supervisor(rita_cfg=RitaConfig(workspace=str(WS),
                                          auto_setup=False,
                                          ai_routing=False),
                      config_path=tmp_path / "config", tts=FakeTTS(),
                      workdir=tmp_path / "work")


class TestStatusQuotesActivity:
    def test_running_status_quotes_the_last_activity_line(self, tmp_path):
        sup = make_supervisor(tmp_path)
        release = threading.Event()
        started = threading.Event()

        def work(ctl):
            started.set()
            release.wait(timeout=30)
            return "ok"

        sup.manager.submit("modify hello_world", work)
        assert started.wait(timeout=10)
        sup._activity("→ asking the coding agent…")
        text = sup._live_status()
        release.set()
        assert "asking the coding agent" in text
        assert re.search(r"last activity .*\d+s ago", text), text

    def test_activity_still_reaches_the_gui_sink(self, tmp_path):
        sup = make_supervisor(tmp_path)
        seen = []
        sup.on_activity = seen.append
        sup._activity("→ writing src/main.c (2/5)…")
        assert seen == ["→ writing src/main.c (2/5)…"]

    def test_idle_status_carries_no_stale_activity(self, tmp_path):
        sup = make_supervisor(tmp_path)
        sup._activity("← the coding agent replied in 18s")
        text = sup._live_status()
        assert "Nothing is running" in text
        assert "replied" not in text     # old narration never haunts idle
