"""The main window shell: menu bar + icon toolbar + workflow tabs + project dock + status bar.

The five workflow tabs (Dashboard, Observations, Individuals, Identification, Statistics) carry the
day-to-day photo-ID pipeline; secondary screens (Projects, Import, Settings, Plugins, Help) open as
cached non-modal dialogs from the menus/toolbar. ``navigate_to`` keeps accepting the legacy screen
names (Home, Candidates, Comparison, …) and maps them onto the new shell.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QTabWidget,
    QToolBar,
    QWidget,
)

from herpetoid import __version__
from herpetoid.application.project_service import ProjectService

from . import project_actions
from .dialogs import ScreenDialog
from .dock import ProjectDock
from .icons import icon
from .screens.help import HelpScreen
from .screens.home import HomeScreen
from .screens.identification import IdentificationScreen
from .screens.import_images import ImageImportScreen
from .screens.individuals import IndividualBrowserScreen
from .screens.observations import ObservationsScreen
from .screens.plugins import PluginManagerScreen
from .screens.projects import ProjectManagerScreen
from .screens.settings import SettingsScreen
from .screens.statistics import StatisticsScreen
from .state import AppState
from .theme import ThemeManager, available_styles

_ScreenT = TypeVar("_ScreenT", bound=QWidget)

# Legacy navigate_to names (used by the Dashboard cards and older callers) → tab names.
_LEGACY_TABS = {"Home": "Dashboard", "Candidates": "Identification", "Comparison": "Identification"}
# Names that open a dialog instead of switching tabs.
_DIALOG_NAMES = ("Projects", "Import", "Settings", "Plugins", "Help")

_EXPORT_FORMATS = (("CSV", "csv"), ("Excel", "xlsx"), ("JSON", "json"), ("PDF", "pdf"))
_EXPORT_FILTERS = {
    "csv": "CSV (*.csv)",
    "xlsx": "Excel (*.xlsx)",
    "json": "JSON (*.json)",
    "pdf": "PDF (*.pdf)",
}


class MainWindow(QMainWindow):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self.setWindowTitle("HerpetoID")
        self.resize(1280, 820)
        self._dialogs: dict[str, ScreenDialog] = {}
        self._icon_actions: list[tuple[QAction, str]] = []
        self._project_actions: list[QAction] = []

        self._tabs = QTabWidget()
        self._tabs.setObjectName("mainTabs")
        self._tabs.setDocumentMode(True)
        self._tabs.addTab(HomeScreen(state, self.navigate_to), "Dashboard")
        self._tabs.addTab(ObservationsScreen(state), "Observations")
        self._tabs.addTab(IndividualBrowserScreen(state), "Individuals")
        self._tabs.addTab(IdentificationScreen(state), "Identification")
        self._tabs.addTab(StatisticsScreen(state), "Statistics")
        self.setCentralWidget(self._tabs)

        self._dock = ProjectDock(
            state,
            self.navigate_to,
            open_observation=self._open_observation,
            open_individual=self._open_individual,
        )
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._dock)

        self._build_menus()
        self._build_toolbar()
        self._apply_icons()

        self._species_status = QLabel()
        self._version_status = QLabel(f"v{__version__}")
        self.statusBar().addPermanentWidget(self._species_status)
        self.statusBar().addPermanentWidget(self._version_status)

        state.project_changed.connect(self._on_project_changed)
        self._on_project_changed()

    # -- shell construction ------------------------------------------------------------------------
    def _action(
        self,
        text: str,
        slot: Callable[[], object],
        *,
        shortcut: str | None = None,
        icon_name: str | None = None,
        needs_project: bool = False,
    ) -> QAction:
        action = QAction(text, self)
        action.triggered.connect(slot)
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        if icon_name is not None:
            self._icon_actions.append((action, icon_name))
        if needs_project:
            self._project_actions.append(action)
        return action

    def _build_menus(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&File")
        self._new_project_action = self._action(
            "New Project…",
            lambda: project_actions.new_project(self, self._state),
            shortcut="Ctrl+N",
            icon_name="new-project",
        )
        self._open_project_action = self._action(
            "Open Project…",
            lambda: project_actions.open_project_dialog(self, self._state),
            shortcut="Ctrl+O",
            icon_name="open-project",
        )
        file_menu.addAction(self._new_project_action)
        file_menu.addAction(self._open_project_action)
        self._recent_menu = QMenu("Recent Projects", self)
        self._recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        file_menu.addMenu(self._recent_menu)
        file_menu.addSeparator()
        # One single entry point for getting photos in: "Add Observations" (each image becomes an
        # observation). Shared by the File menu, the Project menu and the toolbar.
        self._import_action = self._action(
            "Add Observations…",
            lambda: self.open_dialog("Import"),
            shortcut="Ctrl+I",
            icon_name="observation",
            needs_project=True,
        )
        file_menu.addAction(self._import_action)
        self._export_menu = QMenu("Export", self)
        for label, fmt in _EXPORT_FORMATS:
            self._export_menu.addAction(self._action(label + "…", partial(self._export, fmt)))
        self._export_action = file_menu.addMenu(self._export_menu)
        self._project_actions.append(self._export_action)
        file_menu.addSeparator()
        file_menu.addAction(self._action("Exit", self.close, shortcut="Ctrl+Q"))

        project_menu = bar.addMenu("&Project")
        project_menu.addAction(self._import_action)
        self._identify_action = self._action(
            "Identify",
            lambda: self.navigate_to("Identification"),
            shortcut="Ctrl+D",
            icon_name="identify",
            needs_project=True,
        )
        project_menu.addAction(self._identify_action)
        project_menu.addSeparator()
        project_menu.addAction(
            self._action("Close Project", self._state.close_project, needs_project=True)
        )

        view_menu = bar.addMenu("&View")
        dock_action = self._dock.toggleViewAction()
        dock_action.setText("Project Panel")
        view_menu.addAction(dock_action)
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        current_theme = self._state.settings.settings.theme
        for label, value in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(value == current_theme)
            action.triggered.connect(lambda _=False, v=value: self._set_theme(v))
            theme_group.addAction(action)
            theme_menu.addAction(action)
        style_menu = view_menu.addMenu("Style")
        style_group = QActionGroup(self)
        style_group.setExclusive(True)
        current_style = self._state.settings.settings.style
        for style in available_styles():
            action = QAction(style.name, self)
            action.setCheckable(True)
            action.setChecked(style.style_id == current_style)
            action.triggered.connect(lambda _=False, v=style.style_id: self._set_style(v))
            style_group.addAction(action)
            style_menu.addAction(action)
        view_menu.addSeparator()
        for index in range(self._tabs.count()):
            name = self._tabs.tabText(index)
            view_menu.addAction(
                self._action(name, partial(self.navigate_to, name), shortcut=f"Ctrl+{index + 1}")
            )

        tools_menu = bar.addMenu("&Tools")
        tools_menu.addAction(
            self._action("Settings…", lambda: self.open_dialog("Settings"), icon_name="settings")
        )

        plugins_menu = bar.addMenu("P&lugins")
        plugins_menu.addAction(
            self._action("Plugin Manager…", lambda: self.open_dialog("Plugins"))
        )

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(
            self._action(
                "User Manual", lambda: self.open_dialog("Help"), shortcut="F1", icon_name="help"
            )
        )
        help_menu.addAction(self._action("About HerpetoID", self._about))

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        toolbar.addAction(self._new_project_action)
        toolbar.addAction(self._open_project_action)
        toolbar.addSeparator()
        toolbar.addAction(self._import_action)
        toolbar.addAction(self._identify_action)
        self._export_toolbar_action = self._action(
            "Export", lambda: self._export_menu.popup(self.cursor().pos()), icon_name="export"
        )
        self._export_toolbar_action.setMenu(self._export_menu)
        self._project_actions.append(self._export_toolbar_action)
        toolbar.addAction(self._export_toolbar_action)
        toolbar.addSeparator()

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        species_caption = QLabel("Species: ")
        species_caption.setStyleSheet("color: palette(mid);")
        toolbar.addWidget(species_caption)
        self.species_combo = QComboBox()
        for module in self._state.registry.modules(enabled_only=True):
            self.species_combo.addItem(module.descriptor.name, module.descriptor.module_id)
        self.species_combo.currentIndexChanged.connect(
            lambda: setattr(self._state, "default_module_id", self.species_combo.currentData())
        )
        self._state.default_module_id = self.species_combo.currentData()
        toolbar.addWidget(self.species_combo)
        algorithm_caption = QLabel("  Algorithm: ")
        algorithm_caption.setStyleSheet("color: palette(mid);")
        toolbar.addWidget(algorithm_caption)
        self.algorithm_combo = QComboBox()
        for algo in self._state.registry.algorithms(enabled_only=True):
            self.algorithm_combo.addItem(algo.descriptor.name, algo.descriptor.algorithm_id)
        self.algorithm_combo.currentIndexChanged.connect(
            lambda: setattr(self._state, "default_algorithm_id", self.algorithm_combo.currentData())
        )
        self._state.default_algorithm_id = self.algorithm_combo.currentData()
        toolbar.addWidget(self.algorithm_combo)
        toolbar.addSeparator()
        toolbar.addAction(
            self._action("Settings", lambda: self.open_dialog("Settings"), icon_name="settings")
        )
        toolbar.addAction(self._action("Help", lambda: self.open_dialog("Help"), icon_name="help"))

    def _apply_icons(self) -> None:
        for action, name in self._icon_actions:
            action.setIcon(icon(name))

    def changeEvent(self, event: QEvent) -> None:  # re-tint icons when the theme flips
        if event.type() == QEvent.Type.PaletteChange:
            self._apply_icons()
        super().changeEvent(event)

    # -- menu slots ---------------------------------------------------------------------------------
    def _rebuild_recent_menu(self) -> None:
        self._recent_menu.clear()
        recent = self._state.settings.prune_recent_projects(
            lambda p: ProjectService.is_project_bundle(Path(p))
        )
        if not recent:
            empty = self._recent_menu.addAction("(no recent projects)")
            empty.setEnabled(False)
            return
        for path in recent:
            self._recent_menu.addAction(
                self._action(
                    path,
                    partial(project_actions.open_project_path, self, self._state, Path(path)),
                )
            )

    def _set_theme(self, theme: str) -> None:
        self._state.settings.set_theme(theme)
        self._apply_appearance()

    def _set_style(self, style_id: str) -> None:
        self._state.settings.set_style(style_id)
        self._apply_appearance()

    def _apply_appearance(self) -> None:
        settings = self._state.settings.settings
        app = QApplication.instance()
        if isinstance(app, QApplication):
            ThemeManager(app).apply(settings.theme, settings.style)

    def _export(self, format_id: str) -> None:
        if self._state.catalog is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            f"Export {format_id.upper()}",
            f"export.{format_id}",
            _EXPORT_FILTERS[format_id],
        )
        if not destination:
            return
        statistics = self.find_screen(StatisticsScreen)
        try:
            statistics.export_to(format_id, Path(destination))
        except Exception as exc:  # surface export errors without crashing
            self.statusBar().showMessage(f"Export failed: {exc}")
            return
        self.statusBar().showMessage(f"Exported to {destination}")

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "About HerpetoID",
            f"<b>HerpetoID v{__version__}</b><br>"
            "A modular platform for non-invasive individual identification of wildlife "
            "from natural body patterns.",
        )

    # -- state --------------------------------------------------------------------------------------
    def _on_project_changed(self) -> None:
        project = self._state.project
        if project is not None:
            self.setWindowTitle(f"HerpetoID — {project.project.name}")
            self.statusBar().showMessage(f"Project: {project.project.name}")
        else:
            self.setWindowTitle("HerpetoID")
            self.statusBar().showMessage("Ready")
        for action in self._project_actions:
            action.setEnabled(project is not None)
        catalog = self._state.catalog
        species = catalog.list_species() if catalog is not None else []
        if len(species) == 1:
            self._species_status.setText(f"Species: {species[0].scientific_name}  ")
        elif species:
            self._species_status.setText(f"Species: {len(species)}  ")
        else:
            self._species_status.setText("")

    # -- navigation facade ----------------------------------------------------------------------------
    def screen_names(self) -> list[str]:
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    def current_screen_name(self) -> str:
        return self._tabs.tabText(self._tabs.currentIndex())

    def navigate_to(self, name: str) -> None:
        """Switch to a tab or open a dialog; accepts both new and legacy screen names."""
        if name in _DIALOG_NAMES:
            self.open_dialog(name)
            return
        target = _LEGACY_TABS.get(name, name)
        for i in range(self._tabs.count()):
            if self._tabs.tabText(i) == target:
                self._tabs.setCurrentIndex(i)
                if name in ("Candidates", "Comparison"):
                    identification = self.find_screen(IdentificationScreen)
                    identification.set_mode("compare" if name == "Comparison" else "identify")
                return

    def _open_observation(self, observation_id: int) -> None:
        """Jump to the Observations tab with the given record selected (dock navigation)."""
        self.navigate_to("Observations")
        self.find_screen(ObservationsScreen).select_observation(observation_id)

    def _open_individual(self, individual_id: int) -> None:
        """Jump to the Individuals tab with the given record selected (dock navigation)."""
        self.navigate_to("Individuals")
        self.find_screen(IndividualBrowserScreen).select_individual(individual_id)

    def find_screen(self, cls: type[_ScreenT]) -> _ScreenT:
        """The tab widget of the given screen class (raises KeyError if it is not a tab)."""
        for i in range(self._tabs.count()):
            widget = self._tabs.widget(i)
            if isinstance(widget, cls):
                return widget
        raise KeyError(cls.__name__)

    def open_dialog(self, name: str) -> QWidget:
        """Show the named cached dialog (creating it on first use) and return its embedded screen."""
        dialog = self._dialogs.get(name)
        if dialog is None:
            dialog = self._create_dialog(name)
            self._dialogs[name] = dialog
        dialog.open_raised()
        return dialog.screen_widget

    def _create_dialog(self, name: str) -> ScreenDialog:
        state = self._state
        if name == "Projects":
            return ScreenDialog("Projects", ProjectManagerScreen(state), self)
        if name == "Import":
            return ScreenDialog(
                "Add Observations", ImageImportScreen(state), self, width=860, height=620
            )
        if name == "Settings":
            return ScreenDialog("Settings", SettingsScreen(state), self, width=440, height=320)
        if name == "Plugins":
            return ScreenDialog("Plugin Manager", PluginManagerScreen(state.registry), self)
        if name == "Help":
            return ScreenDialog("User Manual", HelpScreen(), self, width=920, height=640)
        raise KeyError(name)
