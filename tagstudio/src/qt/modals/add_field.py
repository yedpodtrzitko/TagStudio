# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QListWidget,
)

from src.core.library import Library


class AddFieldModal(QWidget):
    def __init__(self, library: "Library"):
        # [Done]
        # - OR -
        # [Cancel] [Save]
        super().__init__()
        self.lib = library
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 6, 6, 6)

        self.title_widget = QLabel()
        self.title_widget.setObjectName("fieldTitle")
        self.title_widget.setWordWrap(True)
        self.title_widget.setStyleSheet(
            # 'background:blue;'
            # 'text-align:center;'
            "font-weight:bold;" "font-size:14px;" "padding-top: 6px"
        )
        self.title_widget.setText("Add Field")
        self.title_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)

        items = []
        for df in self.lib.default_fields:
            items.append(f'{df["name"]} ({df["type"].replace("_", " ").title()})')

        self.list_widget.addItems(items)

        self.button_container = QWidget()
        self.button_layout = QHBoxLayout(self.button_container)
        self.button_layout.setContentsMargins(6, 6, 6, 6)

        self.save_button = QPushButton()
        self.save_button.setText("Add")
        self.save_button.setDefault(True)
        self.button_layout.addWidget(self.save_button)

        self.root_layout.addWidget(self.title_widget)
        self.root_layout.addWidget(self.list_widget)

        self.root_layout.addWidget(self.button_container)

    def add_callback(self, callback: Callable):
        self.save_button.clicked.connect(
            lambda: callback(self.list_widget.selectedIndexes())
        )
