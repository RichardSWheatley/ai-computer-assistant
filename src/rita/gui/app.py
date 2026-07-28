"""GUI entry point: `rita-app` (windowed) / `python -m rita.gui`."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("RITA's GUI needs PySide6: pip install 'rita[gui]'")
        return 2

    from ..supervisor import Supervisor
    from .main_window import RitaWindow
    from .presenter import GuiPresenter
    from .theme import QSS

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("RITA")
    app.setStyleSheet(QSS)
    presenter = GuiPresenter(Supervisor())
    window = RitaWindow(presenter)
    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover - real GUI loop
    sys.exit(main())
