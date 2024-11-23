# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio
from __future__ import annotations

import math
from typing import TYPE_CHECKING

import structlog
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from src.core.library import Library, Tag
from src.core.library.alchemy.enums import FilterState
from src.core.palette import ColorType, get_tag_color
from src.qt.modals.build_tag import BuildTagPanel
from src.qt.widgets.panel import PanelModal, PanelWidget
from src.qt.widgets.tag import TagWidget

if TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

logger = structlog.get_logger()


class TagDatabasePanel(PanelWidget):
    def __init__(self, library: Library, driver: QtDriver = None, is_popup: bool = True):
        super().__init__()
        self.lib = library
        self.tag_limit = 30
        self.is_popup = is_popup
        self.driver = driver

        self.setMinimumSize(200, 300)
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(6, 0, 6, 0)

        self.search_field = QLineEdit()
        self.search_field.setObjectName("searchField")
        self.search_field.setMinimumSize(QSize(0, 32))
        self.search_field.setPlaceholderText("Search Tags")
        self.search_field.textEdited.connect(lambda: self.update_tags(self.search_field.text()))
        self.search_field.returnPressed.connect(
            lambda checked=False: self.on_return(self.search_field.text())
        )

        self.scroll_contents = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_contents)
        self.scroll_layout.setContentsMargins(6, 0, 6, 0)
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area = QScrollArea()
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShadow(QFrame.Shadow.Plain)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidget(self.scroll_contents)

        self.root_layout.addWidget(self.search_field)
        self.root_layout.addWidget(self.scroll_area)

        if self.driver:
            self.add_tag_btn = QPushButton()
            self.add_tag_btn.setText("Add Tag")
            self.add_tag_btn.clicked.connect(self.driver.add_tag_action_callback)
            self.root_layout.addWidget(self.add_tag_btn)

        if self.lib.storage_path:
            self.update_tags()

    def on_return(self, text: str):
        if text:
            # self.search_field.setText("")
            self.update_tags(text)
        else:
            self.search_field.setFocus()
            if self.is_popup:
                self.parentWidget().hide()

    def update_tags(self, query: str | None = None):
        # TODO: Look at recycling rather than deleting and re-initializing
        logger.info("updating tags", query=query)
        while self.scroll_layout.itemAt(0):
            self.scroll_layout.takeAt(0).widget().deleteLater()

        tags = self.lib.search_tags(FilterState(tag=query, page_size=self.tag_limit))

        for tag in tags:
            tag_widget = TagWidget(tag, has_edit=True, has_remove=False)
            tag_widget.on_edit.connect(lambda checked=False, t=tag: self.edit_tag(t))
            tag_widget.on_click.connect(self.set_main_filter(tag))
            tag_widget.on_double_click.connect(self.set_main_filter(tag, search=True))

            button_plus = QPushButton()
            button_plus.setMinimumSize(23, 23)
            button_plus.setMaximumSize(23, 23)
            button_plus.setText("+")
            button_plus.setStyleSheet(
                f"QPushButton{{"
                f"background: {get_tag_color(ColorType.PRIMARY, tag.color)};"
                f"color: {get_tag_color(ColorType.TEXT, tag.color)};"
                f"font-weight: 600;"
                f"border-color:{get_tag_color(ColorType.BORDER, tag.color)};"
                f"border-radius: 6px;"
                f"border-style:solid;"
                f"border-width: {math.ceil(self.devicePixelRatio())}px;"
                f"padding-bottom: 5px;"
                f"font-size: 20px;"
                f"}}"
                f"QPushButton::hover"
                f"{{"
                f"border-color:{get_tag_color(ColorType.LIGHT_ACCENT, tag.color)};"
                f"color: {get_tag_color(ColorType.DARK_ACCENT, tag.color)};"
                f"background: {get_tag_color(ColorType.LIGHT_ACCENT, tag.color)};"
                f"}}"
            )

            button_plus.clicked.connect(self.add_entries_tag(tag))

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(3)
            row_layout.addWidget(tag_widget)
            row_layout.addWidget(button_plus)
            self.scroll_layout.addWidget(row_widget)

        self.search_field.setFocus()

    def add_entries_tag(self, tag: Tag):
        def inner():
            if not self.driver:
                logger.warning("add_entries_tag called without driver")
                return

            self.driver.add_selected_tag(tag)

        return inner

    def set_main_filter(self, tag: Tag, search: bool = False):
        def inner():
            if not self.driver:
                return

            self.driver.main_window.searchField.setText(f"tag_id:{tag.id}")

            if search:
                # happens on double click
                self.driver.filter_items(FilterState(tag_id=tag.id))

        return inner

    def edit_tag(self, tag: Tag):
        build_tag_panel = BuildTagPanel(self.lib, tag=tag)

        self.edit_modal = PanelModal(
            build_tag_panel,
            tag.name,
            "Edit Tag",
            done_callback=(self.update_tags(self.search_field.text())),
            has_save=True,
        )
        # TODO Check Warning: Expected type 'BuildTagPanel', got 'PanelWidget' instead
        self.edit_modal.saved.connect(lambda: self.edit_tag_callback(build_tag_panel))
        self.edit_modal.show()

    def edit_tag_callback(self, btp: BuildTagPanel):
        self.lib.update_tag(btp.build_tag(), btp.subtag_ids, btp.alias_names, btp.alias_ids)
        self.update_tags(self.search_field.text())
