from pathlib import Path
from unittest import mock
from unittest.mock import Mock

from PySide6.QtWidgets import QFileDialog
from src.qt.widgets.library_dirs import LibraryDirsWidget


def test_widget_select_folders(qt_driver):
    # Given
    widget = LibraryDirsWidget(qt_driver.lib, qt_driver)
    qt_driver.item_thumbs = [Mock() for _ in qt_driver.frame_content]

    with (
        mock.patch("src.qt.widgets.library_dirs.QFileDialog.exec") as mock_exec,
        mock.patch("src.qt.widgets.library_dirs.QFileDialog.selectedFiles") as mock_files,
    ):
        mock_exec.return_value = QFileDialog.DialogCode.Accepted
        return_items = [Path("/tmp/path1"), Path("/tmp/path2")]
        mock_files.return_value = return_items

        # When
        widget.add_folders_callback()

    # Then
    assert set(return_items).issubset({x.path for x in qt_driver.lib.get_folders()})
