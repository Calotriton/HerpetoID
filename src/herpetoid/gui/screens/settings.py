"""Settings screen: appearance (mode + style preset, applied live) and identification defaults."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from herpetoid.gui.state import AppState
from herpetoid.gui.theme import ThemeManager, available_styles

_THEMES = (("System", "system"), ("Light", "light"), ("Dark", "dark"))


def _swatch(color: str, size: int = 14) -> QIcon:
    """A round accent-color dot used to preview a style in the picker."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pixmap)


class SettingsScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        settings = state.settings.settings

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        appearance = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance)
        self.theme_combo = QComboBox()
        for label, value in _THEMES:
            self.theme_combo.addItem(label, value)
        index = self.theme_combo.findData(settings.theme)
        self.theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self.theme_combo.currentIndexChanged.connect(self._on_appearance_changed)
        appearance_form.addRow("Mode", self.theme_combo)

        self.style_combo = QComboBox()
        for style in available_styles():
            self.style_combo.addItem(_swatch(style.accent), style.name, style.style_id)
        index = self.style_combo.findData(settings.style)
        self.style_combo.setCurrentIndex(index if index >= 0 else 0)
        self.style_combo.currentIndexChanged.connect(self._on_appearance_changed)
        appearance_form.addRow("Style", self.style_combo)

        hint = QLabel("Changes apply immediately and are remembered.")
        hint.setStyleSheet("color: palette(mid); font-size: 12px;")
        appearance_form.addRow("", hint)
        layout.addWidget(appearance)

        identification = QGroupBox("Identification")
        identification_form = QFormLayout(identification)
        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 20)
        self.top_k_spin.setValue(settings.default_top_k)
        self.top_k_spin.valueChanged.connect(self._on_top_k_changed)
        identification_form.addRow("Candidates per run (Top-K)", self.top_k_spin)
        layout.addWidget(identification)
        layout.addStretch(1)

    def _on_appearance_changed(self) -> None:
        theme = str(self.theme_combo.currentData())
        style = str(self.style_combo.currentData())
        self._state.settings.set_theme(theme)
        self._state.settings.set_style(style)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            ThemeManager(app).apply(theme, style)

    def _on_top_k_changed(self, value: int) -> None:
        settings = self._state.settings.settings
        settings.default_top_k = value
        self._state.settings.save(settings)
