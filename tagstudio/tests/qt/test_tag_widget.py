from unittest.mock import patch

from src.core.library import Entry
from src.qt.widgets.tag import TagWidget
from src.qt.widgets.tag_box import TagBoxWidget


def test_tag_widget(qtbot, library, qt_driver):
    # given
    entry = library.entries[0]
    field = entry.tag_box_fields[0]

    tag_widget = TagBoxWidget(field, "title", [], qt_driver)

    qtbot.add_widget(tag_widget)

    assert not tag_widget.add_modal.isVisible()

    # when/then check no exception is raised
    tag_widget.add_button.clicked.emit()
    # check `tag_widget.add_modal` is visible
    assert tag_widget.add_modal.isVisible()


def test_tag_widget_add_existing_raises(qtbot, library, qt_driver):
    entry = library.entries[0]
    field = entry.tag_box_fields[0]

    tag = next(iter(entry.tags))

    tag_widget = TagBoxWidget(field, "title", [], qt_driver)

    qtbot.add_widget(tag_widget)

    tag_widget.driver.selected = [0]
    with patch.object(tag_widget, "error_occurred") as mocked:
        tag_widget.add_modal.widget.tag_chosen.emit(tag.id)
        assert mocked.emit.called


def test_tag_widget_add_new_pass(qtbot, library, qt_driver, generate_tag):
    # Given
    entry = library.entries[0]
    field = entry.tag_box_fields[0]

    tag = generate_tag(name="new_tag")
    library.add_tag(tag)

    tag_widget = TagBoxWidget(field, "title", [], qt_driver)

    qtbot.add_widget(tag_widget)

    tag_widget.driver.selected = [0]
    with patch.object(tag_widget, "error_occurred") as mocked:
        # When
        tag_widget.add_modal.widget.tag_chosen.emit(tag.id)

        # Then
        assert not mocked.emit.called


def test_tag_widget_remove(qtbot, qt_driver):
    entry: Entry = qt_driver.lib.entries[0]

    tag = list(entry.tags)[0]
    assert tag

    assert entry.tag_box_fields
    assert entry.tag_box_fields[0].tags
    field = entry.tag_box_fields[0]

    tag_widget = TagBoxWidget(field, "title", [tag], qt_driver)
    tag_widget.driver.selected = [0]

    qtbot.add_widget(tag_widget)

    # get all widgets from `tag_widget.base_layout`
    tag_widget = tag_widget.base_layout.itemAt(0).widget()
    assert isinstance(tag_widget, TagWidget)

    tag_widget.remove_button.clicked.emit()

    entry: Entry = qt_driver.lib.entries[0]
    assert not entry.tag_box_fields[0].tags
