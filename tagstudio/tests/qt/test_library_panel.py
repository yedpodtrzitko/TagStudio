from src.qt.widgets.library_panel import LibraryPanel


def test_panel_toggle_libs(qt_driver, library):
    panel = LibraryPanel(library, qt_driver)
    panel.update_widgets()

    folders = {x.uuid for x in library.get_folders()}
    assert set(panel.lib_dirs_container.library_dirs.keys()) == folders
