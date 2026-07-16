"""Theme management: mode (system / light / dark) + style presets, via a Fusion palette + stylesheet.

A *style* is a named preset (accent trio + light and dark surface palettes). The *mode* picks which
of the two palettes is active (``system`` resolves to the OS color scheme). Both are user settings;
:class:`ThemeManager` combines them into one palette + stylesheet application.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel

DEFAULT_STYLE = "teal"


@dataclass(frozen=True)
class ThemeStyle:
    """A visual preset: the accent trio plus a light and a dark surface palette."""

    style_id: str
    name: str
    accent: str
    accent_hover: str
    accent_pressed: str
    light: dict[str, str]
    dark: dict[str, str]


def _light(**overrides: str) -> dict[str, str]:
    base = {
        "window": "#f5f6f8",
        "base": "#ffffff",
        "surface": "#ffffff",
        "surface_hover": "#eef1f4",
        "text": "#1f2937",
        "muted": "#6b7280",
        "border": "#e2e6ea",
        "nav_bg": "#eef1f4",
        "hover": "rgba(0, 0, 0, 0.05)",
        "alt_row": "#f7f9fb",
        "grid": "#eef1f4",
    }
    base.update(overrides)
    return base


def _dark(**overrides: str) -> dict[str, str]:
    base = {
        "window": "#1f2226",
        "base": "#17191c",
        "surface": "#26292e",
        "surface_hover": "#2f333a",
        "text": "#e4e6e8",
        "muted": "#9aa0a6",
        "border": "#373c42",
        "nav_bg": "#191b1e",
        "hover": "rgba(255, 255, 255, 0.06)",
        "alt_row": "#1c1f23",
        "grid": "#26292e",
    }
    base.update(overrides)
    return base


#: The selectable style presets, in the order they are offered to the user.
STYLES: tuple[ThemeStyle, ...] = (
    ThemeStyle(
        style_id="teal",
        name="Brook Teal",
        accent="#2f9e8f",
        accent_hover="#38b3a2",
        accent_pressed="#26857a",
        light=_light(),
        dark=_dark(),
    ),
    ThemeStyle(
        style_id="moss",
        name="Forest Moss",
        accent="#6a994e",
        accent_hover="#7aa95e",
        accent_pressed="#588a41",
        light=_light(
            window="#f5f7f3",
            surface_hover="#edf1e9",
            nav_bg="#eef2ea",
            border="#e1e6dc",
            alt_row="#f7f9f4",
            grid="#eef1e9",
        ),
        dark=_dark(
            window="#1f231d",
            base="#171a15",
            surface="#262b23",
            surface_hover="#2f352b",
            nav_bg="#191c17",
            border="#383f33",
            alt_row="#1c2019",
            grid="#262b23",
        ),
    ),
    ThemeStyle(
        style_id="slate",
        name="River Slate",
        accent="#4a7fb5",
        accent_hover="#5b90c6",
        accent_pressed="#3d6c9e",
        light=_light(
            window="#f4f6f9",
            surface_hover="#ecf0f5",
            nav_bg="#edf1f6",
            border="#e0e5ec",
            alt_row="#f6f8fb",
            grid="#edf1f6",
        ),
        dark=_dark(
            window="#1e2126",
            base="#16181d",
            surface="#252930",
            surface_hover="#2e333c",
            nav_bg="#181b1f",
            border="#363c45",
            alt_row="#1b1e23",
            grid="#252930",
        ),
    ),
    ThemeStyle(
        style_id="clay",
        name="Sunset Clay",
        accent="#c1663f",
        accent_hover="#d0764e",
        accent_pressed="#a85534",
        light=_light(
            window="#f8f6f3",
            surface_hover="#f2ede7",
            nav_bg="#f2eee9",
            border="#e8e2da",
            alt_row="#f9f7f4",
            grid="#f0ebe5",
        ),
        dark=_dark(
            window="#232019",
            base="#1a1813",
            surface="#2b2721",
            surface_hover="#353028",
            nav_bg="#1c1a15",
            border="#403a31",
            alt_row="#201d17",
            grid="#2b2721",
        ),
    ),
)

_STYLES_BY_ID = {style.style_id: style for style in STYLES}


def available_styles() -> tuple[ThemeStyle, ...]:
    return STYLES


def get_style(style_id: str | None) -> ThemeStyle:
    """The named style, falling back to the default for unknown/legacy ids."""
    return _STYLES_BY_ID.get(style_id or "", _STYLES_BY_ID[DEFAULT_STYLE])


def _rgba(hex_color: str, alpha: float) -> str:
    # Qt stylesheets accept rgba() alpha as an int (0-255) or a percentage — NOT a CSS 0.0-1.0
    # float (that fails to parse and silently drops the whole property).
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {round(alpha * 100)}%)"


def _palette(colors: dict[str, str], accent: str) -> QPalette:
    palette = QPalette()
    text = QColor(colors["text"])
    highlight = QColor(accent)
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, text)
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["base"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["alt_row"]))
    palette.setColor(QPalette.ColorRole.Text, text)
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, text)
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, text)
    palette.setColor(QPalette.ColorRole.Highlight, highlight)
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, highlight)
    palette.setColor(QPalette.ColorRole.Mid, QColor(colors["muted"]))
    disabled = QColor(colors["muted"])
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled)
    return palette


def _stylesheet(style: ThemeStyle, mode: str) -> str:
    """A modern flat stylesheet for one style preset in the given resolved mode."""
    c = style.dark if mode == "dark" else style.light
    accent = style.accent
    accent_hover = style.accent_hover
    accent_pressed = style.accent_pressed
    # Selection is a soft accent tint with normal text — calmer than a solid accent fill, and cell
    # cues (ticks, score colors) stay readable inside a selected row.
    selection = _rgba(accent, 0.32 if mode == "dark" else 0.16)
    selection_strong = _rgba(accent, 0.45 if mode == "dark" else 0.28)
    return f"""
    * {{
        font-size: 13px;
    }}
    QMainWindow, QWidget {{
        color: {c["text"]};
    }}
    QToolTip {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 6px;
        padding: 5px 8px;
    }}

    /* --- Shell chrome: menu bar, toolbar, tabs, docks, status bar --- */
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
        background: {accent};
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
        background: {accent};
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
        background: {accent};
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
        padding: 9px 18px;
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
        border-bottom: 2px solid {accent};
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
    /* The dock is one calm panel: its tree floats on the panel background, borderless. */
    QDockWidget QTreeWidget {{
        background: transparent;
        border: none;
    }}
    QStatusBar {{
        color: {c["muted"]};
        background: {c["nav_bg"]};
        border-top: 1px solid {c["border"]};
    }}
    QStatusBar::item {{
        border: none;
    }}

    /* --- Typography helpers --- */
    QLabel#sectionTitle {{
        color: {c["muted"]};
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 1px;
        margin-top: 2px;
    }}
    QLabel#pageTitle {{
        font-size: 30px;
        font-weight: 800;
    }}
    QLabel#pageSubtitle {{
        font-size: 14px;
        color: {c["muted"]};
    }}
    QLabel#toast {{
        background: {accent};
        color: white;
        border-radius: 9px;
        padding: 10px 16px;
        font-weight: 600;
    }}

    /* --- Buttons --- */
    QPushButton {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background: {c["surface_hover"]};
        border-color: {c["muted"]};
    }}
    QPushButton:pressed {{
        background: {c["hover"]};
    }}
    QPushButton:checked {{
        background: {accent};
        color: white;
        border-color: {accent};
    }}
    QPushButton:disabled {{
        color: {c["muted"]};
        background: transparent;
    }}
    QPushButton#modeSwitch {{
        background: transparent;
        color: {c["muted"]};
        border: 1px solid {c["border"]};
        border-radius: 13px;
        padding: 4px 12px;
    }}
    QPushButton#modeSwitch:hover {{
        color: {c["text"]};
        background: {c["hover"]};
    }}
    QPushButton#modeSwitch:checked {{
        background: {selection};
        color: {accent};
        border: 1px solid {accent};
    }}
    QPushButton#accentOutline {{
        background: transparent;
        color: {accent};
        border: 2px solid {accent};
        font-weight: 600;
    }}
    QPushButton#accentOutline:hover {{
        background: {selection};
    }}
    QPushButton#accentOutline:pressed {{
        background: {c["hover"]};
    }}
    QPushButton#accentOutline:disabled {{
        color: {c["muted"]};
        border-color: {c["border"]};
        background: transparent;
    }}
    QPushButton#primary {{
        background: {accent};
        color: white;
        border: none;
        font-weight: 600;
    }}
    QPushButton#primary:hover {{
        background: {accent_hover};
    }}
    QPushButton#primary:pressed {{
        background: {accent_pressed};
    }}
    QPushButton#primary:disabled {{
        background: {c["surface"]};
        color: {c["muted"]};
    }}

    /* --- Inputs --- */
    QLineEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QPlainTextEdit, QTextEdit {{
        background: {c["base"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 5px 8px;
        selection-background-color: {accent};
        selection-color: white;
    }}
    QLineEdit:focus, QComboBox:focus, QDateEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{
        border: 1px solid {accent};
    }}
    /* Disabled inputs read as calm read-only fields, not greyed chrome (locked observations). */
    QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled,
    QSpinBox:disabled, QDoubleSpinBox:disabled {{
        background: transparent;
        border-color: {c["grid"]};
        color: {c["muted"]};
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        padding: 4px;
        selection-background-color: {selection_strong};
        selection-color: {c["text"]};
    }}
    QCheckBox::indicator, QRadioButton::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {c["border"]};
        border-radius: 4px;
        background: {c["base"]};
    }}
    QRadioButton::indicator {{
        border-radius: 8px;
    }}
    QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
        border-color: {accent};
    }}
    QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
        background: {accent};
        border-color: {accent};
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {c["border"]};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {accent};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px;
        height: 14px;
        margin: -5px 0;
        border-radius: 7px;
        background: {accent};
    }}
    QProgressBar {{
        border: none;
        background: {c["border"]};
        border-radius: 3px;
    }}
    QProgressBar::chunk {{
        background: {accent};
        border-radius: 3px;
    }}

    /* --- Tables, trees & lists --- */
    QTableWidget, QListWidget, QTreeWidget {{
        background: {c["base"]};
        alternate-background-color: {c["alt_row"]};
        border: 1px solid {c["border"]};
        border-radius: 8px;
        gridline-color: {c["grid"]};
        outline: 0;
        /* Selection = a soft accent tint with normal text (set on the view — the delegate ignores
           ::item:selected backgrounds), so ticks and score colors stay readable when selected. */
        selection-background-color: {selection_strong};
        selection-color: {c["text"]};
    }}
    QTableWidget::item {{
        padding: 4px 6px;
    }}
    QTreeWidget::item {{
        padding: 3px 4px;
        border-radius: 6px;
    }}
    QTreeWidget::item:hover {{
        background: {c["hover"]};
    }}
    QListWidget#matchCards::item:selected {{
        background: {c["hover"]};
        color: {c["text"]};
        border: 1px solid {accent};
        border-radius: 8px;
    }}
    QHeaderView::section {{
        background: transparent;
        color: {c["muted"]};
        padding: 7px 8px;
        border: none;
        border-bottom: 1px solid {c["border"]};
        font-weight: 600;
    }}
    QTableCornerButton::section {{
        background: transparent;
        border: none;
        border-bottom: 1px solid {c["border"]};
    }}

    /* --- Cards (Dashboard) --- */
    QFrame#homeCard, QFrame#statusCard, QFrame#statTile {{
        background: {c["surface"]};
        border: 1px solid {c["border"]};
        border-radius: 12px;
    }}
    QFrame#homeCard:hover {{
        border: 1px solid {accent};
    }}
    QFrame#homeCard QLabel, QFrame#statusCard QLabel, QFrame#statTile QLabel {{
        border: none;
        background: transparent;
    }}
    QLabel#statValue {{
        font-size: 26px;
        font-weight: 800;
        color: {accent};
    }}
    QLabel#cardTitle {{
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#cardCaption {{
        color: {c["muted"]};
        font-size: 12px;
    }}

    /* --- Group boxes / frames --- */
    QGroupBox {{
        background: {c["surface"]};
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
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c["border"]}; border-radius: 4px; min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c["border"]}; border-radius: 4px; min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {c["muted"]};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    """


def section_label(text: str) -> QLabel:
    """A small uppercase section heading (the app's one way of titling a panel region)."""
    label = QLabel(text.upper())
    label.setObjectName("sectionTitle")
    return label


class ThemeManager:
    """Applies a mode + style preset to the :class:`QApplication`."""

    def __init__(self, app: QApplication) -> None:
        self._app = app

    def apply(self, theme: str, style_id: str | None = None) -> str:
        """Apply ``'system'`` | ``'light'`` | ``'dark'`` in the given style; returns the mode."""
        resolved = self._resolve(theme)
        style = get_style(style_id)
        colors = style.dark if resolved == "dark" else style.light
        self._app.setStyle("Fusion")
        self._app.setPalette(_palette(colors, style.accent))
        self._app.setStyleSheet(_stylesheet(style, resolved))
        return resolved

    def _resolve(self, theme: str) -> str:
        if theme in ("light", "dark"):
            return theme
        scheme = self._app.styleHints().colorScheme()
        return "dark" if scheme == Qt.ColorScheme.Dark else "light"
