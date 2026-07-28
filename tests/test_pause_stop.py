"""Fix 4: PAUSE / RESUME / STOP — task checkpoints and pausable speech."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
WS = FIXTURES / "zephyr_ws"
TW = FIXTURES / "twister"


def blinky_fit(_prompt: str = "") -> str:
    return json.dumps({"fit": "sample.basic.blinky", "reason": "fits"})


class SteppableWest:
    """FakeWest wrapper whose build() signals entry and waits for release —
    so tests decide exactly when the pipeline reaches its checkpoints."""

    def __init__(self, inner):
        self.inner = inner
        self.in_build = threading.Event()
        self.release_build = threading.Event()

    def build(self, app_dir, platform, outdir):
        self.in_build.set()
        assert self.release_build.wait(5), "test never released the build"
        return self.inner.build(app_dir, platform, outdir)

    def twister(self, **kw):
        return self.inner.twister(**kw)

    def generate_hardware_map(self, out):
        return self.inner.generate_hardware_map(out)


def make_pipeline(tmp_path, *, build_seq=("ok",), twister_seq=("pass.json",)):
    from rita.config import RitaConfig
    from rita.firmware.claude import FakeClaude
    from rita.firmware.index import VerificationIndex
    from rita.firmware.pipeline import IteratePipeline
    from rita.firmware.west import FakeWest

    fake = FakeWest(build_seq=list(build_seq), twister_seq=list(twister_seq),
                    fixtures_dir=TW)
    west = SteppableWest(fake)
    claude = FakeClaude(completions=[blinky_fit()])
    cfg = RitaConfig(workspace=str(WS))
    pipe = IteratePipeline(runner=west, claude=claude,
                           index=VerificationIndex.build(WS), cfg=cfg,
                           workdir=tmp_path / "work")
    return pipe, west, fake


def run_task(manager, pipe):
    return manager.submit(
        "blink", lambda ctl: pipe.run(goal="blink the led",
                                      board="apollo510_evb",
                                      terms=["led", "blinky"], ctl=ctl))


class TestTaskManager:
    def test_pause_after_build_resumes_into_twister_without_rebuilding(self, tmp_path):
        from rita.core.tasks import TaskManager
        manager = TaskManager()
        pipe, west, fake = make_pipeline(tmp_path)

        tid = run_task(manager, pipe)
        assert west.in_build.wait(5)
        manager.pause(tid)
        assert manager.state(tid) == "PAUSING"        # mid-op: never interrupted
        west.release_build.set()                      # build (atomic op) finishes
        assert manager.wait_state(tid, "PAUSED", timeout=5)
        assert len(fake.build_calls) == 1
        assert fake.twister_calls == []               # suspended before twister

        manager.resume(tid)
        assert manager.wait_state(tid, "DONE", timeout=5)
        assert len(fake.build_calls) == 1             # no rebuild on resume
        assert len(fake.twister_calls) == 1
        assert manager.report(tid).result.outcome == "green"

    def test_stop_reports_partial_results_and_manager_survives(self, tmp_path):
        from rita.core.tasks import TaskManager
        manager = TaskManager()
        pipe, west, fake = make_pipeline(tmp_path)

        tid = run_task(manager, pipe)
        assert west.in_build.wait(5)
        manager.stop(tid)
        west.release_build.set()
        assert manager.wait_state(tid, "STOPPED", timeout=5)
        rep = manager.report(tid)
        assert "RESOLVE" in rep.completed_stages
        assert "FINAL_BUILD" in rep.completed_stages
        assert "FINAL_TEST" not in rep.completed_stages  # cancelled at boundary

        # Per-task: the manager keeps accepting work.
        pipe2, west2, fake2 = make_pipeline(tmp_path / "second")
        west2.release_build.set()
        tid2 = run_task(manager, pipe2)
        assert manager.wait_state(tid2, "DONE", timeout=5)

    def test_stop_while_paused_wakes_and_cancels(self, tmp_path):
        from rita.core.tasks import TaskManager
        manager = TaskManager()
        pipe, west, fake = make_pipeline(tmp_path)

        tid = run_task(manager, pipe)
        assert west.in_build.wait(5)
        manager.pause(tid)
        west.release_build.set()
        assert manager.wait_state(tid, "PAUSED", timeout=5)
        manager.stop(tid)
        assert manager.wait_state(tid, "STOPPED", timeout=5)

    def test_crash_is_failed_not_fatal(self):
        from rita.core.tasks import TaskManager
        manager = TaskManager()

        def boom(ctl):
            raise RuntimeError("kaboom")

        tid = manager.submit("bad", boom)
        assert manager.wait_state(tid, "FAILED", timeout=5)
        assert "kaboom" in manager.report(tid).error


class BlockingTTS:
    """Speaks one chunk at a time, each gated by the test (deterministic).

    stop() models a real engine: it aborts the in-flight utterance, so that
    speak() returns without having spoken."""

    def __init__(self):
        self.spoken: list[str] = []
        self.gate = threading.Semaphore(0)
        self.stops = 0
        self.aborted = False

    def speak(self, text: str) -> None:
        assert self.gate.acquire(timeout=5), "test never released a chunk"
        if self.aborted:
            self.aborted = False
            return
        self.spoken.append(text)

    def stop(self) -> None:
        self.stops += 1
        self.aborted = True
        self.gate.release()      # the abort unblocks the in-flight utterance


class TestPausableSpeaker:
    def test_pause_keeps_position_resume_continues_stop_flushes(self):
        from rita.voice.tts import PausableSpeaker
        tts = BlockingTTS()
        spk = PausableSpeaker(tts)
        spk.say("One. Two. Three. Four.")

        tts.gate.release()                 # let chunk 1 out
        spk.wait_until(lambda: len(tts.spoken) == 1)
        spk.pause()                        # instant: engine stop + no next chunk
        assert tts.stops == 1
        tts.gate.release()                 # even released, chunk 2 must not play
        time.sleep(0.05)
        assert tts.spoken == ["One."]
        assert spk.position == 1           # position kept

        spk.resume()
        spk.wait_until(lambda: len(tts.spoken) == 2)
        assert tts.spoken == ["One.", "Two."]   # no repeat, no skip

        spk.stop()                         # flush the rest
        tts.gate.release()
        time.sleep(0.05)
        assert tts.spoken == ["One.", "Two."]
        assert spk.pending == 0

    def test_say_after_stop_starts_fresh(self):
        from rita.voice.tts import PausableSpeaker
        tts = BlockingTTS()
        spk = PausableSpeaker(tts)
        spk.say("One. Two.")
        spk.stop()
        spk.say("Fresh.")
        tts.gate.release()
        spk.wait_until(lambda: "Fresh." in tts.spoken)


class TestControlWords:
    def test_voice_control_words_drive_manager_and_speaker(self, tmp_path):
        from rita.core.tasks import TaskManager, make_control_handler
        from rita.routing.model import Utterance
        from rita.routing.router import route
        from rita.routing.vocabulary import Vocabulary
        from rita.voice.tts import PausableSpeaker

        manager = TaskManager()
        tts = BlockingTTS()
        speaker = PausableSpeaker(tts)
        handler = make_control_handler(manager, speaker)
        vocab = Vocabulary.seed()

        pipe, west, fake = make_pipeline(tmp_path)
        tid = run_task(manager, pipe)
        assert west.in_build.wait(5)

        said = handler(route(Utterance.from_text("pause"), vocab))
        assert "paus" in said.lower()
        west.release_build.set()
        assert manager.wait_state(tid, "PAUSED", timeout=5)

        said = handler(route(Utterance.from_text("resume"), vocab))
        assert manager.wait_state(tid, "DONE", timeout=5)

        said = handler(route(Utterance.from_text("stop"), vocab))
        assert "stop" in said.lower() or "nothing" in said.lower()
