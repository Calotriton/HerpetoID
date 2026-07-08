"""Image Import screen: add image files as observations of a chosen species."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from herpetoid.domain import PluginRef
from herpetoid.gui.state import AppState

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)"


class ImageImportScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._module_by_species: dict[str, PluginRef] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Species:"))
        self.species_combo = QComboBox()
        self.species_combo.setMinimumWidth(220)
        controls.addWidget(self.species_combo)
        controls.addWidget(QLabel("Observer:"))
        self.observer_edit = QLineEdit()
        controls.addWidget(self.observer_edit)
        self.add_button = QPushButton("Add Images…")
        self.add_button.clicked.connect(self._choose_files)
        controls.addWidget(self.add_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.hint_label = QLabel("Open or create a project first (Projects tab).")
        layout.addWidget(self.hint_label)
        layout.addStretch(1)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        has_project = self._state.project is not None
        self.add_button.setEnabled(has_project)
        self.species_combo.setEnabled(has_project)
        self.observer_edit.setEnabled(has_project)
        self.hint_label.setVisible(not has_project)
        self._populate_species()
        self._update_status()

    def _populate_species(self) -> None:
        self.species_combo.clear()
        self._module_by_species.clear()
        for record in self._state.registry.modules(enabled_only=True):
            for name in record.descriptor.supported_species:
                if name not in self._module_by_species:
                    self._module_by_species[name] = PluginRef(
                        record.descriptor.module_id, record.descriptor.version
                    )
                    self.species_combo.addItem(name)

    def _update_status(self) -> None:
        catalog = self._state.catalog
        if catalog is None:
            self.status_label.setText("")
            return
        self.status_label.setText(
            f"Observations: {catalog.observation_count()}  ·  "
            f"Individuals: {catalog.individual_count()}"
        )

    def _choose_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Add images", "", _IMAGE_FILTER)
        if not files:
            return
        try:
            count = self.import_files([Path(f) for f in files])
        except OSError as exc:
            QMessageBox.warning(self, "Import failed", str(exc))
            return
        QMessageBox.information(self, "Import complete", f"Imported {count} image(s).")

    def import_files(self, paths: list[Path]) -> int:
        """Import each path as a new observation (one observation per image). Returns the count."""
        catalog = self._state.catalog
        if catalog is None or self.species_combo.count() == 0:
            return 0
        species_name = self.species_combo.currentText()
        module = self._module_by_species.get(species_name)
        species = catalog.ensure_species(species_name, module=module)
        assert species.id is not None
        observer = self.observer_edit.text().strip()
        for path in paths:
            catalog.import_observation(species.id, [path], observer=observer)
        self._update_status()
        return len(paths)
