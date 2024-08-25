from src.core.library.alchemy.fields import TagBoxTypes, TextFieldTypes
from src.qt.widgets.preview_panel import PreviewPanel


def test_update_widgets(qt_driver, library):
    assert len(library.entries) == 2

    qt_driver.selected = [0, 1]

    panel = PreviewPanel(library, qt_driver)
    panel.update_widgets()

    assert {f.type for f in panel.common_fields} == {
        TagBoxTypes.meta_tag_box,
        TextFieldTypes.text_line,
    }

    assert {f.type for f in panel.mixed_fields} == {
        TagBoxTypes.tag_box,
    }


def test_write_container(qt_driver, library):
    panel = PreviewPanel(library, qt_driver)

    entry = library.entries[0]

    for field in entry.fields:
        if field.type == TextFieldTypes.text_line:
            panel.write_container(0, field)
            modal = panel.containers[0].modal
            modal.save_button.click()


def test_update_field(qt_driver, library):
    panel = PreviewPanel(library, qt_driver)

    qt_driver.frame_content = library.entries[:2]
    qt_driver.selected = [0, 1]
    panel.selected = [0, 1]

    field = [
        x for x in library.entries[0].fields if x.type == TextFieldTypes.text_line
    ][0]

    panel.update_field(field, "meow")

    for entry_idx in (0, 1):
        field = [
            x
            for x in library.entries[entry_idx].fields
            if x.type == TextFieldTypes.text_line
        ][0]
        assert field.value == "meow"
