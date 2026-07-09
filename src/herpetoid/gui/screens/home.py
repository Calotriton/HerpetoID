"""Home screen: a landing page with the current project's status and quick actions."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from PySide6.QtCore import Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from herpetoid.gui.state import AppState

# (title, description, destination screen) for the quick-action cards.
_ACTIONS: tuple[tuple[str, str, str], ...] = (
    ("Projects", "Create or open a portable project bundle.", "Projects"),
    ("Import images", "Add photos to the catalog as observations.", "Import"),
    ("Observations", "Mark the pattern ROI and record measurements.", "Observations"),
    ("Candidates", "Match a capture against known individuals.", "Candidates"),
    ("Comparison", "Compare two captures side by side.", "Comparison"),
    ("Individuals", "Browse and edit the identified catalog.", "Individuals"),
    ("Statistics", "Measurements, ratios and growth over time.", "Statistics"),
    ("Help", "Read the offline user manual.", "Help"),
)


def _clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        child = item.layout()
        if widget is not None:
            widget.deleteLater()
        elif child is not None:
            _clear_layout(child)


class _ActionCard(QFrame):
    """A clickable card that navigates to a screen."""

    def __init__(self, title: str, description: str, on_click: Callable[[], None]) -> None:
        super().__init__()
        self._on_click = on_click
        self.setObjectName("homeCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "#homeCard { background: palette(base); border: 1px solid palette(mid);"
            " border-radius: 10px; }"
            " #homeCard:hover { border: 1px solid palette(highlight); }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 14px; font-weight: 700; border: none;")
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: palette(mid); font-size: 12px; border: none;")
        layout.addWidget(title_label)
        layout.addWidget(description_label)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self._on_click()
        super().mouseReleaseEvent(event)


def _stat_tile(value: str, label: str) -> QWidget:
    tile = QFrame()
    tile.setObjectName("statTile")
    tile.setStyleSheet(
        "#statTile { background: palette(base); border: 1px solid palette(mid); border-radius: 10px; }"
    )
    layout = QVBoxLayout(tile)
    layout.setContentsMargins(16, 10, 16, 10)
    layout.setSpacing(0)
    number = QLabel(value)
    number.setStyleSheet(
        "font-size: 26px; font-weight: 800; color: palette(highlight); border: none;"
    )
    caption = QLabel(label)
    caption.setStyleSheet("color: palette(mid); font-size: 11px; border: none;")
    layout.addWidget(number)
    layout.addWidget(caption)
    return tile


class HomeScreen(QWidget):
    def __init__(self, state: AppState, navigate: Callable[[str], None]) -> None:
        super().__init__()
        self._state = state
        self._navigate = navigate

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        title = QLabel("HerpetoID")
        title.setStyleSheet("font-size: 32px; font-weight: 800;")
        subtitle = QLabel(
            "Non-invasive individual identification of wildlife from natural body patterns."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font-size: 14px; color: palette(mid);")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self._status_host = QWidget()
        self._status_layout = QVBoxLayout(self._status_host)
        self._status_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._status_host)

        actions_header = QLabel("Quick actions")
        actions_header.setStyleSheet("font-size: 15px; font-weight: 700; margin-top: 6px;")
        layout.addWidget(actions_header)

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (title_text, description, destination) in enumerate(_ACTIONS):
            card = _ActionCard(title_text, description, partial(self._navigate, destination))
            grid.addWidget(card, index // 4, index % 4)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)
        layout.addStretch(1)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        _clear_layout(self._status_layout)
        card = QFrame()
        card.setObjectName("statusCard")
        card.setStyleSheet(
            "#statusCard { background: palette(base); border: 1px solid palette(mid);"
            " border-radius: 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(12)

        project = self._state.project
        catalog = self._state.catalog
        if project is None or catalog is None:
            heading = QLabel("No project open")
            heading.setStyleSheet("font-size: 16px; font-weight: 700; border: none;")
            hint = QLabel("Create a new project or open an existing bundle to begin.")
            hint.setStyleSheet("color: palette(mid); border: none;")
            card_layout.addWidget(heading)
            card_layout.addWidget(hint)
            buttons = QHBoxLayout()
            open_button = QPushButton("Go to Projects")
            open_button.setObjectName("primary")
            open_button.clicked.connect(lambda: self._navigate("Projects"))
            buttons.addWidget(open_button)
            buttons.addStretch(1)
            card_layout.addLayout(buttons)
        else:
            heading = QLabel(f"Current project · {project.project.name}")
            heading.setStyleSheet("font-size: 16px; font-weight: 700; border: none;")
            card_layout.addWidget(heading)

            tiles = QHBoxLayout()
            tiles.setSpacing(12)
            tiles.addWidget(_stat_tile(str(len(catalog.list_species())), "Species"))
            tiles.addWidget(_stat_tile(str(catalog.observation_count()), "Observations"))
            tiles.addWidget(_stat_tile(str(catalog.individual_count()), "Individuals"))
            tiles.addStretch(1)
            card_layout.addLayout(tiles)

            buttons = QHBoxLayout()
            for text, destination in (
                ("Import images", "Import"),
                ("Observations", "Observations"),
                ("Identify", "Candidates"),
            ):
                button = QPushButton(text)
                button.clicked.connect(lambda _=False, dest=destination: self._navigate(dest))
                buttons.addWidget(button)
            buttons.addStretch(1)
            card_layout.addLayout(buttons)

        self._status_layout.addWidget(card)
