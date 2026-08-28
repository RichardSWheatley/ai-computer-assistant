# Voice in the GUI: the microphone lands in the app

RITA's voice engine (mic → Whisper STT → wake gate → router → two-channel
reply → TTS) has been complete and tested since Fix 1/Fix 5 — but only the
CLI `talk` path ever opened the microphone. That violates the product
rule: **nothing runs via command line**. This spec threads listening into
the installed app.

## Behavior

- `RitaConfig.voice_enabled: bool = False`, persisted like every other
  setting. The Settings checkbox reflects it, saves it, and applies it
  immediately — no restart.
- `GuiPresenter.start_voice()` / `stop_voice()` / `voice_active`. Voice
  runs on a background thread owned by the presenter (headless-testable;
  the Qt window only reflects state). Backends (recorder, STT, TTS) are
  injectable; the real ones are built lazily.
- Every spoken utterance flows through the SAME `RouterShell` as typed
  input: wake gate first ("hello Rita" / the configured name), then the
  deterministic router. No second routing path.
- Replies use the existing channel split: at most two sentences spoken
  through the PausableSpeaker (Pause still halts speech instantly);
  code/logs land in the screen pane, never in audio.
- Transcript honesty: an utterance RITA ignored while asleep leaves no
  trace; an answered one shows what was heard (🎤) and the reply.
- "stop listening" / "goodbye" put the wake gate back to sleep — the mic
  keeps listening for the wake word only; the checkbox stays on.
- Missing voice deps are an honest, named failure: `start_voice()`
  reports what's missing and how to get it, `voice_active` stays False,
  the checkbox does not silently pretend.
- On launch, `voice_enabled` starts listening automatically.

## Acceptance criteria

- `voice_enabled` round-trips through config save/load.
- Fakes end-to-end: wake greeting → "Yes?" spoken; a follow-up question
  is heard, echoed to the transcript, answered, and spoken.
- An utterance while asleep produces no transcript entry and no speech.
- A stop phrase returns the gate to sleep: the next command without the
  wake word is ignored; the wake word wakes it again.
- `stop_voice()` ends the listen thread promptly.
- With unavailable backends, `start_voice()` returns False, reports the
  reason, and `voice_active` is False.
