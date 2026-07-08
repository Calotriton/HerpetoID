"""The main window: a navigation sidebar driving a stack of screens, plus a status bar."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QWidget,
)

from herpetoid.application.registry import PluginRegistry

from .screens.home import HomeScreen
from .screens.placeholder import PlaceholderScreen
from .screens.plugins import PluginManagerScreen


class MainWindow(QMainWindow):
    def __init__(self, registry: PluginRegistry) -> None:
        super().__init__()
        self.setWindowTitle("HerpetoID")
        self.resize(1100, 720)

        self._nav = QListWidget()
        self._nav.setFixedWidth(190)
        self._nav.setObjectName("navigation")
        self._stack = QStackedWidget()

        self._add_screen("Home", HomeScreen())
        self._add_screen("Projects", PlaceholderScreen("Project Manager"))
        self._add_screen("Import", PlaceholderScreen("Image Import"))
        self._add_screen("Observations", PlaceholderScreen("Observation Editor"))
        self._add_screen("Individuals", PlaceholderScreen("Individual Browser"))
        self._add_screen("Candidates", PlaceholderScreen("Candidate Ranking"))
        self._add_screen("Comparison", PlaceholderScreen("Comparison Window"))
        self._add_screen("Statistics", PlaceholderScreen("Statistics"))
        self._add_screen("Plugins", PluginManagerScreen(registry))
        self._add_screen("Settings", PlaceholderScreen("Settings"))
        self._add_screen("Help", PlaceholderScreen("Help"))

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Ready")
        self._nav.setCurrentRow(0)

    def _add_screen(self, name: str, widget: QWidget) -> None:
        self._nav.addItem(QListWidgetItem(name))
        self._stack.addWidget(widget)

    def screen_names(self) -> list[str]:
        return [self._nav.item(i).text() for i in range(self._nav.count())]

    def current_screen_name(self) -> str:
        item = self._nav.currentItem()
        return item.text() if item is not None else ""

    def navigate_to(self, name: str) -> None:
        for i in range(self._nav.count()):
            if self._nav.item(i).text() == name:
                self._nav.setCurrentRow(i)
                return
