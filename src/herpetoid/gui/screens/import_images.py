"""Image Import screen: add image files as observations, with a thumbnail gallery of imports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from herpetoid.domain import PluginRef
from herpetoid.gui.state import AppState

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)"
_THUMB = QSize(140, 140)
_CELL = QSize(156, 178)  # thumbnail + a two-line caption
_OBSERVATION_ROLE = Qt.ItemDataRole.UserRole


class ImageImportScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._module_by_species: dict[str, PluginRef] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # A form makes the two required inputs read top-to-bottom and clearly labelled.
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.species_combo = QComboBox()
        self.species_combo.setMinimumWidth(240)
        form.addRow("Species", self.species_combo)
        self.observer_edit = QLineEdit()
        self.observer_edit.setPlaceholderText("Required — type the observer's name before adding images")
        self.observer_edit.setClearButtonEnabled(True)
        self.observer_edit.textChanged.connect(self._update_add_enabled)
        form.addRow("Observer *", self.observer_edit)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add images…")
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._choose_files)
        actions.addWidget(self.add_button)
        self.add_hint = QLabel("Enter an observer name to enable importing.")
        self.add_hint.setStyleSheet("color: palette(mid);")
        actions.addWidget(self.add_hint)
        actions.addStretch(1)
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setToolTip("Remove the selected image(s) — or press Del in the gallery")
        self.delete_button.clicked.connect(self._delete_selected)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.hint_label = QLabel("Open or create a project first (Projects tab).")
        layout.addWidget(self.hint_label)

        self.gallery = QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setIconSize(_THUMB)
        self.gallery.setGridSize(_CELL)  # bounds each cell so the caption can't dwarf the thumbnail
        self.gallery.setUniformItemSizes(True)
        self.gallery.setWordWrap(True)
        self.gallery.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setSpacing(8)
        # Shift/Ctrl+click to select ranges/multiples; Del deletes the selection (via the event filter).
        self.gallery.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.gallery.installEventFilter(self)
        self.gallery.itemSelectionChanged.connect(self._update_delete_enabled)
        layout.addWidget(self.gallery, 1)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.gallery and event.type() == QEvent.Type.KeyPress:
            assert isinstance(event, QKeyEvent)
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._delete_selected()
                return True
        return super().eventFilter(obj, event)

    def _refresh(self) -> None:
        has_project = self._state.project is not None
        self.species_combo.setEnabled(has_project)
        self.observer_edit.setEnabled(has_project)
        self.hint_label.setVisible(not has_project)
        self._populate_species()
        self._update_status()
        self._populate_gallery()
        self._update_add_enabled()
        self._update_delete_enabled()

    def _update_add_enabled(self) -> None:
        ready = self._state.project is not None and bool(self.observer_edit.text().strip())
        self.add_button.setEnabled(ready)
        self.add_hint.setVisible(self._state.project is not None and not ready)

    def _update_delete_enabled(self) -> None:
        self.delete_button.setEnabled(bool(self.gallery.selectedItems()))

    def _populate_species(self) -> None:
        current = self.species_combo.currentText()
        self.species_combo.clear()
        self._module_by_species.clear()
        for record in self._state.registry.modules(enabled_only=True):
            for name in record.descriptor.supported_species:
                if name not in self._module_by_species:
                    self._module_by_species[name] = PluginRef(
                        record.descriptor.module_id, record.descriptor.version
                    )
                    self.species_combo.addItem(name)
        if current:  # keep the user's selection across refreshes
            index = self.species_combo.findText(current)
            if index >= 0:
                self.species_combo.setCurrentIndex(index)

    def _update_status(self) -> None:
        catalog = self._state.catalog
        if catalog is None:
            self.status_label.setText("")
            return
        self.status_label.setText(
            f"Observations: {catalog.observation_count()}  ·  "
            f"Individuals: {catalog.individual_count()}"
        )

    def _populate_gallery(self) -> None:
        self.gallery.clear()
        project = self._state.project
        catalog = self._state.catalog
        if project is None or catalog is None:
            return
        for image in catalog.list_images():
            if not image.thumbnail_path:
                continue
            pixmap = QPixmap(str(project.path / image.thumbnail_path))
            if pixmap.isNull():
                continue
            item = QListWidgetItem(QIcon(pixmap), image.original_filename)
            item.setToolTip(image.original_filename)  # full name on hover; the cell shows an elided one
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            item.setSizeHint(_CELL)
            item.setData(_OBSERVATION_ROLE, image.observation_id)  # so we can delete its observation
            self.gallery.addItem(item)

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

    def _delete_selected(self) -> None:
        items = self.gallery.selectedItems()
        catalog = self._state.catalog
        if not items or catalog is None:
            return
        observation_ids = {
            int(item.data(_OBSERVATION_ROLE))
            for item in items
            if item.data(_OBSERVATION_ROLE) is not None
        }
        if not observation_ids:
            return
        confirm = QMessageBox.question(
            self,
            "Delete images",
            f"Delete {len(observation_ids)} selected observation(s)? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            for observation_id in observation_ids:
                catalog.delete_observation(observation_id)
        except Exception as exc:  # surface a failure instead of silently doing nothing
            QMessageBox.warning(self, "Delete failed", str(exc))
        self._state.project_changed.emit()  # refresh this and every other screen

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
        # Notify every screen (this one included) so the new observations appear everywhere.
        self._state.project_changed.emit()
        return len(paths)
