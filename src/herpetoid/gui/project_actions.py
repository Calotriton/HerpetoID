"""Project create/open flows shared by the menu bar, toolbar and the Projects dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QWidget

from herpetoid.gui.state import AppState


def new_project(parent: QWidget, state: AppState) -> None:
    """Ask for a folder + name and create a project bundle there (warns on failure)."""
    directory = QFileDialog.getExistingDirectory(
        parent, "Choose an empty folder for the new project"
    )
    if not directory:
        return
    name, accepted = QInputDialog.getText(parent, "New Project", "Project name:")
    if not accepted or not name.strip():
        return
    try:
        state.create_project(Path(directory), name.strip())
    except (FileExistsError, OSError) as exc:
        QMessageBox.warning(parent, "Could not create project", str(exc))


def open_project_dialog(parent: QWidget, state: AppState) -> None:
    """Ask for a project folder and open it."""
    directory = QFileDialog.getExistingDirectory(parent, "Open project folder")
    if directory:
        open_project_path(parent, state, Path(directory))


def open_project_path(parent: QWidget, state: AppState, path: Path) -> None:
    """Open the bundle at ``path`` (no-op if already open; warns on failure)."""
    current = state.project
    if current is not None and Path(current.path) == path:
        return  # already open (guards against double-click firing two signals)
    try:
        state.open_project(path)
    except (FileNotFoundError, ValueError) as exc:
        QMessageBox.warning(parent, "Could not open project", str(exc))
