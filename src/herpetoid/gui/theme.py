"""Theme management: system / light / dark, applied via a Fusion palette."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(37, 37, 38)
    base = QColor(30, 30, 30)
    text = QColor(220, 220, 220)
    highlight = QColor(38, 121, 200)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, window)
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, window)
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    disabled = QColor(120, 120, 120)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return palette


class ThemeManager:
    """Applies a theme to the :class:`QApplication`."""

    def __init__(self, app: QApplication) -> None:
        self._app = app

    def apply(self, theme: str) -> str:
        """Apply ``'system'`` | ``'light'`` | ``'dark'``; returns the resolved theme."""
        resolved = self._resolve(theme)
        self._app.setStyle("Fusion")
        if resolved == "dark":
            self._app.setPalette(_dark_palette())
        else:
            self._app.setPalette(self._app.style().standardPalette())
        return resolved

    def _resolve(self, theme: str) -> str:
        if theme in ("light", "dark"):
            return theme
        scheme = self._app.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
