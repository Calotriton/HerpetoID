"""Plugin Manager screen: lists discovered species modules and algorithms (real registry data)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.application.registry import PluginRegistry

_HEADERS = ["ID", "Name", "Version", "Source"]


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: 600; font-size: 15px; margin-top: 8px;")
    return label


def _make_table() -> QTableWidget:
    table = QTableWidget(0, len(_HEADERS))
    table.setHorizontalHeaderLabels(_HEADERS)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    return table


def _fill(table: QTableWidget, rows: list[tuple[str, str, str, str]]) -> None:
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            table.setItem(row_index, column_index, QTableWidgetItem(str(value)))


class PluginManagerScreen(QWidget):
    """Shows installed species modules and algorithms."""

    def __init__(self, registry: PluginRegistry) -> None:
        super().__init__()
        self._registry = registry
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        layout.addWidget(_heading("Species Modules"))
        self.modules_table = _make_table()
        layout.addWidget(self.modules_table)

        layout.addWidget(_heading("Identification Algorithms"))
        self.algorithms_table = _make_table()
        layout.addWidget(self.algorithms_table)

        self.refresh()

    def refresh(self) -> None:
        _fill(
            self.modules_table,
            [
                (m.descriptor.module_id, m.descriptor.name, m.descriptor.version, m.source)
                for m in self._registry.modules()
            ],
        )
        _fill(
            self.algorithms_table,
            [
                (a.descriptor.algorithm_id, a.descriptor.name, a.descriptor.version, a.source)
                for a in self._registry.algorithms()
            ],
        )
