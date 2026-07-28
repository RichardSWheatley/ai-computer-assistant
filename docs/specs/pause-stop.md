# Spec: PAUSE and RESUME/STOP (Fix 4)

## Controls

Two persistent controls (voice control words today; UI buttons bind to the
same TaskManager/speaker API):

- **PAUSE** halts speech instantly (position kept) and suspends task
  execution at the **next safe checkpoint**. **RESUME** continues both —
  speech from the kept position, the task from the checkpoint it paused at.
- **STOP** flushes the speech queue and cancels the current task at a safe
  boundary, reporting **partial results** (completed stages + artifacts).
  STOP is per-task: the TaskManager and learned state survive and new tasks
  are accepted immediately.

## Hardware operations are atomic

`west flash`, RTT capture, and power measurement are never interrupted
mid-operation. Checkpoints exist **only between pipeline stages** (the Fix 3
pipeline calls `ctl.checkpoint(stage)` after RESOLVE, BUILD, SIM_TEST). The
UI therefore shows "pausing after current step…" until the checkpoint is
reached, then "paused".

## Design

- `rita.core.tasks.TaskManager` — `submit(name, fn) -> TaskId`, `pause`,
  `resume`, `stop`, `state`, `report`, `wait_state`. Tasks run on worker
  threads; `fn(ctl)` receives a `TaskControl`.
- `TaskControl.checkpoint(completed_stage)` records progress, then: raises
  `TaskStopped` if a stop was requested; blocks (state `PAUSED`) if a pause
  was requested, until RESUME (or STOP, which raises). State machine:

```
PENDING -> RUNNING -> DONE | FAILED
RUNNING --pause--> PAUSING --checkpoint--> PAUSED --resume--> RUNNING
RUNNING | PAUSED --stop--> STOPPING --boundary--> STOPPED (partial report)
```

- Because pausing blocks the worker *inside* the run, RESUME continues
  exactly where execution stopped: a task paused after BUILD resumes into
  SIM_TEST **without rebuilding** — no replay logic, no re-entry.
- `rita.voice.tts.PausableSpeaker` wraps any `TextToSpeech`: text is split
  into sentence chunks spoken on a worker thread; PAUSE takes effect at the
  next chunk boundary (and calls the engine's `stop()` when it has one),
  keeping the queue position; RESUME continues from that position; STOP
  flushes the queue. Sub-300 ms responsiveness is architectural (short
  chunks + immediate engine stop).
- `make_control_handler(manager, speaker)` binds the router's `control`
  dispatches (Fix 1) to these APIs.

## Acceptance criteria (each is a test)

- PAUSE during BUILD: state is `PAUSING` until the stage completes, then
  `PAUSED`; RESUME continues into twister **without rebuilding** (the build
  runs exactly once).
- STOP mid-pipeline: state `STOPPED`, the report lists completed stages,
  and the TaskManager immediately accepts new tasks.
- STOP while PAUSED wakes the task and cancels it.
- PAUSE halts speech before the next chunk; RESUME picks up at the kept
  position with no chunk repeated or skipped; STOP flushes the queue.
- Voice control words ("pause", "resume", "stop") drive all of the above.
