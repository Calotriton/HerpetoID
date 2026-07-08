"""A placeholder screen for views not yet implemented."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderScreen(QWidget):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.screen_name = name
        layout = QVBoxLayout(self)
        label = QLabel(f"{name}\n\n(coming soon)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: palette(mid); font-size: 16px;")
        layout.addWidget(label)
