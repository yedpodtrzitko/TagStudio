import sys
import pathlib
from tempfile import TemporaryDirectory
from unittest.mock import patch, Mock

import pytest
from syrupy.extensions.json import JSONSnapshotExtension

CWD = pathlib.Path(__file__).parent
# this needs to be above `src` imports
sys.path.insert(0, str(CWD.parent))

from src.core.library import Library, Tag
from src.core.library.alchemy.enums import TagColor
from src.core.library.alchemy.fields import TagBoxField, TagBoxTypes
from tests.alchemy.test_library import generate_entry
from src.core.library import alchemy as backend
from src.qt.ts_qt import QtDriver


@pytest.fixture
def snapshot_json(snapshot):
    return snapshot.with_defaults(extension_class=JSONSnapshotExtension)


@pytest.fixture
def library():
    # reset generated entries
    lib = Library()
    lib.open_library(":memory:")

    tag = Tag(
        name="foo",
        color=TagColor.RED,
    )

    tag2 = Tag(
        name="bar",
        color=TagColor.BLUE,
    )

    assert lib.add_tag(tag)

    # default item with deterministic name
    entry = generate_entry(path=pathlib.Path("foo.txt"))
    entry.tag_box_fields = [
        TagBoxField(
            name="tag_box",
            tags={tag},
        ),
        TagBoxField(
            name="meta_box",
            type=TagBoxTypes.meta_tag_box,
            # tags={tag2}
        ),
    ]

    entry2 = generate_entry(path=pathlib.Path("bar.txt"))
    entry2.tag_box_fields = [
        TagBoxField(
            name="meta_box",
            tags={tag2},
            type=TagBoxTypes.meta_tag_box,
        ),
    ]

    assert lib.add_entries([entry, entry2])
    assert len(lib.tags) == 4

    yield lib


@pytest.fixture
def qt_driver(qtbot, library):
    with TemporaryDirectory() as tmp_dir:

        class Args:
            config_file = pathlib.Path(tmp_dir) / "tagstudio.ini"
            open = pathlib.Path(tmp_dir)
            ci = True

        # patch CustomRunnable

        with patch("src.qt.ts_qt.Consumer"), patch("src.qt.ts_qt.CustomRunnable"):
            driver = QtDriver(backend, Args())

            driver.main_window = Mock()
            driver.preview_panel = Mock()
            driver.flow_container = Mock()
            driver.item_thumbs = []

            driver.lib = library
            # driver.start()
            # driver.open_library(":memory:")
            # driver.lib.add_entries([generate_entry(path=pathlib.Path("foo.txt"))])
            driver.frame_content = library.entries
            yield driver


@pytest.fixture
def generate_tag():
    def inner(name, **kwargs):
        params = dict(name=name, color=TagColor.RED) | kwargs
        return Tag(**params)

    yield inner
