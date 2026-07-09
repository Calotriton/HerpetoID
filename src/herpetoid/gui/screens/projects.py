"""Project Manager screen: create / open portable project bundles and list recent ones."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from herpetoid.application.project_service import ProjectService
from herpetoid.gui.state import AppState


class ProjectManagerScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        title = QLabel("Projects")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        buttons = QHBoxLayout()
        new_button = QPushButton("New Project…")
        new_button.setObjectName("primary")
        new_button.clicked.connect(self._new_project)
        open_button = QPushButton("Open Project…")
        open_button.clicked.connect(self._open_project)
        buttons.addWidget(new_button)
        buttons.addWidget(open_button)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        self.current_label = QLabel()
        self.current_label.setStyleSheet("margin-top: 8px;")
        layout.addWidget(self.current_label)

        recent_header = QLabel("<b>Recent projects</b>")
        layout.addWidget(recent_header)
        hint = QLabel("Double-click a project (or select it and press Enter) to open it.")
        hint.setStyleSheet("color: palette(mid); font-size: 12px;")
        layout.addWidget(hint)
        self.recent_list = QListWidget()
        # itemActivated fires on double-click and on Enter, so both open the selected project.
        self.recent_list.itemActivated.connect(self._open_recent)
        self.recent_list.itemDoubleClicked.connect(self._open_recent)
        layout.addWidget(self.recent_list, 1)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        project = self._state.project
        if project is not None:
            self.current_label.setText(
                f"Current project: <b>{project.project.name}</b> — {project.path}"
            )
        else:
            self.current_label.setText("No project open.")
        self.recent_list.clear()
        # Only list bundles that still exist, so deleted/temporary folders don't linger in the list.
        recent = self._state.settings.prune_recent_projects(
            lambda p: ProjectService.is_project_bundle(Path(p))
        )
        for path in recent:
            self.recent_list.addItem(QListWidgetItem(path))

    def _new_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "Choose an empty folder for the new project"
        )
        if not directory:
            return
        name, accepted = QInputDialog.getText(self, "New Project", "Project name:")
        if not accepted or not name.strip():
            return
        try:
            self._state.create_project(Path(directory), name.strip())
        except (FileExistsError, OSError) as exc:
            QMessageBox.warning(self, "Could not create project", str(exc))

    def _open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Open project folder")
        if directory:
            self._open_path(Path(directory))

    def _open_recent(self, item: QListWidgetItem) -> None:
        self._open_path(Path(item.text()))

    def _open_path(self, path: Path) -> None:
        current = self._state.project
        if current is not None and Path(current.path) == path:
            return  # already open (guards against double-click firing two signals)
        try:
            self._state.open_project(path)
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Could not open project", str(exc))
