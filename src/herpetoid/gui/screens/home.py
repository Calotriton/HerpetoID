"""Home screen: a welcome / landing view."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class HomeScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)

        title = QLabel("HerpetoID")
        title.setStyleSheet("font-size: 30px; font-weight: 700;")
        subtitle = QLabel(
            "Non-invasive individual identification of wildlife from natural body patterns."
        )
        subtitle.setStyleSheet("font-size: 14px; color: palette(mid);")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(
            QLabel("Use the sidebar to manage projects, import images, and identify individuals.")
        )
        layout.addStretch(1)
