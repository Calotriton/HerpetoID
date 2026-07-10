"""Non-modal dialog wrappers hosting the secondary screens (Projects, Import, Settings, …).

The screens themselves are unchanged widgets; the main window creates each dialog once, caches it and
re-shows it, so ``project_changed`` connections stay stable and (e.g.) the import gallery keeps its
session history. Always shown with :meth:`QDialog.show` (non-modal) — the workflow tabs keep updating
live while a dialog is open, and modal ``exec()`` would block headless test drivers.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget


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
