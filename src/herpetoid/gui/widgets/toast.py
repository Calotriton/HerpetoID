"""A transient toast notification overlaid on a screen.

Non-modal and self-dismissing: it confirms an action (e.g. "Observation saved successfully") without
stealing focus or blocking headless test drivers the way a modal message box would.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    """A floating label anchored to the bottom-centre of its parent; auto-hides after a delay."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, duration_ms: int = 5000) -> None:
        """Show ``text`` bottom-centre over the parent and hide it after ``duration_ms``."""
        parent = self.parentWidget()
        if parent is None:
            return
        self.setText(text)
        width = max(260, min(560, parent.width() - 48))
        self.setFixedWidth(width)
        self.adjustSize()
        self.move((parent.width() - self.width()) // 2, parent.height() - self.height() - 24)
        self.show()
        self.raise_()
        self._timer.start(duration_ms)
