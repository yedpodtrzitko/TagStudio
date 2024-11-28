import pathlib
import sys
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pytest
import structlog

CWD = pathlib.Path(__file__).parent
# this needs to be above `src` imports
sys.path.insert(0, str(CWD.parent))

from src.core.library import Entry, Library, Tag
from src.core.library import alchemy as backend
from src.core.library.alchemy.enums import TagColor
from src.core.library.alchemy.fields import TagBoxField, _FieldID
from src.core.library.alchemy.library import MissingFieldAction
from src.qt.ts_qt import QtDriver

logger = structlog.get_logger()


@pytest.fixture
def cwd():
    return CWD


@pytest.fixture
def library(request):
    """WARNING: the library content is removed on end of the test"""
    # when no param is passed, use the default
    folder_path = "/dev/null/"
    storage_path = ":memory:"
    temp_dir = None
    if hasattr(request, "param"):
        assert isinstance(request.param, TemporaryDirectory)
        temp_dir = request.param
        storage_path = folder_path = pathlib.Path(temp_dir.name)
        # check the folder is empty
        if storage_path.exists() and list(storage_path.iterdir()):
            raise ValueError(
                f"Temporary directory {storage_path} is not empty. "
                "Please use a clean temporary directory for the test."
            )

    lib = Library()
    status = lib.open_library(storage_path, use_migrations=False)
    assert status.success

    tag = Tag(
        name="foo",
        color=TagColor.RED,
    )
    assert lib.add_tag(tag)

    subtag = Tag(
        name="subbar",
        color=TagColor.YELLOW,
    )

    tag2 = Tag(
        name="bar",
        color=TagColor.BLUE,
        subtags={subtag},
    )
    lib.add_tag(tag2)

    folder = lib.add_folder(folder_path)

    all_fields = lib.field_types
    default_fields = [
        f.as_field
        for (key, f) in all_fields.items()
        if key
        in {
            _FieldID.TITLE.name,
            _FieldID.TAGS_CONTENT.name,
            _FieldID.TAGS_META.name,
        }
    ]

    # default item with deterministic name
    entry = Entry(
        folder=folder,
        path=pathlib.Path("foo.txt"),
        fields=default_fields,
    )

    entry.tag_box_fields = [
        TagBoxField(
            type_key=_FieldID.TAGS.name,
            tags={tag},
            position=0,
        ),
        TagBoxField(
            type_key=_FieldID.TAGS_META.name,
            position=0,
        ),
    ]

    all_fields = lib.field_types
    default_fields = [
        f.as_field
        for (key, f) in all_fields.items()
        if key
        in {
            _FieldID.TITLE.name,
            _FieldID.TAGS_CONTENT.name,
            _FieldID.TAGS_META.name,
        }
    ]

    entry2 = Entry(
        folder=folder,
        path=pathlib.Path("one/two/bar.md"),
        fields=default_fields,
    )

    assert lib.add_entries([entry, entry2])
    assert lib.add_field_tag(
        entry2, tag2, _FieldID.TAGS_META.name, missing_field=MissingFieldAction.RAISE
    )
    assert len(lib.tags) == 5, lib.tags

    yield lib

    if isinstance(temp_dir, TemporaryDirectory):
        temp_dir.cleanup()


@pytest.fixture
def entry_min(library):
    yield next(library.get_entries())


@pytest.fixture
def entry_full(library):
    yield next(library.get_entries(with_joins=True))


@pytest.fixture
def qt_driver(qtbot, library):
    with TemporaryDirectory() as tmp_dir:

        class Args:
            config_file = pathlib.Path(tmp_dir) / "tagstudio.ini"
            open = pathlib.Path(tmp_dir)
            ci = True

        with patch("src.qt.ts_qt.Consumer"), patch("src.qt.ts_qt.CustomRunnable"):
            driver = QtDriver(backend, Args())

            driver.main_window = Mock()
            driver.preview_panel = Mock()
            driver.flow_container = Mock()
            driver.item_thumbs = []

            driver.lib = library
            # TODO - downsize this method and use it
            # driver.start()
            driver.frame_content = list(library.get_entries())
            yield driver


@pytest.fixture
def generate_tag():
    def inner(name, **kwargs):
        params = dict(name=name, color=TagColor.RED) | kwargs
        return Tag(**params)

    yield inner
