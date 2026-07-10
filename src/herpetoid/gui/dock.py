"""The collapsible left project panel: a navigator over the project's actual records + quick stats.

Unlike the tab bar (which switches views), the tree lists the project's *records*: every observation
and every individual. Activating one jumps to the right tab **and selects that record**. Toggleable
from the View menu (``QDockWidget.toggleViewAction``).
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

from herpetoid.application.catalog_service import pending_code
from herpetoid.gui.state import AppState

_KIND_ROLE = Qt.ItemDataRole.UserRole
_ID_ROLE = Qt.ItemDataRole.UserRole + 1


class ProjectDock(QDockWidget):
    def __init__(
        self,
        state: AppState,
        navigate: Callable[[str], None],
        *,
        open_observation: Callable[[int], None] | None = None,
        open_individual: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__("Project")
        self.setObjectName("projectDock")
        self._state = state
        self._navigate = navigate
        self._open_observation = open_observation
        self._open_individual = open_individual
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
        codes = {i.id: i.code for i in individuals}

        root = QTreeWidgetItem([project.project.name])
        root.setData(0, _KIND_ROLE, "tab")
        root.setData(0, _ID_ROLE, "Dashboard")

        obs_group = QTreeWidgetItem([f"Observations ({len(observations)})"])
        obs_group.setData(0, _KIND_ROLE, "tab")
        obs_group.setData(0, _ID_ROLE, "Observations")
        for obs in observations:
            if obs.individual_id is not None:
                label = f"#{obs.id} · {codes.get(obs.individual_id, '?')}"
            elif (pending := pending_code(obs)) is not None:
                label = f"#{obs.id} · {pending} (pending)"
            else:
                label = f"#{obs.id} · unassigned"
            child = QTreeWidgetItem([label])
            child.setData(0, _KIND_ROLE, "observation")
            child.setData(0, _ID_ROLE, obs.id)
            obs_group.addChild(child)
        root.addChild(obs_group)

        ind_group = QTreeWidgetItem([f"Individuals ({len(individuals)})"])
        ind_group.setData(0, _KIND_ROLE, "tab")
        ind_group.setData(0, _ID_ROLE, "Individuals")
        for individual in individuals:
            child = QTreeWidgetItem([individual.code])
            child.setData(0, _KIND_ROLE, "individual")
            child.setData(0, _ID_ROLE, individual.id)
            ind_group.addChild(child)
        root.addChild(ind_group)

        stats_item = QTreeWidgetItem(["Statistics"])
        stats_item.setData(0, _KIND_ROLE, "tab")
        stats_item.setData(0, _ID_ROLE, "Statistics")
        root.addChild(stats_item)

        self.tree.addTopLevelItem(root)
        root.setExpanded(True)
        obs_group.setExpanded(len(observations) <= 12)  # keep long lists folded by default
        ind_group.setExpanded(len(individuals) <= 12)

        report = self._state.statistics.compute(
            individuals=individuals, observations=observations
        )
        self.stats_label.setText(
            f"Individuals: {report.individual_count}\n"
            f"Observations: {report.observation_count}\n"
            f"Recaptures: {report.recapture_count}"
        )

    def _on_item_activated(self, item: QTreeWidgetItem) -> None:
        kind = item.data(0, _KIND_ROLE)
        value = item.data(0, _ID_ROLE)
        if kind == "tab" and isinstance(value, str):
            self._navigate(value)
        elif kind == "observation" and value is not None and self._open_observation is not None:
            self._open_observation(int(value))
        elif kind == "individual" and value is not None and self._open_individual is not None:
            self._open_individual(int(value))
