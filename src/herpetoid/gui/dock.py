"""The collapsible left project panel: a project tree plus quick stats.

Toggleable from the View menu (``QDockWidget.toggleViewAction``). Activating a tree entry navigates
to the matching workflow tab.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.gui.state import AppState

_NAV_ROLE = Qt.ItemDataRole.UserRole


class ProjectDock(QDockWidget):
    def __init__(self, state: AppState, navigate: Callable[[str], None]) -> None:
        super().__init__("Project")
        self.setObjectName("projectDock")
        self._state = state
        self._navigate = navigate
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
        )

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemActivated.connect(self._on_item_activated)
        self.tree.itemClicked.connect(self._on_item_activated)
        layout.addWidget(self.tree, 1)

        stats_header = QLabel("QUICK STATS")
        stats_header.setStyleSheet(
            "font-size: 10px; letter-spacing: 1px; color: palette(mid); font-weight: 600;"
        )
        layout.addWidget(stats_header)
        self.stats_label = QLabel()
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)

        self.setWidget(container)
        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self.tree.clear()
        project = self._state.project
        catalog = self._state.catalog
        if project is None or catalog is None:
            placeholder = QTreeWidgetItem(["No project open"])
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(placeholder)
            self.stats_label.setText("—")
            return

        observations = catalog.list_observations()
        individuals = catalog.list_individuals()

        root = QTreeWidgetItem([project.project.name])
        root.setData(0, _NAV_ROLE, "Dashboard")
        obs_item = QTreeWidgetItem([f"Observations ({len(observations)})"])
        obs_item.setData(0, _NAV_ROLE, "Observations")
        ind_item = QTreeWidgetItem([f"Individuals ({len(individuals)})"])
        ind_item.setData(0, _NAV_ROLE, "Individuals")
        stats_item = QTreeWidgetItem(["Statistics"])
        stats_item.setData(0, _NAV_ROLE, "Statistics")
        root.addChildren([obs_item, ind_item, stats_item])
        for species in catalog.list_species():
            species_item = QTreeWidgetItem([species.scientific_name])
            species_item.setData(0, _NAV_ROLE, "Individuals")
            root.addChild(species_item)
        self.tree.addTopLevelItem(root)
        self.tree.expandAll()

        report = self._state.statistics.compute(
            individuals=individuals, observations=observations
        )
        self.stats_label.setText(
            f"Individuals: {report.individual_count}\n"
            f"Observations: {report.observation_count}\n"
            f"Recaptures: {report.recapture_count}"
        )

    def _on_item_activated(self, item: QTreeWidgetItem) -> None:
        target = item.data(0, _NAV_ROLE)
        if isinstance(target, str):
            self._navigate(target)
