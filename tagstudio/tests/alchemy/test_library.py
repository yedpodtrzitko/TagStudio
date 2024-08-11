import random
import string
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.core.library.alchemy import Entry
from src.core.library.alchemy import Library
from src.core.library.alchemy.enums import FilterState
from src.core.library.alchemy.fields import DEFAULT_FIELDS


def generate_entry(*, path: Path = None) -> Entry:
    if not path:
        # TODO - be sure no collision happens
        name = "".join(random.choices(string.ascii_lowercase, k=10))
        path = Path(name)

    return Entry(
        path=path,
    )


@pytest.mark.skip
def test_library_bootstrap():
    with TemporaryDirectory() as tmp_dir:
        lib = Library()
        lib.open_library(tmp_dir)
        assert lib.engine


def test_library_add_file():
    """Check Entry.path handling for insert vs lookup"""
    with TemporaryDirectory() as tmp_dir:
        # create file in tmp_dir
        file_path = Path(tmp_dir) / "bar.txt"
        file_path.write_text("bar")

        entry = Entry(path=file_path)

        lib = Library()
        lib.open_library(tmp_dir)
        assert not lib.has_item(entry.path)

        assert lib.add_entries([entry])

        assert lib.has_item(entry.path)


def test_create_tag(library, generate_tag):
    # tag already exists
    assert not library.add_tag(generate_tag("foo"))

    # new tag name
    assert library.add_tag(generate_tag("xxx"))


def test_library_search(library, generate_tag):
    entries = library.entries
    assert len(entries) == 2, entries
    tag = next(iter(entries[0].tags))

    query_count, items = library.search_library(
        FilterState(
            name=tag.name,
        ),
    )

    assert query_count == 1
    assert len(items) == 1

    entry = items[0]
    assert {x.name for x in entry.tags} == {
        "foo",
    }

    assert entry.tag_box_fields


def test_tag_search(library):
    tag = library.tags[0]

    assert library.search_tags(
        FilterState(name=tag.name),
    )
    assert not library.search_tags(
        FilterState(name=tag.name * 2),
    )


@pytest.mark.parametrize(
    ["file_path", "exists"],
    [
        (Path("foo.txt"), True),
        (Path("-----.txt"), False),
    ],
)
def test_has_item(library, file_path, exists):
    assert library.has_item(file_path) is exists, f"mismatch with item {file_path}"


def test_get_entry(library):
    entry = library.entries[0]
    assert entry.id

    _, entries = library.search_library(FilterState(id=entry.id))
    assert len(entries) == 1
    entry = entries[0]
    assert entry.path
    assert entry.tags


def test_entries_count(library):
    entries = [generate_entry() for _ in range(10)]
    library.add_entries(entries)
    matches, page = library.search_library(
        FilterState(
            page_size=5,
        )
    )

    assert matches == 12
    assert len(page) == 5


def test_add_field_to_entry(library):
    # Given
    item_path = Path("xxx")
    entry = generate_entry(path=item_path)
    # meta tags present
    assert len(entry.tag_box_fields) == 1

    library.add_entries([entry])

    # TODO - do this better way
    for field_idx, item in enumerate(DEFAULT_FIELDS):
        if item.name == "Tags":
            break

    # When
    library.add_field_to_entry(entry, field_idx)

    # Then
    entry = [x for x in library.entries if x.path == item_path][0]
    # meta tags and tags field present
    assert len(entry.tag_box_fields) == 2


def test_add_field_tag(library, generate_tag):
    # Given
    entry = library.entries[0]
    tag_name = "xxx"
    tag = generate_tag(tag_name)
    tag_field = entry.tag_box_fields[0]

    # When
    library.add_field_tag(entry, tag, tag_field.type)

    # Then
    entry = [x for x in library.entries if x.id == entry.id][0]
    tag_field = entry.tag_box_fields[0]
    assert [x.name for x in tag_field.tags if x.name == tag_name]


def test_entry_field_name(library):
    # Given
    _, entries = library.search_library(FilterState())
    tag_field = entries[0].fields[0]

    assert tag_field.name == "tag_box"
