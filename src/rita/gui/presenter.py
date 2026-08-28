"""The GUI's brain-stem: headless presenter over the Supervisor.

The window binds plain callables (`on_user`, `on_reply`, `on_screen`,
`on_task`, `on_status`) to Qt signals; everything else — quote stripping,
routing, the speech/screen split, pause/stop semantics, task-completion
announcements, workspace sync — happens here, testable without a display.
"""

from __future__ import annotations

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from ..config import save_rita_config
from ..firmware.sync import SyncResult, sync_workspace
from ..routing.vocabulary import Vocabulary
from ..supervisor import Supervisor
from ..ui.channels import split_response

_QUOTES = "\"'“”‘’"


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    name: str
    state: str
    outcome: str | None = None       # PipelineReport outcome when DONE
    completed_stages: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatusInfo:
    workspace: str | None
    zephyr_version: str | None
    modules: int
    coder_cli: bool                  # coding agent configured + resolvable
    sdk_version: str | None = None


def _noop(*_a, **_k) -> None:
    return None


def strip_quotes(text: str) -> str:
    """The user quotes commands; RITA routes the contents."""
    return text.strip().strip(_QUOTES).strip()


class GuiPresenter:
    def __init__(self, supervisor: Supervisor,
                 poll_interval: float = 0.05) -> None:
        self.sup = supervisor
        self.on_user = _noop      # (text) echoed user entry, unquoted
        self.on_reply = _noop     # (speech) speech-channel text
        self.on_screen = _noop    # (text) screen-channel artifacts
        self.on_task = _noop      # (TaskSnapshot) state transitions
        self.on_status = _noop    # (StatusInfo)
        self._poll = poll_interval
        self._seen_states: dict[str, str] = {}
        self._closing = threading.Event()
        threading.Thread(target=self._watch_tasks, daemon=True,
                         name="gui-task-watch").start()

    # --- input ---------------------------------------------------------------

    def submit_text(self, text: str) -> None:
        clean = strip_quotes(text)
        if not clean:
            return
        self.on_user(clean)
        threading.Thread(target=self._handle, args=(clean,), daemon=True,
                         name="gui-handle").start()

    def _handle(self, clean: str) -> None:
        said = self.sup.shell.handle_typed(clean)
        self._emit_reply(said)

    def _emit_reply(self, said: str) -> None:
        if not said:
            return
        reply = split_response(said)
        self.on_reply(reply.speech)
        if reply.screen.strip() != reply.speech.strip():
            self.on_screen(reply.screen)
        if self.sup.speaker is not None:
            self.sup.speaker.say(reply.speech)

    # --- the two persistent buttons (Fix 4) ----------------------------------

    def _control(self, word: str) -> None:
        from ..routing.model import Utterance
        from ..routing.router import route

        d = route(Utterance.from_text(word), self.sup.shell.vocab,
                  self.sup.cfg.assistant_name)
        said = self.sup.shell.dispatch(d)
        self._emit_reply(said)

    def pause(self) -> None:
        self._control("pause")

    def resume(self) -> None:
        self._control("resume")

    def stop(self) -> None:
        self._control("stop")

    # --- task announcements --------------------------------------------------

    def _watch_tasks(self) -> None:
        while not self._closing.wait(self._poll):
            for tid in self.sup.manager.tasks():
                rep = self.sup.manager.report(tid)
                if self._seen_states.get(tid) == rep.state:
                    continue
                self._seen_states[tid] = rep.state
                outcome = getattr(rep.result, "outcome", None)
                self.on_task(TaskSnapshot(
                    id=rep.id, name=rep.name, state=rep.state, outcome=outcome,
                    completed_stages=rep.completed_stages))
                if rep.state in ("DONE", "STOPPED", "FAILED"):
                    self._announce_finished(tid, rep)

    def _announce_finished(self, tid: str, rep) -> None:
        self._emit_reply(self.sup.task_summary(tid))
        result = rep.result
        if result is not None and getattr(result, "stages", None):
            lines = [f"[{s.stage}] {s.outcome}: {s.detail}" for s in result.stages]
            for stage in result.stages:
                for f in stage.failures:
                    lines.append(f.describe())
            self.on_screen("\n".join(lines))

    # --- workspace + status --------------------------------------------------

    def sync(self, path: str, hw_map: str | None = None) -> SyncResult:
        result = sync_workspace(path, hw_map=hw_map)
        self.sup.cfg.workspace = path
        if hw_map:
            self.sup.cfg.hardware_map = hw_map
        save_rita_config(self.sup.cfg, self.sup.config_path)
        self.sup._facts.clear()                       # facts changed
        self.sup.shell.vocab = Vocabulary.load()      # synced boards feed routing
        self.on_status(self.status())
        return result

    def _coder_available(self) -> bool:
        """The seam is honest: available only when a command is configured
        AND its executable resolves (PATH or a real file)."""
        cmd = self.sup.cfg.coder_command
        if self.sup._coder is not None:
            return True                       # injected worker (tests/modules)
        if not cmd:
            return False
        from ..firmware.static_check import split_command

        argv = split_command(cmd)
        exe = argv[0] if argv else ""
        return bool(exe) and (shutil.which(exe) is not None
                              or Path(exe).exists())

    def status(self) -> StatusInfo:
        from ..firmware.workspace import read_sdk_info, read_workspace_info

        zephyr_version = None
        if self.sup.cfg.workspace and Path(self.sup.cfg.workspace).exists():
            zephyr_version = read_workspace_info(
                self.sup.cfg.workspace)["zephyr_version"]
        sdk = read_sdk_info()
        return StatusInfo(
            workspace=self.sup.cfg.workspace,
            zephyr_version=zephyr_version,
            modules=len(self.sup.registry.discover()),
            coder_cli=self._coder_available(),
            sdk_version=sdk["version"] if sdk else None)

    def close(self) -> None:
        self._closing.set()
