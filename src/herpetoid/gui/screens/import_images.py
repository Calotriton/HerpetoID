"""Image Import screen: add image files as observations, with a thumbnail gallery of imports."""

from __future__ import annotations

from logging import getLogger
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSize, Qt
from PySide6.QtGui import QIcon, QImageReader, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
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

from herpetoid.application.image_discovery import collect_images
from herpetoid.domain import PluginRef
from herpetoid.gui.formatting import format_date
from herpetoid.gui.state import AppState
from herpetoid.infrastructure.capture_date import capture_date_for
from herpetoid.infrastructure.paths import BundlePathError

_IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp)"
_THUMB = QSize(140, 140)
_CELL = QSize(156, 178)  # thumbnail + a two-line caption
_STAGED_THUMB = QSize(72, 72)
#: Placeholder shown until a species is chosen. Carries no data, so nothing can import under it.
_NO_SPECIES = "— Select a species —"
#: Above this many files, a folder selection asks for confirmation before staging: a whole card
#: dump picked by mistake would otherwise decode thumbnails for minutes with no way back.
_LARGE_SELECTION = 300
_OBSERVATION_ROLE = Qt.ItemDataRole.UserRole
_LOGGER = getLogger("herpetoid.gui.import")


class ImageImportScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._module_by_species: dict[str, PluginRef] = {}
        self._staged: list[Path] = []
        #: (filename, reason) for every file the last import could not read.
        self.last_import_errors: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # A form makes the two required inputs read top-to-bottom and clearly labelled.
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.species_combo = QComboBox()
        self.species_combo.setMinimumWidth(240)
        self.species_combo.setToolTip(
            "The species module that will interpret these captures. It decides the measurement "
            "fields, how the pattern is read and which captures are compared against each other "
            "— it can be changed later from Project → Change Species…"
        )
        self.species_combo.currentIndexChanged.connect(self._update_add_enabled)
        form.addRow("Species *", self.species_combo)
        self.observer_edit = QLineEdit()
        self.observer_edit.setPlaceholderText("Required — type the observer's name before adding images")
        self.observer_edit.setClearButtonEnabled(True)
        self.observer_edit.textChanged.connect(self._update_add_enabled)
        form.addRow("Observer *", self.observer_edit)
        layout.addLayout(form)

        # Two explicit steps: (1) select files — staged only, nothing touches the project yet;
        # (2) press Import to actually add them. Closing the dialog without importing imports nothing.
        actions = QHBoxLayout()
        self.add_button = QPushButton("Select images…")
        self.add_button.clicked.connect(self._choose_files)
        actions.addWidget(self.add_button)
        # Field photographs arrive as a folder tree (one per site, day or camera), so selecting the
        # session folder must be enough — the researcher should not have to open every subfolder.
        self.add_folder_button = QPushButton("Select folder…")
        self.add_folder_button.setToolTip(
            "Select a folder and stage every image inside it, including all of its subfolders"
        )
        self.add_folder_button.clicked.connect(self._choose_folder)
        actions.addWidget(self.add_folder_button)
        self.import_button = QPushButton("Import 0 images")
        self.import_button.setObjectName("primary")
        self.import_button.clicked.connect(self._import_staged)
        actions.addWidget(self.import_button)
        self.clear_staged_button = QPushButton("Clear selection")
        self.clear_staged_button.clicked.connect(self._clear_staged)
        actions.addWidget(self.clear_staged_button)
        self.add_hint = QLabel("Enter an observer name to enable importing.")
        self.add_hint.setStyleSheet("color: palette(mid);")
        actions.addWidget(self.add_hint)
        actions.addStretch(1)
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setToolTip("Remove the selected image(s) — or press Del in the gallery")
        self.delete_button.clicked.connect(self._delete_selected)
        actions.addWidget(self.delete_button)
        layout.addLayout(actions)

        self.staged_label = QLabel("<b>Selected for import</b> (not imported yet)")
        layout.addWidget(self.staged_label)
        self.staged_list = QListWidget()
        self.staged_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.staged_list.setIconSize(QSize(72, 72))
        self.staged_list.setGridSize(QSize(88, 104))
        self.staged_list.setUniformItemSizes(True)
        self.staged_list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.staged_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.staged_list.setMovement(QListWidget.Movement.Static)
        self.staged_list.setFixedHeight(118)
        layout.addWidget(self.staged_list)

        self.status_label = QLabel()
        layout.addWidget(self.status_label)
        self.hint_label = QLabel("Open or create a project first (File → New/Open Project).")
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
        has_project = self._state.project is not None
        has_observer = bool(self.observer_edit.text().strip())
        has_species = self.selected_species() is not None
        self.add_button.setEnabled(has_project)
        self.add_folder_button.setEnabled(has_project)
        self.import_button.setEnabled(
            has_project and has_observer and has_species and bool(self._staged)
        )
        self.import_button.setText(
            f"Import {len(self._staged)} image(s)" if self._staged else "Import 0 images"
        )
        self.clear_staged_button.setEnabled(bool(self._staged))
        # Say which of the two required answers is still missing, rather than a dead button.
        missing = [
            label
            for label, given in (("a species", has_species), ("an observer name", has_observer))
            if not given
        ]
        if missing:
            self.add_hint.setText(f"Choose {' and '.join(missing)} to enable importing.")
        self.add_hint.setVisible(has_project and bool(self._staged) and bool(missing))
        has_staged = bool(self._staged)
        self.staged_label.setText(
            f"<b>Selected for import</b> — {len(self._staged)} image(s), not imported yet"
        )
        self.staged_label.setVisible(has_staged)
        self.staged_list.setVisible(has_staged)

    def _update_delete_enabled(self) -> None:
        self.delete_button.setEnabled(bool(self.gallery.selectedItems()))

    def _populate_species(self) -> None:
        """Offer the installed species — but never pick one on the researcher's behalf.

        A silent default is how a whole session ends up filed under the wrong species: the combo
        showed a name nobody chose. So an unclaimed project opens on a placeholder and Import stays
        disabled until a species is actually selected. A project that already holds exactly one
        species has declared itself, and that one is preselected: repeat imports stay one click.
        """
        current = self.selected_species()
        catalog = self._state.catalog
        self.species_combo.blockSignals(True)
        self.species_combo.clear()
        self._module_by_species = dict(self._state.registry.species_offered())
        in_project = [s.scientific_name for s in catalog.list_species()] if catalog else []
        settled = current or (in_project[0] if len(in_project) == 1 else None)
        if settled is None:
            self.species_combo.addItem(_NO_SPECIES, None)
        for name in sorted(self._module_by_species):
            self.species_combo.addItem(name, name)
        if settled is not None:
            index = self.species_combo.findData(settled)
            self.species_combo.setCurrentIndex(max(index, 0))
        self.species_combo.blockSignals(False)

    def selected_species(self) -> str | None:
        """The chosen species name, or ``None`` while the placeholder is showing."""
        data = self.species_combo.currentData()
        return str(data) if data else None

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
            try:  # bundle paths are untrusted input; never render a file from outside the bundle
                thumbnail = project.image_store.resolve(image.thumbnail_path)
            except BundlePathError:
                continue
            pixmap = QPixmap(str(thumbnail))
            if pixmap.isNull():
                continue
            item = QListWidgetItem(QIcon(pixmap), image.original_filename)
            item.setToolTip(image.original_filename)  # full name on hover; the cell shows an elided one
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            item.setSizeHint(_CELL)
            item.setData(_OBSERVATION_ROLE, image.observation_id)  # so we can delete its observation
            self.gallery.addItem(item)

    def _choose_files(self) -> None:
        """Stage files for import — nothing is added to the project until Import is pressed."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select images", "", _IMAGE_FILTER)
        if not files:
            return
        self.stage_files([Path(f) for f in files])

    def _choose_folder(self) -> None:
        """Stage every image in a chosen folder *and all of its subfolders*."""
        chosen = QFileDialog.getExistingDirectory(
            self, "Select a folder of images (subfolders included)"
        )
        if not chosen:
            return
        folder = Path(chosen)
        found = self.scan_folder(folder)
        if not found:
            QMessageBox.information(
                self,
                "No images found",
                f"“{folder.name}” and its subfolders contain no supported image files.\n\n"
                "Supported formats: PNG, JPEG, TIFF, BMP.",
            )
            return
        if len(found) > _LARGE_SELECTION:
            confirm = QMessageBox.question(
                self,
                "Large selection",
                f"{len(found)} images were found in “{folder.name}” and its subfolders.\n\n"
                "Stage all of them? This can take a while.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
        added = self.stage_files(found)
        self.status_label.setText(
            f"{added} image(s) staged from “{folder.name}” and its subfolders"
            + (f" ({len(found) - added} already selected)." if added < len(found) else ".")
        )

    def scan_folder(self, folder: Path) -> list[Path]:
        """Every image under ``folder``, subfolders included. Slow on a big tree — show a wait cursor."""
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            return collect_images(folder)
        finally:
            QApplication.restoreOverrideCursor()

    def stage_files(self, paths: list[Path]) -> int:
        """Add ``paths`` to the staging strip, skipping any already there. Returns how many were new."""
        already = set(self._staged)
        added = 0
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for path in paths:
                if path in already:
                    continue
                already.add(path)
                self._staged.append(path)
                item = QListWidgetItem(_thumbnail_icon(path), path.name)
                item.setToolTip(_staged_tooltip(path))
                item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
                self.staged_list.addItem(item)
                added += 1
        finally:
            QApplication.restoreOverrideCursor()
        self._update_add_enabled()
        return added

    def staged_files(self) -> list[Path]:
        return list(self._staged)

    def _clear_staged(self) -> None:
        self._staged.clear()
        self.staged_list.clear()
        self._update_add_enabled()

    def _import_staged(self) -> None:
        if not self._staged:
            return
        count = self.import_files(list(self._staged))
        self._clear_staged()
        if self.last_import_errors:
            detail = "\n".join(f"{name}: {reason}" for name, reason in self.last_import_errors)
            QMessageBox.warning(
                self,
                "Import finished with errors",
                f"Imported {count} image(s). {len(self.last_import_errors)} could not be read:"
                f"\n\n{detail}",
            )
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
        """Import each path as a new observation (one observation per image).

        Each observation's date is pre-filled from the file's own name or the folders it came from
        (``IMG_20230715_1425.JPG``, ``2023-07-15 Riu Aigües/…``), and failing that from the
        camera's EXIF metadata; the researcher can still change it on the Observations tab. A file
        that states a date nowhere leaves the field empty rather than guessing.

        Returns the number imported. A file that cannot be read (corrupt, not an image, or too large
        to decode) is skipped and recorded in :attr:`last_import_errors` rather than aborting the
        batch -- a single bad card-reader file must not cost the researcher the rest of the import.
        """
        self.last_import_errors = []
        catalog = self._state.catalog
        if catalog is None:
            return 0
        species_name = self.selected_species()
        if species_name is None:  # nothing is imported until a species is actually chosen
            return 0
        module = self._module_by_species.get(species_name)
        species = catalog.ensure_species(species_name, module=module)
        assert species.id is not None
        observer = self.observer_edit.text().strip()
        imported = 0
        for path in paths:
            try:
                found = capture_date_for(path)
                catalog.import_observation(
                    species.id,
                    [path],
                    observer=observer,
                    observed_at=found.value if found else None,
                )
            except Exception as exc:  # malformed images raise a wide variety of decoder errors
                _LOGGER.warning("Could not import %s: %s", path, exc)
                self.last_import_errors.append((path.name, str(exc)))
                continue
            imported += 1
        # Notify every screen (this one included) so the new observations appear everywhere.
        self._state.project_changed.emit()
        return imported


def _thumbnail_icon(path: Path) -> QIcon:
    """A small icon for ``path``, decoded at thumbnail size.

    Staging a folder can mean hundreds of 20-megapixel frames, and decoding each one at full size
    just to shrink it would stall the window for minutes — :class:`QImageReader` lets the decoder
    produce the reduced image directly.
    """
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # honor EXIF orientation, as the real import does
    size = reader.size()
    too_big = size.width() > _STAGED_THUMB.width() or size.height() > _STAGED_THUMB.height()
    if size.isValid() and too_big:  # never upscale a small file just to fill the cell
        reader.setScaledSize(size.scaled(_STAGED_THUMB, Qt.AspectRatioMode.KeepAspectRatio))
    image = reader.read()
    return QIcon(QPixmap.fromImage(image)) if not image.isNull() else QIcon()


def _staged_tooltip(path: Path) -> str:
    """The full path, plus the date found for it — and where — so it can be checked beforehand."""
    found = capture_date_for(path)
    if found is None:
        return str(path)
    return f"{path}\nDate from {found.source}: {format_date(found.value)}"
