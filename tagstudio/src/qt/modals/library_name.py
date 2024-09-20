from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout


class LibraryNameDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Choose Library Name")

        # Create layout
        layout = QVBoxLayout()

        # Add label
        label = QLabel("Choose Library Name:")
        layout.addWidget(label)

        # Add text input
        self.library_name_input = QLineEdit(self)
        layout.addWidget(self.library_name_input)

        # Add OK button
        ok_button = QPushButton("OK", self)
        ok_button.clicked.connect(self.accept)  # Close dialog when clicked
        layout.addWidget(ok_button)

        # Set layout to the dialog
        self.setLayout(layout)

    def get_library_name(self):
        return self.library_name_input.text()
