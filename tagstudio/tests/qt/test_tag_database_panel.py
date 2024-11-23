from unittest.mock import Mock

from src.qt.modals.tag_database import TagDatabasePanel


def test_panel_tag_search(qt_driver, library):
    # Given
    panel = TagDatabasePanel(library, driver=None, is_popup=False)

    # When
    tag = library.tags[0]
    panel.update_tags(tag.name)

    # Then
    assert panel.scroll_layout.count() == 1


def test_panel_tag_add(qt_driver, library):
    # Given
    entry = next(library.get_entries(with_joins=True))
    panel = TagDatabasePanel(library, driver=qt_driver, is_popup=False)
    qt_driver.selected = [0]
    qt_driver.frame_content = [entry]
    qt_driver.item_thumbs = [Mock()]

    # When
    tag = library.tags[0]
    # check the entry doesnt have the tag yet
    assert tag.id not in {x.id for x in entry.tags}
    add_callable = panel.add_entries_tag(tag)
    add_callable()

    # Then
    entry = next(library.get_entries(with_joins=True))
    assert tag.id in {x.id for x in entry.tags}
