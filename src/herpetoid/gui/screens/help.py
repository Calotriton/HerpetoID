"""Help screen: the offline user manual with a table of contents and rendered Markdown."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QSplitter, QTextBrowser, QWidget

from herpetoid.infrastructure.docs import load_manual


class HelpScreen(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._chapters = load_manual()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.toc = QListWidget()
        self.toc.setFixedWidth(220)
        for chapter in self._chapters:
            self.toc.addItem(chapter.title)
        self.toc.currentRowChanged.connect(self._show_chapter)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)

        splitter.addWidget(self.toc)
        splitter.addWidget(self.browser)
        splitter.setSizes([220, 800])
        layout.addWidget(splitter)

        if self._chapters:
            self.toc.setCurrentRow(0)

    def _show_chapter(self, row: int) -> None:
        if 0 <= row < len(self._chapters):
            self.browser.setMarkdown(self._chapters[row].markdown)
