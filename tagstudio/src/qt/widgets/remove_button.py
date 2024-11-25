from typing import Callable

from PySide6.QtWidgets import QMessageBox


def remove_message_box(prompt: str, title: str, callback: Callable):
    remove_mb = QMessageBox()
    remove_mb.setText(prompt)
    remove_mb.setWindowTitle(title)
    remove_mb.setIcon(QMessageBox.Icon.Warning)
    cancel_button = remove_mb.addButton("&Cancel", QMessageBox.ButtonRole.RejectRole)
    remove_button = remove_mb.addButton("&Remove", QMessageBox.ButtonRole.DestructiveRole)
    remove_mb.setDefaultButton(remove_button)
    remove_mb.setEscapeButton(cancel_button)

    result = remove_mb.exec_()
    if result == 3:  # TODO - dont use magic number here
        return callback()
