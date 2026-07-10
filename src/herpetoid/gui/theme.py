"""Theme management: system / light / dark, applied via a Fusion palette + a modern stylesheet."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# Naturalist teal-green accent, shared by both themes.
_ACCENT = "#2f9e8f"
_ACCENT_HOVER = "#38b3a2"
_ACCENT_PRESSED = "#26857a"

_DARK = {
    "window": "#1f2226",
    "base": "#17191c",
    "surface": "#26292e",
    "surface_hover": "#2f333a",
    "text": "#e4e6e8",
    "muted": "#9aa0a6",
    "border": "#3a3f45",
    "nav_bg": "#191b1e",
    "hover": "rgba(255, 255, 255, 0.06)",
    "alt_row": "#212429",
}

_LIGHT = {
    "window": "#f4f6f8",
    "base": "#ffffff",
    "surface": "#ffffff",
    "surface_hover": "#eef1f4",
    "text": "#1f2937",
    "muted": "#6b7280",
    "border": "#d7dde3",
    "nav_bg": "#eef1f4",
    "hover": "rgba(0, 0, 0, 0.05)",
    "alt_row": "#f7f9fb",
}


def _dark_palette() -> QPalette:
    palette = QPalette()
    window = QColor(_DARK["window"])
    base = QColor(_DARK["base"])
    text = QColor(_DARK["text"])
    highlight = QColor(_ACCENT)
    palette.setColor(QPalette.ColorRole.Window, window)
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, base)
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(_DARK["alt_row"]))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor(_DARK["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, base)
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Mid, QColor(_DARK["muted"]))
    disabled = QColor(120, 120, 120)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return palette


def _light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(_LIGHT["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(_LIGHT["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(_LIGHT["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(_LIGHT["alt_row"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(_LIGHT["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(_LIGHT["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(_LIGHT["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, QColor(_ACCENT))
    palette.setColor(QPalette.ColorRole.Mid, QColor(_LIGHT["muted"]))
    return palette


def _stylesheet(c: dict[str, str]) -> str:
    """A modern flat stylesheet parameterized by a theme's colors."""
    return f"""
    * {{
        font-size: 13px;
    }}
    QMainWindow, QWidget {{
        color: {c["text"]};
    }}

    /* --- Shell chrome: menu bar, toolbar, tabs, docks --- */
    QMenuBar {{
        background: {c["nav_bg"]};
        color: {c["text"]};
        border: none;
        padding: 2px 6px;
    }}
    QMenuBar::item {{
        padding: 5px 10px;
        border-radius: 6px;
        background: transparent;
    }}
    QMenuBar::item:selected {{
        background: {c["hover"]};
    }}
    QMenuBar::item:pressed {{
        background: {_ACCENT};
        color: white;
    }}
    QMenu {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 26px 6px 14px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {_ACCENT};
        color: white;
    }}
    QMenu::item:disabled {{
        color: {c["muted"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c["border"]};
        margin: 5px 8px;
    }}
    QToolBar {{
        background: {c["nav_bg"]};
        border: none;
        border-bottom: 1px solid {c["border"]};
        padding: 4px 6px;
        spacing: 2px;
    }}
    QToolBar::separator {{
        background: {c["border"]};
        width: 1px;
        margin: 6px 6px;
    }}
    QToolButton {{
        background: transparent;
        color: {c["text"]};
        border: none;
        border-radius: 7px;
        padding: 5px 8px;
    }}
    QToolButton:hover {{
        background: {c["hover"]};
    }}
    QToolButton:pressed, QToolButton:checked {{
        background: {_ACCENT};
        color: white;
    }}
    QToolButton:disabled {{
        color: {c["muted"]};
    }}
    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {c["border"]};
    }}
    QTabBar {{
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c["muted"]};
        padding: 8px 18px;
        margin: 0 2px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:hover {{
        color: {c["text"]};
        background: {c["hover"]};
    }}
    QTabBar::tab:selected {{
        color: {c["text"]};
        border-bottom: 2px solid {_ACCENT};
        font-weight: 600;
    }}
    QDockWidget {{
        color: {c["muted"]};
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}
    QDockWidget::title {{
        background: {c["nav_bg"]};
        padding: 7px 10px;
        text-align: left;
        font-weight: 600;
    }}

    /* --- Buttons --- */
    QPushButton {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 7px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background: {c["surface_hover"]};
    }}
    QPushButton:pressed {{
        background: {c["hover"]};
    }}
    QPushButton:checked {{
        background: {_ACCENT};
        color: white;
        border-color: {_ACCENT};
    }}
    QPushButton:disabled {{
        color: {c["muted"]};
        background: transparent;
    }}
    QPushButton#primary {{
        background: {_ACCENT};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background: {_ACCENT_HOVER};
    }}
    QPushButton#primary:pressed {{
        background: {_ACCENT_PRESSED};
    }}
    QPushButton#primary:disabled {{
        background: {c["surface"]};
        color: {c["muted"]};
    }}

    /* --- Inputs --- */
    QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
        background: {c["base"]};
        border: 1px solid {c["border"]};
        border-radius: 7px;
        padding: 5px 8px;
        selection-background-color: {_ACCENT};
        selection-color: white;
    }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {_ACCENT};
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}

    /* --- Tables & lists --- */
    QTableWidget, QListWidget, QTreeWidget {{
        background: {c["base"]};
        alternate-background-color: {c["alt_row"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        gridline-color: {c["border"]};
        outline: 0;
    }}
    QTableWidget::item {{ padding: 4px 6px; }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {_ACCENT};
        color: white;
    }}
    /* Match cards carry their own colored score/detail text — select with a border, not a fill. */
    QListWidget#matchCards::item:selected {{
        background: {c["hover"]};
        color: {c["text"]};
        border: 1px solid {_ACCENT};
        border-radius: 8px;
    }}
    QHeaderView::section {{
        background: {c["surface"]};
        color: {c["muted"]};
        padding: 6px 8px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background: {c["surface"]};
        border: none;
    }}

    /* --- Group boxes / frames --- */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: 10px;
        margin-top: 12px;
        padding: 10px 8px 8px 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 5px;
        color: {c["muted"]};
    }}

    /* --- Misc --- */
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:horizontal {{ width: 8px; }}
    QSplitter::handle:vertical {{ height: 8px; }}
    QScrollArea {{ border: none; }}
    QStatusBar {{ color: {c["muted"]}; }}
    QScrollBar:vertical {{
        background: transparent; width: 11px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]}; border-radius: 5px; min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 11px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border"]}; border-radius: 5px; min-width: 28px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


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
            self._app.setStyleSheet(_stylesheet(_DARK))
        else:
            self._app.setPalette(_light_palette())
            self._app.setStyleSheet(_stylesheet(_LIGHT))
        return resolved

    def _resolve(self, theme: str) -> str:
        if theme in ("light", "dark"):
            return theme
        scheme = self._app.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
