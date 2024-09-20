from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class LibraryNameDialog(QDialog):
    chosen_path: Path | None

    def __init__(self):
        super().__init__()

        self.setFixedWidth(400)

        self.chosen_path = None

        self.setWindowTitle("Choose Library Name")

        layout = QVBoxLayout()

        label = QLabel("Choose Library Name")
        layout.addWidget(label)

        self.library_name_input = QLineEdit(self)
        self.library_name_input.textChanged.connect(self.update_storage_label)
        layout.addWidget(self.library_name_input)

        self.directory_label = QLabel("No directory selected")
        layout.addWidget(self.directory_label)

        choose_directory_button = QPushButton("Choose Library Storage", self)
        choose_directory_button.clicked.connect(self.choose_directory)
        layout.addWidget(choose_directory_button)

        cancel_button = QPushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)

        ok_button = QPushButton("OK", self)
        ok_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addWidget(cancel_button)
        button_layout.addWidget(ok_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)

    def get_storage_path(self) -> Path:
        # return self.chosen_path / f"TS {self.get_library_name()}"
        return self.chosen_path / self.get_library_name()

    def get_library_name(self):
        return self.library_name_input.text().strip()

    def choose_directory(self):
        """Open a dialog to choose a directory and display the selected path."""
        directory = QFileDialog.getExistingDirectory(self, "Select Directory")
        if directory:
            self.chosen_path = Path(directory)
            self.update_storage_label()

    def update_storage_label(self):
        if self.chosen_path:
            self.directory_label.setText(f"Selected Directory: {self.get_storage_path()}")
        else:
            self.directory_label.setText("No directory selected")
