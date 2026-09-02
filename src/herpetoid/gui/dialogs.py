"""Dialogs: the non-modal wrappers hosting the secondary screens, and the Change Species dialog.

The screens themselves are unchanged widgets; the main window creates each dialog once, caches it and
re-shows it, so ``project_changed`` connections stay stable and (e.g.) the import gallery keeps its
session history. Always shown with :meth:`QDialog.show` (non-modal) — the workflow tabs keep updating
live while a dialog is open, and modal ``exec()`` would block headless test drivers.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import FieldDefinition
from herpetoid.application.catalog_service import SpeciesReassignment
from herpetoid.domain import Observation
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.info_table import species_field_definitions


class ScreenDialog(QDialog):
    """A plain dialog that hosts one embedded screen widget."""

    def __init__(
        self,
        title: str,
        screen: QWidget,
        parent: QWidget | None = None,
        *,
        width: int = 760,
        height: int = 560,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.screen_widget = screen  # "screen" would shadow QWidget.screen()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(screen)
        self.resize(width, height)

    def open_raised(self) -> None:
        """Show non-modal and bring to front (re-showing an already-open dialog raises it)."""
        self.show()
        self.raise_()
        self.activateWindow()


class ChangeSpeciesDialog(QDialog):
    """Move observations from one species to another.

    The fix for a mistake this application makes easy to commit: a whole session imported under
    whichever species happened to be selected. Nothing photographed or measured is discarded — only
    which species module interprets it changes — so it can be corrected in place rather than forcing
    a re-import. :meth:`~herpetoid.application.catalog_service.CatalogService.reassign_species`
    documents what happens to individuals, the one thing that cannot simply follow.

    Shown with :meth:`QDialog.open` (window-modal but non-blocking), so a headless driver can reach
    :meth:`apply_change` without an event loop.
    """

    def __init__(
        self,
        state: AppState,
        parent: QWidget | None = None,
        *,
        observation_id: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change Species")
        self._state = state
        self._observation_id = observation_id
        #: What the last applied change did — ``None`` until :meth:`apply_change` succeeds.
        self.report: SpeciesReassignment | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        intro = QLabel(
            "Photographs, marked regions and everything already recorded are kept. What changes is "
            "the species module that interprets them: which measurement fields you see, how the "
            "pattern is read, and which captures are compared against each other."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self.from_combo = QComboBox()
        self.from_combo.setMinimumWidth(280)
        form.addRow("Recorded as", self.from_combo)
        self.to_combo = QComboBox()
        form.addRow("Change to", self.to_combo)
        self.scope_combo = QComboBox()
        form.addRow("Apply to", self.scope_combo)
        layout.addLayout(form)

        self.consequences = QLabel()
        self.consequences.setWordWrap(True)
        self.consequences.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.consequences)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.apply_button = buttons.addButton(
            "Change species", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self._on_apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._populate_sources()
        self.from_combo.currentIndexChanged.connect(self._on_source_changed)
        self.to_combo.currentIndexChanged.connect(self._update_consequences)
        self.scope_combo.currentIndexChanged.connect(self._update_consequences)
        self._on_source_changed()
        self.resize(560, 400)

    # -- what the user can choose ------------------------------------------------------------
    def _populate_sources(self) -> None:
        catalog = self._state.catalog
        if catalog is None:
            return
        counts: dict[int, int] = {}
        for recorded in catalog.list_observations():
            counts[recorded.species_id] = counts.get(recorded.species_id, 0) + 1
        for species in catalog.list_species():
            self.from_combo.addItem(
                f"{species.scientific_name}  ·  {counts.get(species.id or -1, 0)} observation(s)",
                species.id,
            )
        if self._observation_id is not None:
            observation = catalog.get_observation(self._observation_id)
            if observation is not None:
                index = self.from_combo.findData(observation.species_id)
                if index >= 0:
                    self.from_combo.setCurrentIndex(index)

    def _on_source_changed(self) -> None:
        """Rebuild the destination and scope choices for the selected source species."""
        catalog = self._state.catalog
        source_id = self.from_combo.currentData()
        source = catalog.get_species(source_id) if catalog is not None and source_id else None

        self.to_combo.blockSignals(True)
        self.to_combo.clear()
        for name in sorted(self._state.registry.species_offered()):
            if source is None or name != source.scientific_name:
                self.to_combo.addItem(name, name)
        self.to_combo.blockSignals(False)

        self.scope_combo.blockSignals(True)
        self.scope_combo.clear()
        total = len(catalog.observations_for_species(source_id)) if catalog and source_id else 0
        label = source.scientific_name if source is not None else "this species"
        self.scope_combo.addItem(f"All {total} observation(s) of {label}", "all")
        if self._observation_id is not None and catalog is not None:
            observation = catalog.get_observation(self._observation_id)
            if observation is not None and observation.species_id == source_id:
                self.scope_combo.addItem(f"Only observation #{self._observation_id}", "one")
                # Opened from a selected row: that row is the likelier intent, so offer it first.
                self.scope_combo.setCurrentIndex(1)
        self.scope_combo.blockSignals(False)
        self._update_consequences()

    def observation_ids(self) -> list[int]:
        """The observations the current choices would move."""
        catalog = self._state.catalog
        if catalog is None:
            return []
        if self.scope_combo.currentData() == "one" and self._observation_id is not None:
            return [self._observation_id]
        source_id = self.from_combo.currentData()
        if not source_id:
            return []
        return [
            observation.id
            for observation in catalog.observations_for_species(source_id)
            if observation.id is not None
        ]

    # -- saying what it will cost, before it is done -------------------------------------------
    def _update_consequences(self) -> None:
        catalog = self._state.catalog
        target = self.to_combo.currentData()
        moving = self.observation_ids()
        if catalog is None or not target or not moving:
            self.consequences.setText("")
            self.apply_button.setEnabled(False)
            return
        self.apply_button.setEnabled(True)

        observations = [catalog.get_observation(i) for i in moving]
        lines = [f"<b>{len(moving)} observation(s)</b> will be recorded as {target}."]
        hidden = self._values_the_target_does_not_use(target, observations)
        if hidden:
            lines.append(
                f"Values {target} does not use are kept in the project but stop being shown: "
                f"{', '.join(hidden)}. Changing back restores them."
            )
        if any(o is not None and o.individual_id is not None for o in observations):
            lines.append(
                "An individual whose captures all move keeps its code and moves with them. A "
                "capture that would leave an individual behind is unlinked instead, keeping its "
                "code as a pending one to re-confirm on the Identification tab."
            )
        lines.append("Any identification already run should be run again under the new module.")
        self.consequences.setText("<br><br>".join(lines))

    def _values_the_target_does_not_use(
        self, target: str, observations: list[Observation | None]
    ) -> list[str]:
        """Labels of measurements recorded on the moving observations the destination won't show."""
        source_fields = {
            f.key: f.label
            for f in species_field_definitions(self._state, self.from_combo.currentData() or 0)
        }
        target_keys = {f.key for f in self._target_fields(target)}
        recorded: set[str] = set()
        for observation in observations:
            if observation is None:
                continue
            recorded.update(
                key
                for key, value in observation.measurements.items()
                if not key.startswith("_") and value not in (None, "")
            )
        return sorted(source_fields.get(key, key) for key in recorded - target_keys)

    def _target_fields(self, target: str) -> tuple[FieldDefinition, ...]:
        """The fields the destination module declares, read from the registry.

        Not from the project: the destination species may not have a row there yet, and the module
        is the authority on its own fields either way.
        """
        ref = self._state.registry.species_offered().get(target)
        if ref is None:
            return ()
        try:
            module = self._state.registry.create_module(ref.plugin_id)
            return tuple(module.define_observation_fields())
        except Exception:  # a broken module must not break the dialog
            return ()

    # -- doing it -------------------------------------------------------------------------------
    def apply_change(self) -> SpeciesReassignment | None:
        """Perform the change. Returns what it did, or ``None`` when there was nothing to do."""
        catalog = self._state.catalog
        target = self.to_combo.currentData()
        moving = self.observation_ids()
        if catalog is None or not target or not moving:
            return None
        species = catalog.ensure_species(
            target, module=self._state.registry.species_offered().get(target)
        )
        if species.id is None:
            return None
        self.report = catalog.reassign_species(moving, species.id)
        # Every screen re-reads: the observations table, the species-driven form, statistics, dock.
        self._state.project_changed.emit()
        return self.report

    def _on_apply(self) -> None:
        try:
            report = self.apply_change()
        except Exception as exc:  # a failed move must say so, not close as though it worked
            QMessageBox.warning(self, "Could not change species", str(exc))
            return
        if report is None:
            QMessageBox.information(self, "Nothing to change", "No observations were selected.")
            return
        QMessageBox.information(self, "Species changed", summarize_reassignment(report))
        self.accept()


def summarize_reassignment(report: SpeciesReassignment) -> str:
    """A plain-language account of what a species change did."""
    lines = [f"Moved {report.observations} observation(s)."]
    if report.individuals_moved:
        lines.append(
            f"{len(report.individuals_moved)} individual(s) moved across with their captures: "
            f"{', '.join(report.individuals_moved)}."
        )
    if report.observations_unlinked:
        lines.append(
            f"{len(report.observations_unlinked)} observation(s) were unlinked from an individual "
            "that stayed behind. Their codes are kept as pending — confirm them on the "
            "Identification tab."
        )
    if report.species_removed:
        lines.append(
            f"{', '.join(report.species_removed)} was removed from the project: nothing was left "
            "recorded under it."
        )
    return "\n\n".join(lines)
