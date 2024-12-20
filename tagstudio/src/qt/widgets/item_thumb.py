# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio
import time
import typing
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from PIL import Image, ImageQt
from PySide6.QtCore import QEvent, QMimeData, QSize, Qt, QUrl
from PySide6.QtGui import QAction, QDrag, QEnterEvent, QPixmap
from PySide6.QtWidgets import (
    QBoxLayout,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from src.core.constants import (
    TAG_ARCHIVED,
    TAG_FAVORITE,
)
from src.core.library import Entry, ItemType, Library
from src.core.library.alchemy.enums import FilterState
from src.core.library.alchemy.fields import _FieldID
from src.core.library.alchemy.library import MissingFieldAction
from src.qt.enums import ThumbSize
from src.qt.flowlayout import FlowWidget
from src.qt.helpers.file_opener import FileOpenerHelper
from src.qt.platform_strings import PlatformStrings
from src.qt.widgets.thumb_button import ThumbButton
from src.qt.widgets.thumb_renderer import ThumbRenderer

if TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)


class BadgeType(Enum):
    FAVORITE = "Favorite"
    ARCHIVED = "Archived"


BADGE_TAGS = {
    BadgeType.FAVORITE: TAG_FAVORITE,
    BadgeType.ARCHIVED: TAG_ARCHIVED,
}


def badge_update_lock(func):
    """Prevent recursively triggering badge updates."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.driver.badge_update_lock:
            return

        self.driver.badge_update_lock = True
        try:
            func(self, *args, **kwargs)
        except Exception:
            raise
        finally:
            self.driver.badge_update_lock = False

    return wrapper


class ItemThumb(FlowWidget):
    """The thumbnail widget for a library item (Entry, Collation, Tag Group, etc.)."""

    update_cutoff: float = time.time()
    rendered_id: int

    collation_icon_128: Image.Image = Image.open(
        str(Path(__file__).parents[3] / "resources/qt/images/collation_icon_128.png")
    )
    collation_icon_128.load()

    tag_group_icon_128: Image.Image = Image.open(
        str(Path(__file__).parents[3] / "resources/qt/images/tag_group_icon_128.png")
    )
    tag_group_icon_128.load()

    small_text_style = (
        "background-color:rgba(0, 0, 0, 192);"
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

    med_text_style = (
        "background-color:rgba(0, 0, 0, 192);"
        "color:#FFFFFF;"
        "font-family:Oxanium;"
        "font-weight:bold;"
        "font-size:18px;"
        "border-radius:3px;"
        "padding-top: 4px;"
        "padding-right: 1px;"
        "padding-bottom: 1px;"
        "padding-left: 1px;"
    )

    def __init__(
        self,
        mode: ItemType,
        library: Library,
        driver: "QtDriver",
        thumb_size: ThumbSize,
        grid_idx: int,
    ):
        super().__init__()
        self.grid_idx = grid_idx
        self.lib = library
        self.mode: ItemType = mode
        self.driver = driver
        self.item_id: int | None = None
        self.thumb_size: ThumbSize = thumb_size
        self.setMinimumSize(thumb_size.value, thumb_size.value)
        self.setMaximumSize(thumb_size.value, thumb_size.value)
        self.setMouseTracking(True)
        self.rendered_id = None
        check_size = 24

        # +----------+
        # |   ARC FAV| Top Right: Favorite & Archived Badges
        # |          |
        # |          |
        # |EXT      #| Lower Left: File Type, Tag Group Icon, or Collation Icon
        # +----------+ Lower Right: Collation Count, Video Length, or Word Count

        # Thumbnail ============================================================

        # +----------+
        # |*--------*|
        # ||        ||
        # ||        ||
        # |*--------*|
        # +----------+
        self.base_layout = QVBoxLayout(self)
        self.base_layout.setObjectName("baseLayout")
        self.base_layout.setContentsMargins(0, 0, 0, 0)

        # +----------+
        # |[~~~~~~~~]|
        # |          |
        # |          |
        # |          |
        # +----------+
        self.top_layout = QHBoxLayout()
        self.top_layout.setObjectName("topLayout")
        self.top_layout.setContentsMargins(6, 6, 6, 6)
        self.top_container = QWidget()
        self.top_container.setLayout(self.top_layout)
        self.base_layout.addWidget(self.top_container)

        # +----------+
        # |[~~~~~~~~]|
        # |     ^    |
        # |     |    |
        # |     v    |
        # +----------+
        self.base_layout.addStretch(2)

        # +----------+
        # |[~~~~~~~~]|
        # |     ^    |
        # |     v    |
        # |[~~~~~~~~]|
        # +----------+
        self.bottom_layout = QHBoxLayout()
        self.bottom_layout.setObjectName("bottomLayout")
        self.bottom_layout.setContentsMargins(6, 6, 6, 6)
        self.bottom_container = QWidget()
        self.bottom_container.setLayout(self.bottom_layout)
        self.base_layout.addWidget(self.bottom_container)

        self.thumb_button = ThumbButton(self, thumb_size)
        self.renderer = ThumbRenderer(library=library)
        self.renderer.updated.connect(
            lambda ts, i, s, entry: (
                self.update_thumb(ts, image=i),
                self.update_size(ts, size=s),
                self.set_filename(entry),
            )
        )
        self.thumb_button.setFlat(True)
        self.thumb_button.setLayout(self.base_layout)
        self.thumb_button.setContextMenuPolicy(Qt.ContextMenuPolicy.ActionsContextMenu)

        self.opener = FileOpenerHelper("")
        open_file_action = QAction("Open file", self)
        open_file_action.triggered.connect(self.opener.open_file)
        open_explorer_action = QAction(PlatformStrings.open_file_str, self)
        open_explorer_action.triggered.connect(self.opener.open_explorer)
        self.thumb_button.addAction(open_file_action)
        self.thumb_button.addAction(open_explorer_action)

        # Static Badges ========================================================

        # Item Type Badge ------------------------------------------------------
        # Used for showing the Tag Group / Collation icons.
        # Mutually exclusive with the File Extension Badge.
        self.item_type_badge = QLabel()
        self.item_type_badge.setObjectName("itemBadge")
        self.item_type_badge.setPixmap(
            QPixmap.fromImage(
                ImageQt.ImageQt(
                    ItemThumb.collation_icon_128.resize(
                        (check_size, check_size), Image.Resampling.BILINEAR
                    )
                )
            )
        )
        self.item_type_badge.setMinimumSize(check_size, check_size)
        self.item_type_badge.setMaximumSize(check_size, check_size)
        self.bottom_layout.addWidget(self.item_type_badge)

        # File Extension Badge -------------------------------------------------
        # Mutually exclusive with the File Extension Badge.
        self.ext_badge = QLabel()
        self.ext_badge.setObjectName("extBadge")
        self.ext_badge.setStyleSheet(ItemThumb.small_text_style)
        self.bottom_layout.addWidget(self.ext_badge)
        self.bottom_layout.addStretch(2)

        # Count Badge ----------------------------------------------------------
        # Used for Tag Group + Collation counts, video length, word count, etc.
        self.count_badge = QLabel()
        self.count_badge.setObjectName("countBadge")
        self.count_badge.setText("-:--")
        self.count_badge.setStyleSheet(ItemThumb.small_text_style)
        self.bottom_layout.addWidget(self.count_badge, alignment=Qt.AlignmentFlag.AlignBottom)
        self.top_layout.addStretch(2)

        # Intractable Badges ===================================================
        self.cb_container = QWidget()
        self.cb_layout = QHBoxLayout()
        self.cb_layout.setDirection(QBoxLayout.Direction.RightToLeft)
        self.cb_layout.setContentsMargins(0, 0, 0, 0)
        self.cb_layout.setSpacing(6)
        self.cb_container.setLayout(self.cb_layout)
        self.top_layout.addWidget(self.cb_container)

        self.badge_active: dict[BadgeType, bool] = {
            BadgeType.FAVORITE: False,
            BadgeType.ARCHIVED: False,
        }

        self.badges: dict[BadgeType, QCheckBox] = {}
        badge_icons = {
            BadgeType.FAVORITE: (
                ":/images/star_icon_empty_128.png",
                ":/images/star_icon_filled_128.png",
            ),
            BadgeType.ARCHIVED: (
                ":/images/box_icon_empty_128.png",
                ":/images/box_icon_filled_128.png",
            ),
        }
        for badge_type in BadgeType:
            icon_empty, icon_checked = badge_icons[badge_type]
            badge = QCheckBox()
            badge.setObjectName(badge_type.name)
            badge.setToolTip(badge_type.value)
            badge.setStyleSheet(
                f"QCheckBox::indicator{{width: {check_size}px;height: {check_size}px;}}"
                f"QCheckBox::indicator::unchecked{{image: url({icon_empty})}}"
                f"QCheckBox::indicator::checked{{image: url({icon_checked})}}"
            )
            badge.setMinimumSize(check_size, check_size)
            badge.setMaximumSize(check_size, check_size)
            badge.setHidden(True)

            badge.stateChanged.connect(lambda x, bt=badge_type: self.on_badge_check(bt))

            self.badges[badge_type] = badge
            self.cb_layout.addWidget(badge)

        self.set_mode(mode)

    def is_rendered(self, entry: Entry) -> bool:
        return self.rendered_id == entry.id

    @property
    def is_favorite(self) -> bool:
        return self.badge_active[BadgeType.FAVORITE]

    @property
    def is_archived(self):
        return self.badge_active[BadgeType.ARCHIVED]

    def set_mode(self, mode: ItemType) -> None:
        if mode == ItemType.NONE:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=True)
            self.unsetCursor()
            self.thumb_button.setHidden(True)
        elif mode == ItemType.ENTRY and self.mode != ItemType.ENTRY:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.thumb_button.setHidden(False)
            self.cb_container.setHidden(False)
            # Count Badge depends on file extension (video length, word count)
            self.item_type_badge.setHidden(True)
            self.count_badge.setStyleSheet(ItemThumb.small_text_style)
            self.count_badge.setHidden(True)
            self.ext_badge.setHidden(True)
        elif mode == ItemType.COLLATION and self.mode != ItemType.COLLATION:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.thumb_button.setHidden(False)
            self.cb_container.setHidden(True)
            self.ext_badge.setHidden(True)
            self.count_badge.setStyleSheet(ItemThumb.med_text_style)
            self.count_badge.setHidden(False)
            self.item_type_badge.setHidden(False)
        elif mode == ItemType.TAG_GROUP and self.mode != ItemType.TAG_GROUP:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, on=False)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.thumb_button.setHidden(False)
            self.ext_badge.setHidden(True)
            self.count_badge.setHidden(False)
            self.item_type_badge.setHidden(False)
        self.mode = mode

    def set_filename(self, entry: Entry) -> None:
        # if MediaType.VIDEO in media_types or MediaType.AUDIO in media_types:
        #    self.count_badge.setHidden(False)
        self.count_badge.setHidden(True)
        if self.mode == ItemType.ENTRY:
            self.ext_badge.setHidden(False)
            self.ext_badge.setText(entry.path.name)

    def set_count(self, count: str) -> None:
        if count:
            self.count_badge.setHidden(False)
            self.count_badge.setText(count)
        else:
            if self.mode == ItemType.ENTRY:
                self.ext_badge.setHidden(True)
                self.count_badge.setHidden(True)

    def update_thumb(self, timestamp: float, image: QPixmap | None = None):
        """Update attributes of a thumbnail element."""
        if timestamp > ItemThumb.update_cutoff:
            self.rendered_id = self.item_id
            self.thumb_button.setIcon(image or QPixmap())

    def update_size(self, timestamp: float, size: QSize):
        """Updates attributes of a thumbnail element."""
        if timestamp > ItemThumb.update_cutoff and self.thumb_button.iconSize != size:
            self.thumb_button.setIconSize(size)
            self.thumb_button.setMinimumSize(size)
            self.thumb_button.setMaximumSize(size)

    def update_clickable(self, clickable: typing.Callable):
        """Updates attributes of a thumbnail element."""
        if self.thumb_button.is_connected:
            self.thumb_button.pressed.disconnect()
        if clickable:
            self.thumb_button.pressed.connect(clickable)
            self.thumb_button.is_connected = True

    def refresh_badge(self, entry: Entry | None = None):
        if not entry:
            if not self.item_id:
                logger.error("missing both entry and item_id")
                return None

            entry = self.lib.get_entry(self.item_id)
            if not entry:
                logger.error("Entry not found", item_id=self.item_id)
                return

        self.assign_badge(BadgeType.ARCHIVED, entry.is_archived)
        self.assign_badge(BadgeType.FAVORITE, entry.is_favorited)

    def set_item_id(self, entry: Entry):
        self.opener.set_filepath(entry.absolute_path)
        self.item_id = entry.id

    def assign_badge(self, badge_type: BadgeType, value: bool) -> None:
        mode = self.mode
        # none mode to avoid recursive badge updates
        self.mode = ItemType.NONE
        badge = self.badges[badge_type]
        self.badge_active[badge_type] = value
        if badge.isChecked() != value:
            badge.setChecked(value)
            badge.setHidden(not value)

        self.mode = mode

    def show_check_badges(self, show: bool):
        if self.mode != ItemType.TAG_GROUP:
            for badge_type, badge in self.badges.items():
                is_hidden = not (show or self.badge_active[badge_type])
                badge.setHidden(is_hidden)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        self.show_check_badges(show=True)
        return super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        self.show_check_badges(show=False)
        return super().leaveEvent(event)

    @badge_update_lock
    def on_badge_check(self, badge_type: BadgeType):
        if self.mode == ItemType.NONE:
            return

        toggle_value = self.badges[badge_type].isChecked()

        self.badge_active[badge_type] = toggle_value
        tag_id = BADGE_TAGS[badge_type]

        # check if current item is selected. if so, update all selected items
        if self.grid_idx in self.driver.selected:
            update_items = self.driver.selected
        else:
            update_items = [self.grid_idx]

        for idx in update_items:
            entry = self.driver.frame_content[idx]
            self.toggle_item_tag(
                entry, toggle_value, tag_id, _FieldID.TAGS_META.name, MissingFieldAction.CREATE
            )
            # update the entry
            self.driver.frame_content[idx] = self.lib.search_library(
                FilterState(id=entry.id)
            ).items[0]

        self.driver.update_badges(update_items)

    def toggle_item_tag(
        self,
        entry: Entry,
        toggle_value: bool,
        tag_id: int,
        field_key: str,
        missing_field: MissingFieldAction = MissingFieldAction.SKIP,
    ):
        logger.info(
            "toggle_item_tag",
            entry_id=entry.id,
            toggle_value=toggle_value,
            tag_id=tag_id,
            field_key=field_key,
        )

        tag = self.lib.get_tag(tag_id)
        if toggle_value:
            self.lib.add_field_tag(entry, tag, field_key, missing_field=missing_field)
        else:
            self.lib.remove_field_tag(entry, tag.id, field_key)

        if self.driver.preview_panel.is_open:
            self.driver.preview_panel.update_widgets()

    def mouseMoveEvent(self, event):  # noqa: N802
        if event.buttons() is not Qt.MouseButton.LeftButton:
            return

        drag = QDrag(self.driver)
        paths = []
        mimedata = QMimeData()

        selected_idxs = self.driver.selected
        if self.grid_idx not in selected_idxs:
            selected_idxs = [self.grid_idx]

        for grid_idx in selected_idxs:
            id = self.driver.item_thumbs[grid_idx].item_id
            entry = self.lib.get_entry(id)
            if not entry:
                continue

            url = QUrl.fromLocalFile(entry.absolute_path)
            paths.append(url)

        mimedata.setUrls(paths)
        drag.setMimeData(mimedata)
        drag.exec(Qt.DropAction.CopyAction)
        logger.info("dragged files to external program", thumbnail_indexs=selected_idxs)
