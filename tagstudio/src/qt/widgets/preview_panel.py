# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

import logging
import os
import time
import typing
from types import FunctionType
from datetime import datetime as dt

import cv2
from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QResizeEvent, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QFrame,
    QSplitter,
    QSizePolicy,
    QMessageBox,
)
from humanfriendly import format_size

from src.core.library import Entry, ItemType, Library
from src.core.ts_core import VIDEO_TYPES, IMAGE_TYPES
from src.qt.helpers import FileOpenerLabel, FileOpenerHelper, open_file
from src.qt.modals import AddFieldModal
from src.qt.widgets import (
    ThumbRenderer,
    FieldContainer,
    TagBoxWidget,
    TextWidget,
    PanelModal,
    EditTextBox,
    EditTextLine,
    ItemThumb,
)

# Only import for type checking/autocompletion, will not be imported at runtime.
if typing.TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

ERROR = f"[ERROR]"
WARNING = f"[WARNING]"
INFO = f"[INFO]"

logging.basicConfig(format="%(message)s", level=logging.INFO)


class PreviewPanel(QWidget):
    """The Preview Panel Widget."""

    tags_updated = Signal()

    def __init__(self, library: Library, driver: "QtDriver"):
        super().__init__()
        self.lib = library
        self.driver: QtDriver = driver
        self.initialized = False
        self.isOpen: bool = False
        # self.filepath = None
        # self.item = None # DEPRECATED, USE self.selected
        self.common_fields = []
        self.mixed_fields = []
        self.selected: list[tuple[ItemType, int]] = []  # New way of tracking items
        self.tag_callback = None
        self.containers: list[QWidget] = []

        self.img_button_size: tuple[int, int] = (266, 266)
        self.image_ratio: float = 1.0

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)

        self.image_container = QWidget()
        image_layout = QHBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.setHandleWidth(12)

        self.preview_img = QPushButton()
        self.preview_img.setMinimumSize(*self.img_button_size)
        self.preview_img.setFlat(True)

        self.preview_img.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.opener = FileOpenerHelper("")
        self.open_file_action = QAction("Open file", self)
        self.open_explorer_action = QAction("Open file in explorer", self)

        self.preview_img.addAction(self.open_file_action)
        self.preview_img.addAction(self.open_explorer_action)
        self.tr = ThumbRenderer()
        self.tr.updated.connect(lambda ts, i, s: (self.preview_img.setIcon(i)))
        self.tr.updated_ratio.connect(
            lambda ratio: (
                self.set_image_ratio(ratio),
                self.update_image_size(
                    (
                        self.image_container.size().width(),
                        self.image_container.size().height(),
                    ),
                    ratio,
                ),
            )
        )

        splitter.splitterMoved.connect(
            lambda: self.update_image_size(
                (
                    self.image_container.size().width(),
                    self.image_container.size().height(),
                )
            )
        )
        splitter.addWidget(self.image_container)

        image_layout.addWidget(self.preview_img)
        image_layout.setAlignment(self.preview_img, Qt.AlignmentFlag.AlignCenter)

        self.file_label = FileOpenerLabel("Filename")
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.file_label.setStyleSheet("font-weight: bold; font-size: 12px")

        self.dimensions_label = QLabel("Dimensions")
        self.dimensions_label.setWordWrap(True)
        # self.dim_label.setTextInteractionFlags(
        # 	Qt.TextInteractionFlag.TextSelectableByMouse)
        self.dimensions_label.setStyleSheet(ItemThumb.small_text_style)

        # 	small_text_style = (
        # 	f'background-color:rgba(17, 15, 27, 192);'
        # 	f'font-family:Oxanium;'
        # 	f'font-weight:bold;'
        # 	f'font-size:12px;'
        # 	f'border-radius:3px;'
        # 	f'padding-top: 4px;'
        # 	f'padding-right: 1px;'
        # 	f'padding-bottom: 1px;'
        # 	f'padding-left: 1px;'
        # )

        self.scroll_layout = QVBoxLayout()
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setContentsMargins(6, 1, 6, 6)

        scroll_container: QWidget = QWidget()
        scroll_container.setObjectName("entryScrollContainer")
        scroll_container.setLayout(self.scroll_layout)
        # scroll_container.setStyleSheet('background:#080716; border-radius:12px;')
        scroll_container.setStyleSheet(
            "background:#00000000;"
            "border-style:none;"
            f"QScrollBar::{{background:red;}}"
        )

        info_section = QWidget()
        info_layout = QVBoxLayout(info_section)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(6)
        self.setStyleSheet("background:#00000000;" f"QScrollBar::{{background:red;}}")

        scroll_area = QScrollArea()
        scroll_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShadow(QFrame.Shadow.Plain)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet(
            "background:#55000000;"
            "border-radius:12px;"
            "border-style:solid;"
            "border-width:1px;"
            "border-color:#11FFFFFF;"
            # f'QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{border: none;background: none;}}'
            # f'QScrollBar::left-arrow:horizontal, QScrollBar::right-arrow:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{border: none;background: none;color: none;}}'
            f"QScrollBar::{{background:red;}}"
        )
        scroll_area.setWidget(scroll_container)

        info_layout.addWidget(self.file_label)
        info_layout.addWidget(self.dimensions_label)
        info_layout.addWidget(scroll_area)
        splitter.addWidget(info_section)

        root_layout.addWidget(splitter)
        splitter.setStretchFactor(1, 2)

        self.afb_container = QWidget()
        self.afb_layout = QVBoxLayout(self.afb_container)
        self.afb_layout.setContentsMargins(0, 12, 0, 0)

        self.add_field_button = QPushButton()
        self.add_field_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_field_button.setMinimumSize(96, 28)
        self.add_field_button.setMaximumSize(96, 28)
        self.add_field_button.setText("Add Field")
        self.add_field_button.setStyleSheet(
            f"QPushButton{{"
            # f'background: #1E1A33;'
            # f'color: #CDA7F7;'
            f"font-weight: bold;"
            # f"border-color: #2B2547;"
            f"border-radius: 6px;"
            f"border-style:solid;"
            # f'border-width:{math.ceil(1*self.devicePixelRatio())}px;'
            "background:#55000000;"
            "border-width:1px;"
            "border-color:#11FFFFFF;"
            # f'padding-top: 1.5px;'
            # f'padding-right: 4px;'
            # f'padding-bottom: 5px;'
            # f'padding-left: 4px;'
            f"font-size: 13px;"
            f"}}"
            f"QPushButton::hover"
            f"{{"
            f"background: #333333;"
            f"}}"
        )
        self.afb_layout.addWidget(self.add_field_button)
        self.afm = AddFieldModal(self.lib)
        self.place_add_field_button()
        self.update_image_size(
            (self.image_container.size().width(), self.image_container.size().height())
        )

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.update_image_size(
            (self.image_container.size().width(), self.image_container.size().height())
        )
        return super().resizeEvent(event)

    def get_preview_size(self) -> tuple[int, int]:
        return (
            self.image_container.size().width(),
            self.image_container.size().height(),
        )

    def set_image_ratio(self, ratio: float):
        # logging.info(f'Updating Ratio to: {ratio} #####################################################')
        self.image_ratio = ratio

    def update_image_size(self, size: tuple[int, int], ratio: float = None):
        if ratio:
            self.set_image_ratio(ratio)
        # self.img_button_size = size
        # logging.info(f'')
        # self.preview_img.setMinimumSize(64,64)

        adj_width = size[0]
        adj_height = size[1]
        # Landscape
        if self.image_ratio > 1:
            # logging.info('Landscape')
            adj_height = size[0] * (1 / self.image_ratio)
        # Portrait
        elif self.image_ratio <= 1:
            # logging.info('Portrait')
            adj_width = size[1] * self.image_ratio

        if adj_width > size[0]:
            adj_height = adj_height * (size[0] / adj_width)
            adj_width = size[0]
        elif adj_height > size[1]:
            adj_width = adj_width * (size[1] / adj_height)
            adj_height = size[1]

        # adj_width = min(adj_width, self.image_container.size().width())
        # adj_height = min(adj_width, self.image_container.size().height())

        # self.preview_img.setMinimumSize(s)
        # self.preview_img.setMaximumSize(s_max)
        adj_size = QSize(adj_width, adj_height)
        self.img_button_size = (adj_width, adj_height)
        self.preview_img.setMaximumSize(adj_size)
        self.preview_img.setIconSize(adj_size)
        # self.preview_img.setMinimumSize(adj_size)

        # if self.preview_img.iconSize().toTuple()[0] < self.preview_img.size().toTuple()[0] + 10:
        # 	if type(self.item) == Entry:
        # 		filepath = os.path.normpath(f'{self.lib.library_dir}/{self.item.path}/{self.item.filename}')
        # 		self.tr.render_big(time.time(), filepath, self.preview_img.size().toTuple(), self.devicePixelRatio())

        # logging.info(f' Img Aspect Ratio: {self.image_ratio}')
        # logging.info(f'  Max Button Size: {size}')
        # logging.info(f'Container Size: {(self.image_container.size().width(), self.image_container.size().height())}')
        # logging.info(f'Final Button Size: {(adj_width, adj_height)}')
        # logging.info(f'')
        # logging.info(f'  Icon Size: {self.preview_img.icon().actualSize().toTuple()}')
        # logging.info(f'Button Size: {self.preview_img.size().toTuple()}')

    def place_add_field_button(self):
        self.scroll_layout.addWidget(self.afb_container)
        self.scroll_layout.setAlignment(
            self.afb_container, Qt.AlignmentFlag.AlignHCenter
        )

        try:
            self.afm.done.disconnect()
            self.add_field_button.clicked.disconnect()
        except RuntimeError:
            pass

        # self.afm.done.connect(lambda f: (self.lib.add_field_to_entry(self.selected[0][1], f), self.update_widgets()))
        self.afm.done.connect(
            lambda f: (self.add_field_to_selected(f), self.update_widgets())
        )
        self.add_field_button.clicked.connect(self.afm.show)

    def add_field_to_selected(self, field_id: int):
        """Adds an entry field to one or more selected items."""
        added = set()
        for item_pair in self.selected:
            if item_pair[0] == ItemType.ENTRY and item_pair[1] not in added:
                self.lib.add_field_to_entry(item_pair[1], field_id)
                added.add(item_pair[1])

    # def update_widgets(self, item: Union[Entry, Collation, Tag]):
    def update_widgets(self):
        """
        Renders the panel's widgets with the newest data from the Library.
        """
        logging.info(f"[ENTRY PANEL] UPDATE WIDGETS ({self.driver.selected})")
        self.isOpen = True
        # self.tag_callback = tag_callback if tag_callback else None
        window_title = ""

        # 0 Selected Items
        if len(self.driver.selected) == 0:
            if len(self.selected) != 0 or not self.initialized:
                self.file_label.setText(f"No Items Selected")
                self.file_label.setFilePath("")
                self.dimensions_label.setText("")
                self.preview_img.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.NoContextMenu
                )
                ratio: float = self.devicePixelRatio()
                self.tr.render_big(time.time(), "", (512, 512), ratio, True)
                try:
                    self.preview_img.clicked.disconnect()
                except RuntimeError:
                    pass
                for i, c in enumerate(self.containers):
                    c.setHidden(True)

            self.selected = list(self.driver.selected)
            self.add_field_button.setHidden(True)

        # 1 Selected Item
        elif len(self.driver.selected) == 1:
            # 1 Selected Entry
            if self.driver.selected[0][0] == ItemType.ENTRY:
                item: Entry = self.lib.get_entry(self.driver.selected[0][1])
                # If a new selection is made, update the thumbnail and filepath.
                if len(self.selected) == 0 or self.selected != self.driver.selected:
                    filepath = os.path.normpath(
                        f"{self.lib.library_dir}/{item.path}/{item.filename}"
                    )
                    self.file_label.setFilePath(filepath)
                    window_title = filepath
                    ratio: float = self.devicePixelRatio()
                    self.tr.render_big(time.time(), filepath, (512, 512), ratio)
                    self.file_label.setText("\u200b".join(filepath))

                    self.preview_img.setContextMenuPolicy(
                        Qt.ContextMenuPolicy.ActionsContextMenu
                    )
                    self.opener = FileOpenerHelper(filepath)
                    self.open_file_action.triggered.connect(self.opener.open_file)
                    self.open_explorer_action.triggered.connect(
                        self.opener.open_explorer
                    )

                    # TODO: Do this somewhere else, this is just here temporarily.
                    extension = os.path.splitext(filepath)[1][1:].lower()
                    try:
                        image = None
                        if extension in IMAGE_TYPES:
                            image = Image.open(filepath)
                            if image.mode == "RGBA":
                                new_bg = Image.new("RGB", image.size, color="#222222")
                                new_bg.paste(image, mask=image.getchannel(3))
                                image = new_bg
                            if image.mode != "RGB":
                                image = image.convert(mode="RGB")
                        elif extension in VIDEO_TYPES:
                            video = cv2.VideoCapture(filepath)
                            video.set(
                                cv2.CAP_PROP_POS_FRAMES,
                                (video.get(cv2.CAP_PROP_FRAME_COUNT) // 2),
                            )
                            success, frame = video.read()
                            if not success:
                                # Depending on the video format, compression, and frame
                                # count, seeking halfway does not work and the thumb
                                # must be pulled from the earliest available frame.
                                video.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                success, frame = video.read()
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            image = Image.fromarray(frame)

                        # Stats for specific file types are displayed here.
                        if extension in (IMAGE_TYPES + VIDEO_TYPES):
                            self.dimensions_label.setText(
                                f"{extension.upper()}  •  {format_size(os.stat(filepath).st_size)}\n{image.width} x {image.height} px"
                            )
                        else:
                            self.dimensions_label.setText(f"{extension.upper()}")

                        if not image:
                            self.dimensions_label.setText(
                                f"{extension.upper()}  •  {format_size(os.stat(filepath).st_size)}"
                            )
                            raise UnidentifiedImageError

                    except (UnidentifiedImageError, FileNotFoundError, cv2.error):
                        pass

                    try:
                        self.preview_img.clicked.disconnect()
                    except RuntimeError:
                        pass
                    self.preview_img.clicked.connect(
                        lambda checked=False, filepath=filepath: open_file(filepath)
                    )

                self.selected = list(self.driver.selected)
                for i, f in enumerate(item.fields):
                    self.write_container(i, f)

                # Hide leftover containers
                if len(self.containers) > len(item.fields):
                    for i, c in enumerate(self.containers):
                        if i > (len(item.fields) - 1):
                            c.setHidden(True)

                self.add_field_button.setHidden(False)

            # 1 Selected Collation
            elif self.driver.selected[0][0] == ItemType.COLLATION:
                pass

            # 1 Selected Tag
            elif self.driver.selected[0][0] == ItemType.TAG_GROUP:
                pass

        # Multiple Selected Items
        elif len(self.driver.selected) > 1:
            if self.selected != self.driver.selected:
                self.file_label.setText(f"{len(self.driver.selected)} Items Selected")
                self.file_label.setFilePath("")
                self.dimensions_label.setText("")
                self.preview_img.setContextMenuPolicy(
                    Qt.ContextMenuPolicy.NoContextMenu
                )
                ratio: float = self.devicePixelRatio()
                self.tr.render_big(time.time(), "", (512, 512), ratio, True)
                try:
                    self.preview_img.clicked.disconnect()
                except RuntimeError:
                    pass

            self.common_fields = []
            self.mixed_fields = []
            for i, item_pair in enumerate(self.driver.selected):
                if item_pair[0] == ItemType.ENTRY:
                    item = self.lib.get_entry(item_pair[1])
                    if i == 0:
                        for f in item.fields:
                            self.common_fields.append(f)
                    else:
                        common_to_remove = []
                        for f in self.common_fields:
                            # Common field found (Same ID, identical content)
                            if f not in item.fields:
                                common_to_remove.append(f)

                                # Mixed field found (Same ID, different content)
                                if self.lib.get_field_index_in_entry(
                                    item, self.lib.get_field_attr(f, "id")
                                ):
                                    # if self.lib.get_field_attr(f, 'type') == ('tag_box'):
                                    # 	pass
                                    # logging.info(f)
                                    # logging.info(type(f))
                                    f_stripped = {
                                        self.lib.get_field_attr(f, "id"): None
                                    }
                                    if f_stripped not in self.mixed_fields and (
                                        f not in self.common_fields
                                        or f in common_to_remove
                                    ):
                                        #  and (f not in self.common_fields or f in common_to_remove)
                                        self.mixed_fields.append(f_stripped)
                        self.common_fields = [
                            f for f in self.common_fields if f not in common_to_remove
                        ]
            order: list[int] = (
                [0]
                + [1, 2]
                + [9, 17, 18, 19, 20]
                + [8, 7, 6]
                + [4]
                + [3, 21]
                + [10, 14, 11, 12, 13, 22]
                + [5]
            )
            self.mixed_fields = sorted(
                self.mixed_fields,
                key=lambda x: order.index(self.lib.get_field_attr(x, "id")),
            )

            self.selected = list(self.driver.selected)
            for i, f in enumerate(self.common_fields):
                logging.info(f"ci:{i}, f:{f}")
                self.write_container(i, f)
            for i, f in enumerate(self.mixed_fields, start=len(self.common_fields)):
                logging.info(f"mi:{i}, f:{f}")
                self.write_container(i, f, mixed=True)

            # Hide leftover containers
            if len(self.containers) > len(self.common_fields) + len(self.mixed_fields):
                for i, c in enumerate(self.containers):
                    if i > (len(self.common_fields) + len(self.mixed_fields) - 1):
                        c.setHidden(True)

            self.add_field_button.setHidden(False)

        self.initialized = True

        # # Uninitialized or New Item:
        # if not self.item or self.item.id != item.id:
        # 	# logging.info(f'Uninitialized or New Item ({item.id})')
        # 	if type(item) == Entry:
        # 		# New Entry: Render preview and update filename label
        # 		filepath = os.path.normpath(f'{self.lib.library_dir}/{item.path}/{item.filename}')
        # 		window_title = filepath
        # 		ratio: float = self.devicePixelRatio()
        # 		self.tr.render_big(time.time(), filepath, (512, 512), ratio)
        # 		self.file_label.setText("\u200b".join(filepath))

        # 		# TODO: Deal with this later.
        # 		# https://stackoverflow.com/questions/64252654/pyqt5-drag-and-drop-into-system-file-explorer-with-delayed-encoding
        # 		# https://doc.qt.io/qtforpython-5/PySide2/QtCore/QMimeData.html#more
        # 		# drag = QDrag(self.preview_img)
        # 		# mime = QMimeData()
        # 		# mime.setUrls([filepath])
        # 		# drag.setMimeData(mime)
        # 		# drag.exec_(Qt.DropAction.CopyAction)

        # 		try:
        # 			self.preview_img.clicked.disconnect()
        # 		except RuntimeError:
        # 			pass
        # 		self.preview_img.clicked.connect(
        # 			lambda checked=False, filepath=filepath: open_file(filepath))

        # 		for i, f in enumerate(item.fields):
        # 			self.write_container(item, i, f)

        # 		self.item = item

        # 		# try:
        # 		# 	self.tags_updated.disconnect()
        # 		# except RuntimeError:
        # 		# 	pass
        # 		# if self.tag_callback:
        # 		# 	# logging.info(f'[UPDATE CONTAINER] Updating Callback for {item.id}: {self.tag_callback}')
        # 		# 	self.tags_updated.connect(self.tag_callback)

        # # Initialized, Updating:
        # elif self.item and self.item.id == item.id:
        # 	# logging.info(f'Initialized Item, Updating! ({item.id})')
        # 	for i, f in enumerate(item.fields):
        # 		self.write_container(item, i, f)

        # # Hide leftover containers
        # if len(self.containers) > len(self.item.fields):
        # 	for i, c in enumerate(self.containers):
        # 		if i > (len(self.item.fields) - 1):
        # 			c.setHidden(True)

        self.setWindowTitle(window_title)
        self.show()

    def set_tags_updated_slot(self, slot: object):
        """
        Replacement for tag_callback.
        """
        try:
            self.tags_updated.disconnect()
        except RuntimeError:
            pass
        logging.info(f"[UPDATE CONTAINER] Setting tags updated slot")
        self.tags_updated.connect(slot)

    # def write_container(self, item:Union[Entry, Collation, Tag], index, field):
    def write_container(self, index, field, mixed=False):
        """Updates/Creates data for a FieldContainer."""
        # logging.info(f'[ENTRY PANEL] WRITE CONTAINER')
        # Remove 'Add Field' button from scroll_layout, to be re-added later.
        self.scroll_layout.takeAt(self.scroll_layout.count() - 1).widget()
        container: FieldContainer = None
        if len(self.containers) < (index + 1):
            container = FieldContainer()
            self.containers.append(container)
            self.scroll_layout.addWidget(container)
        else:
            container = self.containers[index]
            # container.inner_layout.removeItem(container.inner_layout.itemAt(1))
            # container.setHidden(False)
        if self.lib.get_field_attr(field, "type") == "tag_box":
            # logging.info(f'WRITING TAGBOX FOR ITEM {item.id}')
            container.set_title(self.lib.get_field_attr(field, "name"))
            # container.set_editable(False)
            container.set_inline(False)
            title = f"{self.lib.get_field_attr(field, 'name')} (Tag Box)"
            if not mixed:
                item = self.lib.get_entry(
                    self.selected[0][1]
                )  # TODO TODO TODO: TEMPORARY
                if type(container.get_inner_widget()) == TagBoxWidget:
                    inner_container: TagBoxWidget = container.get_inner_widget()
                    inner_container.set_item(item)
                    inner_container.set_tags(self.lib.get_field_attr(field, "content"))
                    try:
                        inner_container.updated.disconnect()
                    except RuntimeError:
                        pass
                    # inner_container.updated.connect(lambda f=self.filepath, i=item: self.write_container(item, index, field))
                else:
                    inner_container = TagBoxWidget(
                        item,
                        title,
                        index,
                        self.lib,
                        self.lib.get_field_attr(field, "content"),
                        self.driver,
                    )

                    container.set_inner_widget(inner_container)
                inner_container.field = field
                inner_container.updated.connect(
                    lambda: (
                        self.write_container(index, field),
                        self.tags_updated.emit(),
                    )
                )
                # if type(item) == Entry:
                # NOTE: Tag Boxes have no Edit Button (But will when you can convert field types)
                # f'Are you sure you want to remove this \"{self.lib.get_field_attr(field, "name")}\" field?'
                # container.set_remove_callback(lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets(item)))
                prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
                callback = lambda: (self.remove_field(field), self.update_widgets())
                container.set_remove_callback(
                    lambda: self.remove_message_box(prompt=prompt, callback=callback)
                )
                container.set_copy_callback(None)
                container.set_edit_callback(None)
            else:
                text = "<i>Mixed Data</i>"
                title = f"{self.lib.get_field_attr(field, 'name')} (Wacky Tag Box)"
                inner_container = TextWidget(title, text)
                container.set_inner_widget(inner_container)
                container.set_copy_callback(None)
                container.set_edit_callback(None)
                container.set_remove_callback(None)

            self.tags_updated.emit()
            # self.dynamic_widgets.append(inner_container)
        elif self.lib.get_field_attr(field, "type") in "text_line":
            # logging.info(f'WRITING TEXTLINE FOR ITEM {item.id}')
            container.set_title(self.lib.get_field_attr(field, "name"))
            # container.set_editable(True)
            container.set_inline(False)
            # Normalize line endings in any text content.
            text: str = ""
            if not mixed:
                text = self.lib.get_field_attr(field, "content").replace("\r", "\n")
            else:
                text = "<i>Mixed Data</i>"
            title = f"{self.lib.get_field_attr(field, 'name')} (Text Line)"
            inner_container = TextWidget(title, text)
            container.set_inner_widget(inner_container)
            # if type(item) == Entry:
            if not mixed:
                modal = PanelModal(
                    EditTextLine(self.lib.get_field_attr(field, "content")),
                    title=title,
                    window_title=f'Edit {self.lib.get_field_attr(field, "name")}',
                    save_callback=(
                        lambda content: (
                            self.update_field(field, content),
                            self.update_widgets(),
                        )
                    ),
                )
                container.set_edit_callback(modal.show)
                prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
                callback = lambda: (self.remove_field(field), self.update_widgets())
                container.set_remove_callback(
                    lambda: self.remove_message_box(prompt=prompt, callback=callback)
                )
                container.set_copy_callback(None)
            else:
                container.set_edit_callback(None)
                container.set_copy_callback(None)
                container.set_remove_callback(None)
            # container.set_remove_callback(lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets(item)))

        elif self.lib.get_field_attr(field, "type") in "text_box":
            # logging.info(f'WRITING TEXTBOX FOR ITEM {item.id}')
            container.set_title(self.lib.get_field_attr(field, "name"))
            # container.set_editable(True)
            container.set_inline(False)
            # Normalize line endings in any text content.
            text: str = ""
            if not mixed:
                text = self.lib.get_field_attr(field, "content").replace("\r", "\n")
            else:
                text = "<i>Mixed Data</i>"
            title = f"{self.lib.get_field_attr(field, 'name')} (Text Box)"
            inner_container = TextWidget(title, text)
            container.set_inner_widget(inner_container)
            # if type(item) == Entry:
            if not mixed:
                container.set_copy_callback(None)
                modal = PanelModal(
                    EditTextBox(self.lib.get_field_attr(field, "content")),
                    title=title,
                    window_title=f'Edit {self.lib.get_field_attr(field, "name")}',
                    save_callback=(
                        lambda content: (
                            self.update_field(field, content),
                            self.update_widgets(),
                        )
                    ),
                )
                container.set_edit_callback(modal.show)
                prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
                callback = lambda: (self.remove_field(field), self.update_widgets())
                container.set_remove_callback(
                    lambda: self.remove_message_box(prompt=prompt, callback=callback)
                )
            else:
                container.set_edit_callback(None)
                container.set_copy_callback(None)
                container.set_remove_callback(None)
        elif self.lib.get_field_attr(field, "type") == "collation":
            # logging.info(f'WRITING COLLATION FOR ITEM {item.id}')
            container.set_title(self.lib.get_field_attr(field, "name"))
            # container.set_editable(True)
            container.set_inline(False)
            collation = self.lib.get_collation(
                self.lib.get_field_attr(field, "content")
            )
            title = f"{self.lib.get_field_attr(field, 'name')} (Collation)"
            text: str = f"{collation.title} ({len(collation.e_ids_and_pages)} Items)"
            if len(self.selected) == 1:
                text += f" - Page {collation.e_ids_and_pages[[x[0] for x in collation.e_ids_and_pages].index(self.selected[0][1])][1]}"
            inner_container = TextWidget(title, text)
            container.set_inner_widget(inner_container)
            # if type(item) == Entry:
            container.set_copy_callback(None)
            # container.set_edit_callback(None)
            # container.set_remove_callback(lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets(item)))
            prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
            callback = lambda: (self.remove_field(field), self.update_widgets())
            container.set_remove_callback(
                lambda: self.remove_message_box(prompt=prompt, callback=callback)
            )
        elif self.lib.get_field_attr(field, "type") == "datetime":
            # logging.info(f'WRITING DATETIME FOR ITEM {item.id}')
            if not mixed:
                try:
                    container.set_title(self.lib.get_field_attr(field, "name"))
                    # container.set_editable(False)
                    container.set_inline(False)
                    # TODO: Localize this and/or add preferences.
                    date = dt.strptime(
                        self.lib.get_field_attr(field, "content"), "%Y-%m-%d %H:%M:%S"
                    )
                    title = f"{self.lib.get_field_attr(field, 'name')} (Date)"
                    inner_container = TextWidget(title, date.strftime("%D - %r"))
                    container.set_inner_widget(inner_container)
                except:
                    container.set_title(self.lib.get_field_attr(field, "name"))
                    # container.set_editable(False)
                    container.set_inline(False)
                    title = f"{self.lib.get_field_attr(field, 'name')} (Date) (Unknown Format)"
                    inner_container = TextWidget(
                        title, str(self.lib.get_field_attr(field, "content"))
                    )
                # if type(item) == Entry:
                container.set_copy_callback(None)
                container.set_edit_callback(None)
                # container.set_remove_callback(lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets(item)))
                prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
                callback = lambda: (self.remove_field(field), self.update_widgets())
                container.set_remove_callback(
                    lambda: self.remove_message_box(prompt=prompt, callback=callback)
                )
            else:
                text = "<i>Mixed Data</i>"
                title = f"{self.lib.get_field_attr(field, 'name')} (Wacky Date)"
                inner_container = TextWidget(title, text)
                container.set_inner_widget(inner_container)
                container.set_copy_callback(None)
                container.set_edit_callback(None)
                container.set_remove_callback(None)
        else:
            # logging.info(f'[ENTRY PANEL] Unknown Type: {self.lib.get_field_attr(field, "type")}')
            container.set_title(self.lib.get_field_attr(field, "name"))
            # container.set_editable(False)
            container.set_inline(False)
            title = f"{self.lib.get_field_attr(field, 'name')} (Unknown Field Type)"
            inner_container = TextWidget(
                title, str(self.lib.get_field_attr(field, "content"))
            )
            container.set_inner_widget(inner_container)
            # if type(item) == Entry:
            container.set_copy_callback(None)
            container.set_edit_callback(None)
            # container.set_remove_callback(lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets(item)))
            prompt = f'Are you sure you want to remove this "{self.lib.get_field_attr(field, "name")}" field?'
            callback = lambda: (self.remove_field(field), self.update_widgets())
            # callback = lambda: (self.lib.get_entry(item.id).fields.pop(index), self.update_widgets())
            container.set_remove_callback(
                lambda: self.remove_message_box(prompt=prompt, callback=callback)
            )
        container.setHidden(False)
        self.place_add_field_button()

    def remove_field(self, field: object):
        """Removes a field from all selected Entries, given a field object."""
        for item_pair in self.selected:
            if item_pair[0] == ItemType.ENTRY:
                entry = self.lib.get_entry(item_pair[1])
                try:
                    index = entry.fields.index(field)
                    updated_badges = False
                    if 8 in entry.fields[index].keys() and (
                        1 in entry.fields[index][8] or 0 in entry.fields[index][8]
                    ):
                        updated_badges = True
                    # TODO: Create a proper Library/Entry method to manage fields.
                    entry.fields.pop(index)
                    if updated_badges:
                        self.driver.update_badges()
                except ValueError:
                    logging.info(
                        f"[PREVIEW PANEL][ERROR?] Tried to remove field from Entry ({entry.id}) that never had it"
                    )
                    pass

    def update_field(self, field: object, content):
        """Removes a field from all selected Entries, given a field object."""
        field = dict(field)
        for item_pair in self.selected:
            if item_pair[0] == ItemType.ENTRY:
                entry = self.lib.get_entry(item_pair[1])
                try:
                    logging.info(field)
                    index = entry.fields.index(field)
                    self.lib.update_entry_field(entry.id, index, content, "replace")
                except ValueError:
                    logging.info(
                        f"[PREVIEW PANEL][ERROR] Tried to update field from Entry ({entry.id}) that never had it"
                    )
                    pass

    def remove_message_box(self, prompt: str, callback: FunctionType) -> int:
        remove_mb = QMessageBox()
        remove_mb.setText(prompt)
        remove_mb.setWindowTitle("Remove Field")
        remove_mb.setIcon(QMessageBox.Icon.Warning)
        cancel_button = remove_mb.addButton(
            "&Cancel", QMessageBox.ButtonRole.DestructiveRole
        )
        remove_button = remove_mb.addButton(
            "&Remove", QMessageBox.ButtonRole.RejectRole
        )
        # remove_mb.setStandardButtons(QMessageBox.StandardButton.Cancel)
        remove_mb.setDefaultButton(cancel_button)
        result = remove_mb.exec_()
        # logging.info(result)
        if result == 1:
            callback()
