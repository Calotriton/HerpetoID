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

from .screens.candidate_ranking import CandidateRankingScreen
from .screens.comparison import ComparisonScreen
from .screens.help import HelpScreen
from .screens.home import HomeScreen
from .screens.import_images import ImageImportScreen
from .screens.individuals import IndividualBrowserScreen
from .screens.observations import ObservationsScreen
from .screens.plugins import PluginManagerScreen
from .screens.projects import ProjectManagerScreen
from .screens.settings import SettingsScreen
from .screens.statistics import StatisticsScreen
from .state import AppState


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self.setWindowTitle("HerpetoID")
        self.resize(1280, 820)

        self._nav = QListWidget()
        self._nav.setFixedWidth(200)
        self._nav.setObjectName("navigation")
        self._stack = QStackedWidget()

        self._add_screen("Home", HomeScreen(state, self.navigate_to))
        self._add_screen("Projects", ProjectManagerScreen(state))
        self._add_screen("Import", ImageImportScreen(state))
        self._add_screen("Observations", ObservationsScreen(state))
        self._add_screen("Candidates", CandidateRankingScreen(state))
        self._add_screen("Individuals", IndividualBrowserScreen(state))
        self._add_screen("Comparison", ComparisonScreen(state))
        self._add_screen("Statistics", StatisticsScreen(state))
        self._add_screen("Plugins", PluginManagerScreen(state.registry))
        self._add_screen("Settings", SettingsScreen(state))
        self._add_screen("Help", HelpScreen())

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        state.project_changed.connect(self._on_project_changed)
        self.statusBar().showMessage("Ready")
        self._nav.setCurrentRow(0)

    def _add_screen(self, name: str, widget: QWidget) -> None:
        self._nav.addItem(QListWidgetItem(name))
        self._stack.addWidget(widget)

    def _on_project_changed(self) -> None:
        project = self._state.project
        if project is not None:
            self.setWindowTitle(f"HerpetoID — {project.project.name}")
            self.statusBar().showMessage(f"Project: {project.project.name}")
        else:
            self.setWindowTitle("HerpetoID")
            self.statusBar().showMessage("Ready")

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
