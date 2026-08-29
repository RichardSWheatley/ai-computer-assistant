"""Path pickers: every box that takes a path gets a browse button.

Nobody should hand-type C:\\ paths (the owner's request). One shared
helper so every picker looks and behaves the same: a compact
folder-icon button beside the field; Cancel leaves the field alone;
mode "command" quotes spaced paths so `split_command` keeps them whole.
"""

from __future__ import annotations

from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QPushButton,
                               QWidget)


def make_picker(parent, line_edit, *, mode: str = "dir",
                caption: str = "Choose", name_filter: str = "") -> QPushButton:
    """A browse button bound to `line_edit`. mode: dir | file | command."""
    from .icons import folder_icon
    from .theme import TEXT_DIM

    btn = QPushButton(parent, objectName="pickButton")
    btn.setIcon(folder_icon(TEXT_DIM))
    btn.setToolTip(f"{caption} — browse…")

    def pick() -> None:
        if mode == "dir":
            path = QFileDialog.getExistingDirectory(parent, caption)
        else:
            path, _ = QFileDialog.getOpenFileName(parent, caption, "",
                                                  name_filter)
        if not path:
            return                       # Cancel never clobbers the field
        if mode == "command" and " " in path:
            path = f'"{path}"'
        line_edit.setText(path)

    btn.clicked.connect(pick)
    return btn


def row_with(parent, line_edit, button: QPushButton) -> QWidget:
    """The field and its (already-made) picker as one widget — for
    QFormLayout rows where the caller keeps a handle on the button."""
    box = QWidget(parent)
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    h.addWidget(line_edit, 1)
    h.addWidget(button)
    return box


def with_picker(parent, line_edit, **kw) -> QWidget:
    """The field and its picker as one widget — for QFormLayout rows."""
    return row_with(parent, line_edit, make_picker(parent, line_edit, **kw))
