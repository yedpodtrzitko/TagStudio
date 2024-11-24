from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from src.core.library import Library
from src.core.library.alchemy.models import Folder
from src.qt.enums import WindowContent

if TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

logger = structlog.get_logger()


class LibraryDirsWidget(QWidget):
    library_dirs: dict[str, Folder]

    def __init__(self, library: Library, driver: QtDriver):
        super().__init__()

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)

        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )

        self.driver = driver
        self.library = library

        # label and button
        self.create_panel()

        # actual library dirs
        self.items_layout = QVBoxLayout()
        self.root_layout.addLayout(self.items_layout)

        self.library_dirs = {}
        # check if library is open
        self.refresh()

    def refresh(self):
        if not self.library.storage_path:
            logger.info("library_dirs.refresh: no library open")
            return

        self.driver.main_window.set_main_content(WindowContent.LIBRARY_CONTENT)

        library_dirs = {x.uuid: x for x in self.library.get_folders()}
        if library_dirs.keys() == self.library_dirs.keys():
            # most likely no reason to refresh
            logger.info(
                "library_dirs.refresh: no change in library dirs",
                prev=self.library_dirs,
                new=library_dirs,
            )
            return

        self.library_dirs = library_dirs
        self.fill_dirs(self.library_dirs)

    def create_panel(self):
        label = QLabel("Library Folders")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        row_layout = QHBoxLayout()
        row_layout.addWidget(label)
        self.root_layout.addLayout(row_layout)

        # add a button which will open a library folder dialog
        button = QPushButton("Add Folder")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(self.add_folders_callback)
        self.root_layout.addWidget(button)

    def add_folders_callback(self):
        """Open QT dialog to select a folder to add into library.

        Allow multiple folders selection when holding Shift
        """
        if not self.library.storage_path:
            logger.info("add_folder: no library open")
            return

        dialog = QFileDialog(self)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly)

        mods = QApplication.keyboardModifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            dialog.setOption(QFileDialog.Option.DontUseNativeDialog)
            selection_mode = QAbstractItemView.SelectionMode.ExtendedSelection
            dialog.findChildren(QListView)[0].setSelectionMode(selection_mode)  # type: ignore
            dialog.findChildren(QTreeView)[0].setSelectionMode(selection_mode)  # type: ignore

        if dialog.exec() == QFileDialog.DialogCode.Accepted:
            selected_dirs = dialog.selectedFiles()
            added_folders = []

            logger.info("add_folders", selected_dirs=selected_dirs)

            for dir_path in selected_dirs:
                if folder := self.library.add_folder(Path(dir_path)):
                    added_folders.append(folder)

            if added_folders:
                self.driver.add_new_files_callback(added_folders)
                self.driver.filter_items()
                self.refresh()

    def fill_dirs(self, folders: dict[str, Folder]) -> None:
        def clear_layout(layout_item: QVBoxLayout):
            for i in reversed(range(layout_item.count())):
                child = layout_item.itemAt(i)
                if child.widget() is not None:
                    child.widget().deleteLater()
                elif child.layout() is not None:
                    clear_layout(child.layout())  # type: ignore
                    # remove any potential previous items

        clear_layout(self.items_layout)

        for folder in folders.values():
            self.create_item(folder)

    def create_item(self, folder: Folder):
        def toggle_folder():
            self.driver.filter.toggle_folder(folder.id)
            self.driver.filter_items()

        button_toggle = QCheckBox()
        button_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        button_toggle.setFixedWidth(30)
        # TODO - figure out which one to check
        button_toggle.setChecked(True)  # item.id not in self.driver.filter.exclude_folders)

        button_toggle.clicked.connect(toggle_folder)

        folder_label = QLabel()
        folder_label.setText(folder.path.name)
        folder_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        row_layout = QHBoxLayout()
        row_layout.addWidget(button_toggle)
        row_layout.addWidget(folder_label)

        self.items_layout.addLayout(row_layout)
