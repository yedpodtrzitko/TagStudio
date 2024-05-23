from pathlib import Path

from src.core.library import Entry


def test_entries_different():
    a = Entry(123, "foo.jpg", Path("/tmp/foo.jpg"), [])
    b = Entry(123, "bar.jpg", Path("/tmp/bar.jpg"), [])

    assert a != b


def test_entries_identical():
    a = Entry(123, "foo.jpg", Path("/tmp/foo.jpg"), [])
    b = Entry(123, "foo.jpg", Path("/tmp/foo.jpg"), [])

    assert a == b
