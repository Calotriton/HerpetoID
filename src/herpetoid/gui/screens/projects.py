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

from herpetoid.gui.state import AppState


class ProjectManagerScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        buttons = QHBoxLayout()
        new_button = QPushButton("New Project…")
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

        layout.addWidget(QLabel("<b>Recent projects</b>"))
        self.recent_list = QListWidget()
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
        for path in self._state.settings.settings.recent_projects:
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
        try:
            self._state.open_project(path)
        except (FileNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Could not open project", str(exc))
