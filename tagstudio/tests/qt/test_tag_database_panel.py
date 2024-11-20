from src.qt.modals.tag_database import TagDatabasePanel


def test_panel_tag_search(qt_driver, library):
    # Given
    panel = TagDatabasePanel(library, is_popup=False)

    # When
    tag = library.tags[0]
    panel.update_tags(tag.name)

    # Then
    assert panel.scroll_layout.count() == 1
