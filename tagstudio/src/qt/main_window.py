# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio


import typing

import structlog
from PySide6.QtCore import (QCoreApplication, QMetaObject, QRect, QSize, Qt, QStringListModel)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QVBoxLayout, QLayout, QLineEdit, QMainWindow,
                               QPushButton, QScrollArea, QSizePolicy,
                               QStatusBar, QWidget, QSplitter, QSpacerItem, QCompleter)

from src.qt.enums import WindowContent
from src.qt.pagination import Pagination
from src.qt.widgets.landing import LandingWidget
from src.qt.widgets.library_nodirs import LibraryNoFolders

# Only import for type checking/autocompletion, will not be imported at runtime.
if typing.TYPE_CHECKING:
    from src.qt.ts_qt import QtDriver

logger = structlog.get_logger(__name__)


class Ui_MainWindow(QMainWindow):

    def __init__(self, driver: "QtDriver", parent=None) -> None:
        super().__init__(parent)
        self.driver: "QtDriver" = driver
        self.setupUi()

    def setupUi(self, ):
        if not self.objectName():
            self.setObjectName(u"MainWindow")
        self.resize(1300, 720)

        self.centralwidget = QWidget(self)
        self.centralwidget.setObjectName(u"centralwidget")
        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName(u"gridLayout")

        self.horizontalLayout = QHBoxLayout()
        self.horizontalLayout.setObjectName(u"horizontalLayout")

        # ComboBox group for search type and thumbnail size
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")

        # left side spacer
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout_3.addItem(spacerItem)

        # Search type selector
        self.comboBox_2 = QComboBox(self.centralwidget)
        self.comboBox_2.setMinimumSize(QSize(165, 0))
        self.comboBox_2.setObjectName("comboBox_2")
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.horizontalLayout_3.addWidget(self.comboBox_2)

        # Thumbnail Size placeholder
        self.thumb_size_combobox = QComboBox(self.centralwidget)
        self.thumb_size_combobox.setObjectName(u"thumbSizeComboBox")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.thumb_size_combobox.sizePolicy().hasHeightForWidth())
        self.thumb_size_combobox.setSizePolicy(sizePolicy)
        self.thumb_size_combobox.setMinimumWidth(128)
        self.thumb_size_combobox.setMaximumWidth(352)
        self.horizontalLayout_3.addWidget(self.thumb_size_combobox)
        self.gridLayout.addLayout(self.horizontalLayout_3, 5, 0, 1, 1)

        self.frame_container = QWidget()
        self.frame_layout = QVBoxLayout(self.frame_container)
        self.frame_layout.setSpacing(0)

        self.scrollArea = QScrollArea()
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setFocusPolicy(Qt.FocusPolicy.WheelFocus)
        self.scrollArea.setFrameShape(QFrame.Shape.NoFrame)
        self.scrollArea.setFrameShadow(QFrame.Shadow.Plain)
        self.scrollArea.setWidgetResizable(True)
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(
            u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 1260, 590))
        self.gridLayout_2 = QGridLayout(self.scrollAreaWidgetContents)
        self.gridLayout_2.setSpacing(8)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.gridLayout_2.setContentsMargins(0, 0, 0, 8)
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.frame_layout.addWidget(self.scrollArea)

        self.landing_widget: LandingWidget = LandingWidget(self.driver, self.devicePixelRatio())
        self.frame_layout.addWidget(self.landing_widget)

        # shown in case library has no folder
        # widget with a label and a button to create a folder
        self.lib_nofolders = LibraryNoFolders()
        self.frame_layout.addWidget(self.lib_nofolders)

        self.pagination = Pagination()
        self.frame_layout.addWidget(self.pagination)

        self.splitter = QSplitter()
        self.splitter.setObjectName("splitter")
        self.splitter.setHandleWidth(12)

        self.library_sidebar = QWidget()
        self.library_sidebar_layout = QVBoxLayout(self.library_sidebar)

        self.splitter.addWidget(self.library_sidebar)
        self.splitter.setStretchFactor(0, 0)

        self.splitter.addWidget(self.frame_container)
        self.splitter.setStretchFactor(1, 1)

        self.horizontalLayout.addWidget(self.splitter)

        self.gridLayout.addLayout(self.horizontalLayout, 10, 0, 1, 1)

        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalLayout_2.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.backButton = QPushButton(self.centralwidget)
        self.backButton.setObjectName(u"backButton")
        self.backButton.setMinimumSize(QSize(0, 32))
        self.backButton.setMaximumSize(QSize(32, 16777215))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        self.backButton.setFont(font)

        self.horizontalLayout_2.addWidget(self.backButton)

        self.forwardButton = QPushButton(self.centralwidget)
        self.forwardButton.setObjectName(u"forwardButton")
        self.forwardButton.setMinimumSize(QSize(0, 32))
        self.forwardButton.setMaximumSize(QSize(32, 16777215))
        font1 = QFont()
        font1.setPointSize(14)
        font1.setBold(True)
        font1.setKerning(True)
        self.forwardButton.setFont(font1)

        self.horizontalLayout_2.addWidget(self.forwardButton)

        self.searchField = QLineEdit(self.centralwidget)
        self.searchField.setObjectName(u"searchField")
        self.searchField.setMinimumSize(QSize(0, 32))
        font2 = QFont()
        font2.setPointSize(11)
        font2.setBold(False)
        self.searchField.setFont(font2)

        self.search_field_model = QStringListModel()
        self.search_field_completer = QCompleter(self.search_field_model, self.searchField)
        self.search_field_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.searchField.setCompleter(self.search_field_completer)

        self.horizontalLayout_2.addWidget(self.searchField)

        self.searchButton = QPushButton(self.centralwidget)
        self.searchButton.setObjectName(u"searchButton")
        self.searchButton.setMinimumSize(QSize(0, 32))
        self.searchButton.setFont(font2)

        self.horizontalLayout_2.addWidget(self.searchButton)
        self.gridLayout.addLayout(self.horizontalLayout_2, 3, 0, 1, 1)
        self.gridLayout_2.setContentsMargins(6, 6, 6, 6)

        self.setCentralWidget(self.centralwidget)

        self.statusbar = QStatusBar(self)
        self.statusbar.setObjectName("statusbar")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.statusbar.sizePolicy().hasHeightForWidth())
        self.statusbar.setSizePolicy(sizePolicy1)
        self.setStatusBar(self.statusbar)

        self.retranslateUi()

        QMetaObject.connectSlotsByName(self)

    def retranslateUi(self):
        self.setWindowTitle(QCoreApplication.translate(
            "MainWindow", u"MainWindow", None))
        # Navigation buttons
        self.backButton.setText(
            QCoreApplication.translate("MainWindow", u"<", None))
        self.forwardButton.setText(
            QCoreApplication.translate("MainWindow", u">", None))

        # Search field
        self.searchField.setPlaceholderText(
            QCoreApplication.translate("MainWindow", u"Search Entries", None))
        self.searchButton.setText(
            QCoreApplication.translate("MainWindow", u"Search", None))

        # Search type selector
        self.comboBox_2.setItemText(0, QCoreApplication.translate("MainWindow", "And (Includes All Tags)"))
        self.comboBox_2.setItemText(1, QCoreApplication.translate("MainWindow", "Or (Includes Any Tag)"))
        self.thumb_size_combobox.setCurrentText("")

        # Thumbnail size selector
        self.thumb_size_combobox.setPlaceholderText(
            QCoreApplication.translate("MainWindow", u"Thumbnail Size", None))

    def moveEvent(self, event) -> None:
        # time.sleep(0.02)  # sleep for 20ms
        pass

    def resizeEvent(self, event) -> None:
        # time.sleep(0.02)  # sleep for 20ms
        pass

    def set_main_content(self, content: WindowContent):
        logger.info("set_main_content", content=content)
        if content == WindowContent.LANDING_PAGE:
            self.scrollArea.setHidden(True)
            self.landing_widget.setHidden(False)
            self.landing_widget.animate_logo_in()
            self.lib_nofolders.setHidden(True)
        elif content == WindowContent.LIBRARY_EMPTY:
            self.scrollArea.setHidden(True)
            self.landing_widget.setHidden(True)
            self.lib_nofolders.setHidden(False)
        elif content == WindowContent.LIBRARY_CONTENT:
            self.landing_widget.setHidden(True)
            self.landing_widget.set_status_label("")
            self.scrollArea.setHidden(False)
            self.lib_nofolders.setHidden(True)
