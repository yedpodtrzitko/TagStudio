import pytest

from src.core.library import ItemType
from src.qt.widgets.item_thumb import ItemThumb


@pytest.mark.parametrize("toggle_value", (True, False))
def test_toggle_favorite(qtbot, qt_driver, toggle_value):
    # panel = PreviewPanel(qt_driver.lib, qt_driver)

    entry = qt_driver.lib.entries[0]

    qt_driver.frame_content = [entry]
    qt_driver.selected = [0]

    thumb = ItemThumb(ItemType.ENTRY, qt_driver.lib, qt_driver, (100, 100))

    qtbot.addWidget(thumb)

    thumb.on_favorite_check(toggle_value)

    # reload entry
    entry = qt_driver.lib.entries[0]

    # check entry has favorite tag in meta tags field
    assert entry.is_favorited == toggle_value
