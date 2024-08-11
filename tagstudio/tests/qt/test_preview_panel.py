from src.core.library.alchemy.fields import TagBoxTypes
from src.qt.widgets.preview_panel import PreviewPanel


def test_update_widgets(qt_driver, library):
    assert len(library.entries) == 2

    qt_driver.selected = [0, 1]

    panel = PreviewPanel(library, qt_driver)
    panel.update_widgets()

    assert {f.type for f in panel.common_fields} == {TagBoxTypes.meta_tag_box}
    assert {f.type for f in panel.mixed_fields} == {TagBoxTypes.tag_box}
