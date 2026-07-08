"""Settings screen: theme (applied live) and default Top-K, persisted via SettingsService."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QComboBox, QFormLayout, QSpinBox, QWidget

from herpetoid.gui.state import AppState
from herpetoid.gui.theme import ThemeManager

_THEMES = ["system", "light", "dark"]


class SettingsScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

        form = QFormLayout(self)
        form.setContentsMargins(16, 16, 16, 16)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(_THEMES)
        self.theme_combo.setCurrentText(state.settings.settings.theme)
        self.theme_combo.currentTextChanged.connect(self._on_theme_changed)
        form.addRow("Theme", self.theme_combo)

        self.top_k_spin = QSpinBox()
        self.top_k_spin.setRange(1, 20)
        self.top_k_spin.setValue(state.settings.settings.default_top_k)
        self.top_k_spin.valueChanged.connect(self._on_top_k_changed)
        form.addRow("Default Top-K", self.top_k_spin)

    def _on_theme_changed(self, theme: str) -> None:
        self._state.settings.set_theme(theme)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            ThemeManager(app).apply(theme)

    def _on_top_k_changed(self, value: int) -> None:
        settings = self._state.settings.settings
        settings.default_top_k = value
        self._state.settings.save(settings)
