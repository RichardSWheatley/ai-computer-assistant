"""RITA's GUI: a native Qt app (PySide6) over a headless presenter.

Every behavior lives in `presenter.GuiPresenter` (plain Python, fully
tested without a display); the Qt widgets bind to it and stay thin. The
`gui` optional extra installs PySide6; the packaged app ships with it.
"""
