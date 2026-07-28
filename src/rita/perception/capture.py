"""Screen capture via mss (lazy, guarded).

Returns the path to a PNG plus its pixel size, or None if no capture backend is
available (headless). Capture is the expensive part of perception, so callers
should prefer the accessibility tree and only capture when they need pixels.
"""

from __future__ import annotations

import os


def capture_screen(out_dir: str | None = None) -> tuple[str, tuple[int, int]] | None:
    try:  # pragma: no cover - needs a display + optional dep
        import mss  # type: ignore
        import mss.tools  # type: ignore
    except Exception:
        return None
    if out_dir is None:  # pragma: no cover - resolved lazily with a display
        from ..home import screens_dir

        out_dir = str(screens_dir())
    try:  # pragma: no cover - needs a display
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "frame.png")
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # primary monitor
            shot = sct.grab(monitor)
            mss.tools.to_png(shot.rgb, shot.size, output=path)
            return path, (shot.size.width, shot.size.height)
    except Exception:
        return None
