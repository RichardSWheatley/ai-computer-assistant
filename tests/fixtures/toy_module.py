"""A real child-process module used by the supervisor/registry tests.

Speaks the module RPC protocol via rita.modules.runtime.serve. Its version
is argv[1] so tests can install several versions of the same module.
"""

import os
import sys
import time

from rita.modules.runtime import serve

VERSION = sys.argv[1] if len(sys.argv) > 1 else "1.0.0"
STATE = {"value": None}


def start(params, emit):
    STATE["value"] = params.get("value")
    emit("progress", {"pct": 50})
    return {"started": True}


def status(params, emit):
    return {"value": STATE["value"], "version": VERSION}


def pause_at_checkpoint(params, emit):
    stage = params.get("stage", "BUILD")
    emit("checkpoint", {"stage": stage})
    return {"paused_at": stage}


def slow(params, emit):
    time.sleep(params.get("seconds", 2.0))
    return {"done": True}


def crash(params, emit):
    sys.stderr.write("boom: simulated module crash\n")
    sys.stderr.flush()
    os._exit(3)


def result(params, emit):
    return {"result": STATE["value"]}


if __name__ == "__main__":
    serve(name="toy", version=VERSION,
          handlers={"start": start, "status": status,
                    "pause_at_checkpoint": pause_at_checkpoint,
                    "slow": slow, "crash": crash, "result": result})
