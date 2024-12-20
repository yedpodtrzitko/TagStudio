# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

import io
import os
import sys
import time
import typing
from datetime import datetime as dt
from pathlib import Path

import cv2
import rawpy
import structlog
from humanfriendly import format_size
from PIL import Image, ImageFont, UnidentifiedImageError
from PIL.Image import DecompressionBombError
from PySide6.QtCore import QBuffer, QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QAction, QGuiApplication, QMovie, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from src.core.enums import Theme
from src.core.library.alchemy.enums import FilterState
from src.core.library.alchemy.fields import (
    BaseField,
    DatetimeField,
    FieldTypeEnum,
    TagBoxField,
    TextField,
    _FieldID,
)
from src.core.library.alchemy.library import Library
from src.core.media_types import MediaCategories
from src.qt.enums import ThumbSize
from src.qt.helpers.file_opener import FileOpenerHelper, FileOpenerLabel, open_file
from src.qt.helpers.file_tester import is_readable_video
from src.qt.helpers.qbutton_wrapper import QPushButtonWrapper
from src.qt.helpers.rounded_pixmap_style import RoundedPixmapStyle
from src.qt.modals.add_field import AddFieldModal
from src.qt.platform_strings import PlatformStrings
from src.qt.widgets.fields import FieldContainer
from src.qt.widgets.media_player import MediaPlayer
from src.qt.widgets.panel import PanelModal
from src.qt.widgets.remove_button import remove_message_box
from src.qt.widgets.tag_box import TagBoxWidget
from src.qt.widgets.text import TextWidget
from src.qt.widgets.text_box_edit import EditTextBox
from src.qt.widgets.text_line_edit import EditTextLine
from src.qt.widgets.thumb_renderer import ThumbRenderer
from src.qt.widgets.video_player import VideoPlayer

if typing.TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)


class PreviewPanel(QWidget):
    """The Preview Panel Widget."""

    tags_updated = Signal()

    def __init__(self, library: Library, driver: "QtDriver"):
        super().__init__()
        self.is_connected = False
        self.lib = library
        self.driver: QtDriver = driver
        self.initialized = False
        self.is_open: bool = False
        self.common_fields: list = []
        self.mixed_fields: list = []
        self.selected: list[int] = []  # New way of tracking items
        self.tag_callback = None
        self.containers: list[FieldContainer] = []

        self.img_button_size: tuple[int, int] = (240, 240)
        self.image_ratio: float = 1.0

        self.label_bg_color = (
            Theme.COLOR_BG_DARK.value
            if QGuiApplication.styleHints().colorScheme() is Qt.ColorScheme.Dark
            else Theme.COLOR_DARK_LABEL.value
        )
        self.panel_bg_color = (
            Theme.COLOR_BG_DARK.value
            if QGuiApplication.styleHints().colorScheme() is Qt.ColorScheme.Dark
            else Theme.COLOR_BG_LIGHT.value
        )

        self.image_container = QWidget()

        file_label_style = "font-size: 12px"
        properties_style = (
            f"background-color:{self.label_bg_color};"
            "color:#FFFFFF;"
            "font-family:Oxanium;"
            "font-weight:bold;"
            "font-size:12px;"
            "border-radius:3px;"
            "padding-top: 4px;"
            "padding-right: 1px;"
            "padding-bottom: 1px;"
            "padding-left: 1px;"
        )
        date_style = "font-size:12px;"

        self.open_file_action = QAction("Open file", self)
        self.open_explorer_action = QAction(PlatformStrings.open_file_str, self)

        self.preview_img = QPushButtonWrapper()
        self.preview_img.setMinimumSize(*self.img_button_size)
        self.preview_img.setFlat(True)
        self.preview_img.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.preview_img.addAction(self.open_file_action)
        self.preview_img.addAction(self.open_explorer_action)

        self.preview_gif = QLabel()
        self.preview_gif.setMinimumSize(*self.img_button_size)
        self.preview_gif.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
        self.preview_gif.setCursor(Qt.CursorShape.ArrowCursor)
        self.preview_gif.addAction(self.open_file_action)
        self.preview_gif.addAction(self.open_explorer_action)
        self.preview_gif.hide()
        self.gif_buffer: QBuffer = QBuffer()

        self.preview_vid = VideoPlayer(driver)
        self.preview_vid.hide()
        self.thumb_renderer = ThumbRenderer(library=library)
        self.thumb_renderer.updated.connect(lambda ts, i, s, entry: (self.preview_img.setIcon(i)))
        self.thumb_renderer.updated_ratio.connect(
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

        self.media_player = MediaPlayer(driver)
        self.media_player.hide()

        image_layout = QHBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)
        image_layout.addWidget(self.preview_img)
        image_layout.setAlignment(self.preview_img, Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.preview_gif)
        image_layout.setAlignment(self.preview_gif, Qt.AlignmentFlag.AlignCenter)
        image_layout.addWidget(self.preview_vid)
        image_layout.setAlignment(self.preview_vid, Qt.AlignmentFlag.AlignCenter)

        self.image_container.setMinimumSize(*self.img_button_size)
        self.file_label = FileOpenerLabel()
        self.file_label.setObjectName("filenameLabel")
        self.file_label.setTextFormat(Qt.TextFormat.RichText)
        self.file_label.setWordWrap(True)
        self.file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.file_label.setStyleSheet(file_label_style)

        self.date_created_label = QLabel()
        self.date_created_label.setObjectName("dateCreatedLabel")
        self.date_created_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.date_created_label.setTextFormat(Qt.TextFormat.RichText)
        self.date_created_label.setStyleSheet(date_style)

        self.date_modified_label = QLabel()
        self.date_modified_label.setObjectName("dateModifiedLabel")
        self.date_modified_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.date_modified_label.setTextFormat(Qt.TextFormat.RichText)
        self.date_modified_label.setStyleSheet(date_style)

        self.dimensions_label = QLabel()
        self.dimensions_label.setObjectName("dimensionsLabel")
        self.dimensions_label.setWordWrap(True)
        self.dimensions_label.setStyleSheet(properties_style)

        self.scroll_layout = QVBoxLayout()
        self.scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_layout.setContentsMargins(6, 1, 6, 6)

        scroll_container: QWidget = QWidget()
        scroll_container.setObjectName("entryScrollContainer")
        scroll_container.setLayout(self.scroll_layout)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("entryScrollArea")
        scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShadow(QFrame.Shadow.Plain)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # NOTE: I would rather have this style applied to the scroll_area
        # background and NOT the scroll container background, so that the
        # rounded corners are maintained when scrolling. I was unable to
        # find the right trick to only select that particular element.

        scroll_area.setStyleSheet(
            "QWidget#entryScrollContainer{"
            f"background:{self.panel_bg_color};"
            "border-radius:6px;"
            "}"
        )
        scroll_area.setWidget(scroll_container)

        date_container = QWidget()
        date_layout = QVBoxLayout(date_container)
        date_layout.setContentsMargins(0, 2, 0, 0)
        date_layout.setSpacing(0)
        date_layout.addWidget(self.date_created_label)
        date_layout.addWidget(self.date_modified_label)

        self.info_section = QWidget()
        self.info_section.setSizePolicy(
            QSizePolicy.Preferred,  # type: ignore
            QSizePolicy.Minimum,  # type: ignore
        )
        info_layout = QVBoxLayout(self.info_section)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(6)
        info_layout.addWidget(self.file_label)
        info_layout.addWidget(date_container)
        info_layout.addWidget(self.dimensions_label)
        info_layout.addWidget(scroll_area)

        self.splitter = splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.setHandleWidth(12)
        splitter.splitterMoved.connect(
            lambda: self.update_image_size(
                (
                    self.image_container.size().width(),
                    self.image_container.size().height(),
                )
            )
        )

        splitter.addWidget(self.image_container)
        splitter.addWidget(self.media_player)
        splitter.addWidget(self.info_section)
        splitter.setStretchFactor(1, 2)

        self.afb_container = QWidget()
        self.afb_layout = QVBoxLayout(self.afb_container)
        self.afb_layout.setContentsMargins(0, 12, 0, 0)

        self.add_field_button = QPushButtonWrapper()
        self.add_field_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_field_button.setMinimumSize(96, 28)
        self.add_field_button.setMaximumSize(96, 28)
        self.add_field_button.setText("Add Field")
        self.afb_layout.addWidget(self.add_field_button)
        self.add_field_modal = AddFieldModal(self.lib)
        self.place_add_field_button()
        self.update_image_size(
            (self.image_container.size().width(), self.image_container.size().height())
        )

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(splitter)

    def update_selected_entry(self, driver: "QtDriver"):
        for grid_idx in driver.selected:
            entry = driver.frame_content[grid_idx]
            results = self.lib.search_library(FilterState(id=entry.id))
            logger.info(
                "found item",
                entries=len(results.items),
                grid_idx=grid_idx,
                lookup_id=entry.id,
            )
            self.driver.frame_content[grid_idx] = results[0]

    def remove_field_prompt(self, name: str) -> str:
        return f'Are you sure you want to remove field "{name}"?'

    def toggle_thumbnail(self):
        # TODO - skip rendering when hidden
        self.image_container.setVisible(not self.image_container.isVisible())

    def toggle_props(self):
        self.info_section.setVisible(not self.info_section.isVisible())

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
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
        self.image_ratio = ratio

    def update_image_size(self, size: tuple[int, int], ratio: float = None):
        if ratio:
            self.set_image_ratio(ratio)

        adj_width: float = size[0]
        adj_height: float = size[1]
        # Landscape
        if self.image_ratio > 1:
            adj_height = size[0] * (1 / self.image_ratio)
        # Portrait
        elif self.image_ratio <= 1:
            adj_width = size[1] * self.image_ratio

        if adj_width > size[0]:
            adj_height = adj_height * (size[0] / adj_width)
            adj_width = size[0]
        elif adj_height > size[1]:
            adj_width = adj_width * (size[1] / adj_height)
            adj_height = size[1]

        adj_size = QSize(int(adj_width), int(adj_height))
        self.img_button_size = (int(adj_width), int(adj_height))
        self.preview_img.setMaximumSize(adj_size)
        self.preview_img.setIconSize(adj_size)
        self.preview_vid.resize_video(adj_size)
        self.preview_vid.setMaximumSize(adj_size)
        self.preview_vid.setMinimumSize(adj_size)
        self.preview_gif.setMaximumSize(adj_size)
        self.preview_gif.setMinimumSize(adj_size)
        proxy_style = RoundedPixmapStyle(radius=8)
        self.preview_gif.setStyle(proxy_style)
        self.preview_vid.setStyle(proxy_style)
        m = self.preview_gif.movie()
        if m:
            m.setScaledSize(adj_size)

    def place_add_field_button(self):
        self.scroll_layout.addWidget(self.afb_container)
        self.scroll_layout.setAlignment(self.afb_container, Qt.AlignmentFlag.AlignHCenter)

        if self.add_field_modal.is_connected:
            self.add_field_modal.done.disconnect()
        if self.add_field_button.is_connected:
            self.add_field_button.clicked.disconnect()

        self.add_field_modal.done.connect(
            lambda f: (self.add_field_to_selected(f), self.update_widgets())
        )
        self.add_field_modal.is_connected = True
        self.add_field_button.clicked.connect(self.add_field_modal.show)

    def add_field_to_selected(self, field_list: list):
        """Add list of entry fields to one or more selected items."""
        logger.info("add_field_to_selected", selected=self.selected, fields=field_list)
        for grid_idx in self.selected:
            entry = self.driver.frame_content[grid_idx]
            for field_item in field_list:
                self.lib.add_entry_field_type(
                    entry.id,
                    field_id=field_item.data(Qt.ItemDataRole.UserRole),
                )

    def update_date_label(self, filepath: Path | None = None) -> None:
        """Update the "Date Created" and "Date Modified" file property labels."""
        if filepath and filepath.is_file():
            file_stats = filepath.stat()
            if st_birthtime := getattr(file_stats, "st_birthtime", None):
                created = dt.fromtimestamp(st_birthtime)
            else:
                created = dt.fromtimestamp(file_stats.st_ctime)
            modified: dt = dt.fromtimestamp(file_stats.st_mtime)
            self.date_created_label.setText(
                f"<b>Date Created:</b> {dt.strftime(created, "%a, %x, %X")}"
            )
            self.date_modified_label.setText(
                f"<b>Date Modified:</b> {dt.strftime(modified, "%a, %x, %X")}"
            )
            self.date_created_label.setHidden(False)
            self.date_modified_label.setHidden(False)
        elif filepath:
            self.date_created_label.setText("<b>Date Created:</b> <i>N/A</i>")
            self.date_modified_label.setText("<b>Date Modified:</b> <i>N/A</i>")
            self.date_created_label.setHidden(False)
            self.date_modified_label.setHidden(False)
        else:
            self.date_created_label.setHidden(True)
            self.date_modified_label.setHidden(True)

    def update_widgets(self) -> bool:
        """Render the panel widgets with the newest data from the Library."""
        logger.info("update_widgets", selected=self.driver.selected)
        self.is_open = True
        # self.tag_callback = tag_callback if tag_callback else None
        window_title = ""

        if not self.driver.selected:
            if self.selected or not self.initialized:
                self.file_label.setText("<i>No Items Selected</i>")
                self.file_label.set_file_path("")
                self.file_label.setCursor(Qt.CursorShape.ArrowCursor)

                self.dimensions_label.setText("")
                self.update_date_label()
                self.preview_img.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
                self.preview_img.setCursor(Qt.CursorShape.ArrowCursor)

                ratio = self.devicePixelRatio()
                self.thumb_renderer.render(
                    time.time(),
                    None,
                    ThumbSize.XX_LARGE,
                    ratio,
                    is_loading=True,
                    update_on_ratio_change=True,
                )
                if self.preview_img.is_connected:
                    self.preview_img.clicked.disconnect()
                for c in self.containers:
                    c.setHidden(True)
            self.preview_img.show()
            self.preview_vid.stop()
            self.preview_vid.hide()
            self.media_player.hide()
            self.media_player.stop()
            self.preview_gif.hide()
            self.selected = list(self.driver.selected)
            self.add_field_button.setHidden(True)

            # common code
            self.initialized = True
            self.setWindowTitle(window_title)
            self.show()
            return True

        # reload entry and fill it into the grid again
        # TODO - do this more granular
        # TODO - Entry reload is maybe not necessary
        for grid_idx in self.driver.selected:
            entry = self.driver.frame_content[grid_idx]
            results = self.lib.search_library(FilterState(id=entry.id))
            logger.info(
                "found item",
                entries=len(results.items),
                grid_idx=grid_idx,
                lookup_id=entry.id,
            )
            self.driver.frame_content[grid_idx] = results[0]

        if len(self.driver.selected) == 1:
            # 1 Selected Entry
            selected_idx = self.driver.selected[0]
            item = self.driver.frame_content[selected_idx]

            self.preview_img.show()
            self.preview_vid.stop()
            self.preview_vid.hide()
            self.media_player.stop()
            self.media_player.hide()
            self.preview_gif.hide()

            # If a new selection is made, update the thumbnail and filepath.
            if not self.selected or self.selected != self.driver.selected:
                filepath = item.absolute_path
                self.file_label.set_file_path(filepath)
                ratio = self.devicePixelRatio()
                self.thumb_renderer.render(
                    time.time(),
                    item,
                    ThumbSize.XX_LARGE,
                    ratio,
                    update_on_ratio_change=True,
                )
                file_str: str = ""
                separator: str = f"<a style='color: #777777'><b>{os.path.sep}</a>"  # Gray
                for i, part in enumerate(filepath.parts):
                    part_ = part.strip(os.path.sep)
                    if i != len(filepath.parts) - 1:
                        file_str += f"{"\u200b".join(part_)}{separator}</b>"
                    else:
                        file_str += f"<br><b>{"\u200b".join(part_)}</b>"
                self.file_label.setText(file_str)
                self.file_label.setCursor(Qt.CursorShape.PointingHandCursor)

                self.preview_img.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)
                self.preview_img.setCursor(Qt.CursorShape.PointingHandCursor)

                self.opener = FileOpenerHelper(filepath)
                self.open_file_action.triggered.connect(self.opener.open_file)
                self.open_explorer_action.triggered.connect(self.opener.open_explorer)

                # TODO: Do this all somewhere else, this is just here temporarily.
                ext: str = filepath.suffix.lower()
                try:
                    if MediaCategories.is_ext_in_category(
                        ext, MediaCategories.IMAGE_ANIMATED_TYPES, mime_fallback=True
                    ):
                        if self.preview_gif.movie():
                            self.preview_gif.movie().stop()
                            self.gif_buffer.close()

                        image: Image.Image = Image.open(filepath)
                        anim_image: Image.Image = image
                        image_bytes_io: io.BytesIO = io.BytesIO()
                        anim_image.save(
                            image_bytes_io,
                            "GIF",
                            lossless=True,
                            save_all=True,
                            loop=0,
                            disposal=2,
                        )
                        image_bytes_io.seek(0)
                        ba: bytes = image_bytes_io.read()

                        self.gif_buffer.setData(ba)
                        movie = QMovie(self.gif_buffer, QByteArray())
                        self.preview_gif.setMovie(movie)
                        movie.start()

                        self.resizeEvent(
                            QResizeEvent(
                                QSize(image.width, image.height),
                                QSize(image.width, image.height),
                            )
                        )
                        self.preview_img.hide()
                        self.preview_vid.hide()
                        self.preview_gif.show()

                    image = None
                    if MediaCategories.is_ext_in_category(ext, MediaCategories.IMAGE_RASTER_TYPES):
                        image = Image.open(str(filepath))
                    elif MediaCategories.is_ext_in_category(ext, MediaCategories.IMAGE_RAW_TYPES):
                        try:
                            with rawpy.imread(str(filepath)) as raw:
                                rgb = raw.postprocess()
                                image = Image.new("L", (rgb.shape[1], rgb.shape[0]), color="black")
                        except (
                            rawpy._rawpy.LibRawIOError,
                            rawpy._rawpy.LibRawFileUnsupportedError,
                        ):
                            pass
                    elif MediaCategories.is_ext_in_category(ext, MediaCategories.AUDIO_TYPES):
                        self.media_player.show()
                        self.media_player.play(filepath)
                    elif MediaCategories.is_ext_in_category(
                        ext, MediaCategories.VIDEO_TYPES
                    ) and is_readable_video(filepath):
                        video = cv2.VideoCapture(str(filepath), cv2.CAP_FFMPEG)
                        video.set(
                            cv2.CAP_PROP_POS_FRAMES,
                            (video.get(cv2.CAP_PROP_FRAME_COUNT) // 2),
                        )
                        success, frame = video.read()
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        image = Image.fromarray(frame)
                        if success:
                            self.preview_img.hide()
                            self.preview_vid.play(filepath, QSize(image.width, image.height))
                            self.resizeEvent(
                                QResizeEvent(
                                    QSize(image.width, image.height),
                                    QSize(image.width, image.height),
                                )
                            )
                            self.preview_vid.show()

                    # Stats for specific file types are displayed here.
                    if image and (
                        MediaCategories.is_ext_in_category(
                            ext, MediaCategories.IMAGE_RASTER_TYPES, mime_fallback=True
                        )
                        or MediaCategories.is_ext_in_category(
                            ext, MediaCategories.VIDEO_TYPES, mime_fallback=True
                        )
                        or MediaCategories.is_ext_in_category(
                            ext, MediaCategories.IMAGE_RAW_TYPES, mime_fallback=True
                        )
                    ):
                        self.dimensions_label.setText(
                            f"{ext.upper()[1:]}  •  {format_size(filepath.stat().st_size)}\n"
                            f"{image.width} x {image.height} px"
                        )
                    elif MediaCategories.is_ext_in_category(
                        ext, MediaCategories.FONT_TYPES, mime_fallback=True
                    ):
                        try:
                            font = ImageFont.truetype(filepath)
                            self.dimensions_label.setText(
                                f"{ext.upper()[1:]} •  {format_size(filepath.stat().st_size)}\n"
                                f"{font.getname()[0]} ({font.getname()[1]}) "
                            )
                        except OSError:
                            self.dimensions_label.setText(
                                f"{ext.upper()[1:]}  •  {format_size(filepath.stat().st_size)}"
                            )
                            logger.info("update_widget couldn't read font file", filepath=filepath)
                    else:
                        self.dimensions_label.setText(f"{ext.upper()[1:]}")
                        self.dimensions_label.setText(
                            f"{ext.upper()[1:]}  •  {format_size(filepath.stat().st_size)}"
                        )
                    self.update_date_label(filepath)

                    if not filepath.is_file():
                        raise FileNotFoundError

                except (FileNotFoundError, cv2.error) as e:
                    self.dimensions_label.setText(f"{ext.upper()[1:]}")
                    logger.error("Couldn't render thumbnail", filepath=filepath, error=e)
                    self.update_date_label()
                except (
                    UnidentifiedImageError,
                    DecompressionBombError,
                ) as e:
                    self.dimensions_label.setText(
                        f"{ext.upper()[1:]}  •  {format_size(filepath.stat().st_size)}"
                    )
                    logger.error("Couldn't render thumbnail", filepath=filepath, error=e)
                    self.update_date_label(filepath)

                if self.preview_img.is_connected:
                    self.preview_img.clicked.disconnect()
                self.preview_img.clicked.connect(lambda checked=False, pth=filepath: open_file(pth))
                self.preview_img.is_connected = True

            self.selected = self.driver.selected
            logger.info(
                "rendering item fields",
                item=item.id,
                fields=[x.type_key for x in item.fields],
            )
            for idx, field in enumerate(item.fields):
                self.write_container(idx, field)

            # Hide leftover containers
            if len(self.containers) > len(item.fields):
                for i, c in enumerate(self.containers):
                    if i > (len(item.fields) - 1):
                        c.setHidden(True)

            self.add_field_button.setHidden(False)

        # Multiple Selected Items
        elif len(self.driver.selected) > 1:
            self.preview_img.show()
            self.preview_gif.hide()
            self.preview_vid.stop()
            self.preview_vid.hide()
            self.media_player.stop()
            self.media_player.hide()
            self.update_date_label()
            if self.selected != self.driver.selected:
                self.file_label.setText(f"<b>{len(self.driver.selected)}</b> Items Selected")
                self.file_label.setCursor(Qt.CursorShape.ArrowCursor)
                self.file_label.set_file_path("")
                self.dimensions_label.setText("")

                self.preview_img.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
                self.preview_img.setCursor(Qt.CursorShape.ArrowCursor)

                ratio = self.devicePixelRatio()
                self.thumb_renderer.render(
                    time.time(),
                    None,
                    ThumbSize.XX_LARGE,
                    ratio,
                    is_loading=True,
                    update_on_ratio_change=True,
                )
                if self.preview_img.is_connected:
                    self.preview_img.clicked.disconnect()
                    self.preview_img.is_connected = False

            # fill shared fields from first item
            first_item = self.driver.frame_content[self.driver.selected[0]]
            common_fields = [f for f in first_item.fields]
            mixed_fields = []

            # iterate through other items
            for grid_idx in self.driver.selected[1:]:
                item = self.driver.frame_content[grid_idx]
                item_field_types = {f.type_key for f in item.fields}
                for f in common_fields[:]:
                    if f.type_key not in item_field_types:
                        common_fields.remove(f)
                        mixed_fields.append(f)

            self.common_fields = common_fields
            self.mixed_fields = sorted(mixed_fields, key=lambda x: x.type.position)

            self.selected = list(self.driver.selected)
            logger.info(
                "update_widgets common_fields",
                common_fields=self.common_fields,
            )
            for i, f in enumerate(self.common_fields):
                self.write_container(i, f)

            logger.info(
                "update_widgets mixed_fields",
                mixed_fields=self.mixed_fields,
                start=len(self.common_fields),
            )
            for i, f in enumerate(self.mixed_fields, start=len(self.common_fields)):
                self.write_container(i, f, is_mixed=True)

            # Hide leftover containers
            if len(self.containers) > len(self.common_fields) + len(self.mixed_fields):
                for i, c in enumerate(self.containers):
                    if i > (len(self.common_fields) + len(self.mixed_fields) - 1):
                        c.setHidden(True)

            self.add_field_button.setHidden(False)

        self.initialized = True

        self.setWindowTitle(window_title)
        self.show()
        return True

    def set_tags_updated_slot(self, slot: object):
        """Replacement for tag_callback."""
        if self.is_connected:
            self.tags_updated.disconnect()

        logger.info("[UPDATE CONTAINER] Setting tags updated slot")
        self.tags_updated.connect(slot)
        self.is_connected = True

    def write_container(self, index: int, field: BaseField, is_mixed: bool = False):
        """Update/Create data for a FieldContainer.

        Args:
            index(int): The container index.
            field(BaseField): The type of field to write to.
            is_mixed(bool): Relevant when multiple items are selected.
                If True, field is not present in all selected items.
        """
        # Remove 'Add Field' button from scroll_layout, to be re-added later.
        self.scroll_layout.takeAt(self.scroll_layout.count() - 1).widget()
        if len(self.containers) < (index + 1):
            container = FieldContainer()
            self.containers.append(container)
            self.scroll_layout.addWidget(container)
        else:
            container = self.containers[index]

        if isinstance(field, TagBoxField):
            container.set_title(field.type.name)
            container.set_inline(False)
            title = f"{field.type.name} (Tag Box)"

            if not is_mixed:
                inner_container = container.get_inner_widget()
                if isinstance(inner_container, TagBoxWidget):
                    inner_container.set_field(field)
                    inner_container.set_tags(list(field.tags))

                    try:
                        inner_container.updated.disconnect()
                    except RuntimeError:
                        logger.error("Failed to disconnect inner_container.updated")

                else:
                    logger.info(
                        "inner_container is not instance of TagBoxWidget",
                        container=inner_container,
                    )
                    inner_container = TagBoxWidget(
                        field,
                        title,
                        self.driver,
                    )

                    container.set_inner_widget(inner_container)

                inner_container.updated.connect(
                    lambda: (
                        self.write_container(index, field),
                        self.update_widgets(),
                    )
                )
                # NOTE: Tag Boxes have no Edit Button (But will when you can convert field types)
                container.set_remove_callback(
                    lambda: remove_message_box(
                        prompt=self.remove_field_prompt(field.type.name),
                        title="Remove Field",
                        callback=lambda: (
                            self.remove_field(field),
                            self.update_selected_entry(self.driver),
                            # reload entry and its fields
                            self.update_widgets(),
                        ),
                    )
                )
            else:
                text = "<i>Mixed Data</i>"
                title = f"{field.type.name} (Wacky Tag Box)"
                inner_container = TextWidget(title, text)
                container.set_inner_widget(inner_container)

            self.tags_updated.emit()
            # self.dynamic_widgets.append(inner_container)
        elif field.type.type == FieldTypeEnum.TEXT_LINE:
            container.set_title(field.type.name)
            container.set_inline(False)

            # Normalize line endings in any text content.
            if not is_mixed:
                assert isinstance(field.value, (str, type(None)))
                text = field.value or ""
            else:
                text = "<i>Mixed Data</i>"

            title = f"{field.type.name} ({field.type.type.value})"
            inner_container = TextWidget(title, text)
            container.set_inner_widget(inner_container)
            if not is_mixed:
                modal = PanelModal(
                    EditTextLine(field.value),
                    title=title,
                    window_title=f"Edit {field.type.type.value}",
                    save_callback=(
                        lambda content: (
                            self.update_field(field, content),
                            self.update_widgets(),
                        )
                    ),
                )
                if "pytest" in sys.modules:
                    # for better testability
                    container.modal = modal  # type: ignore

                container.set_edit_callback(modal.show)
                container.set_remove_callback(
                    lambda: remove_message_box(
                        prompt=self.remove_field_prompt(field.type.type.value),
                        title="Remove Field",
                        callback=lambda: (
                            self.remove_field(field),
                            self.update_widgets(),
                        ),
                    )
                )

        elif field.type.type == FieldTypeEnum.TEXT_BOX:
            container.set_title(field.type.name)
            # container.set_editable(True)
            container.set_inline(False)
            # Normalize line endings in any text content.
            if not is_mixed:
                assert isinstance(field.value, (str, type(None)))
                text = (field.value or "").replace("\r", "\n")
            else:
                text = "<i>Mixed Data</i>"
            title = f"{field.type.name} (Text Box)"
            inner_container = TextWidget(title, text)
            container.set_inner_widget(inner_container)
            if not is_mixed:
                modal = PanelModal(
                    EditTextBox(field.value),
                    title=title,
                    window_title=f"Edit {field.type.name}",
                    save_callback=(
                        lambda content: (
                            self.update_field(field, content),
                            self.update_widgets(),
                        )
                    ),
                )
                container.set_edit_callback(modal.show)
                container.set_remove_callback(
                    lambda: remove_message_box(
                        prompt=self.remove_field_prompt(field.type.name),
                        title="Remove Field",
                        callback=lambda: (
                            self.remove_field(field),
                            self.update_widgets(),
                        ),
                    )
                )

        elif field.type.type == FieldTypeEnum.DATETIME:
            if not is_mixed:
                try:
                    container.set_title(field.type.name)
                    # container.set_editable(False)
                    container.set_inline(False)
                    # TODO: Localize this and/or add preferences.
                    date = dt.strptime(field.value, "%Y-%m-%d %H:%M:%S")
                    title = f"{field.type.name} (Date)"
                    inner_container = TextWidget(title, date.strftime("%D - %r"))
                    container.set_inner_widget(inner_container)
                except Exception:
                    container.set_title(field.type.name)
                    # container.set_editable(False)
                    container.set_inline(False)
                    title = f"{field.type.name} (Date) (Unknown Format)"
                    inner_container = TextWidget(title, str(field.value))
                    container.set_inner_widget(inner_container)

                container.set_remove_callback(
                    lambda: remove_message_box(
                        prompt=self.remove_field_prompt(field.type.name),
                        title="Remove Field",
                        callback=lambda: (
                            self.remove_field(field),
                            self.update_widgets(),
                        ),
                    )
                )
            else:
                text = "<i>Mixed Data</i>"
                title = f"{field.type.name} (Wacky Date)"
                inner_container = TextWidget(title, text)
                container.set_inner_widget(inner_container)
        else:
            logger.warning("write_container - unknown field", field=field)
            container.set_title(field.type.name)
            container.set_inline(False)
            title = f"{field.type.name} (Unknown Field Type)"
            inner_container = TextWidget(title, field.type.name)
            container.set_inner_widget(inner_container)
            container.set_remove_callback(
                lambda: remove_message_box(
                    prompt=self.remove_field_prompt(field.type.name),
                    title="Remove Field",
                    callback=lambda: (
                        self.remove_field(field),
                        self.update_widgets(),
                    ),
                )
            )

        container.edit_button.setHidden(True)
        container.setHidden(False)
        self.place_add_field_button()

    def remove_field(self, field: BaseField):
        """Remove a field from all selected Entries."""
        logger.info("removing field", field=field, selected=self.selected)
        entry_ids = []

        for grid_idx in self.selected:
            entry = self.driver.frame_content[grid_idx]
            entry_ids.append(entry.id)

        self.lib.remove_entry_field(field, entry_ids)

        # if the field is meta tags, update the badges
        if field.type_key == _FieldID.TAGS_META.value:
            self.driver.update_badges(self.selected)

    def update_field(self, field: BaseField, content: str) -> None:
        """Update a field in all selected Entries, given a field object."""
        assert isinstance(
            field, (TextField, DatetimeField, TagBoxField)
        ), f"instance: {type(field)}"

        entry_ids = []
        for grid_idx in self.selected:
            entry = self.driver.frame_content[grid_idx]
            entry_ids.append(entry.id)

        assert entry_ids, "No entries selected"
        self.lib.update_entry_field(
            entry_ids,
            field,
            content,
        )
