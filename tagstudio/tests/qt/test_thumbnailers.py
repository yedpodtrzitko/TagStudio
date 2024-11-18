# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

import io
from pathlib import Path

import pytest
from src.qt.thumbnailers.image import Thumbnailer as ImageThumbnailer
from src.qt.thumbnailers.pdf import Thumbnailer as PDFThumbnailer
from syrupy.extensions.image import PNGImageSnapshotExtension


@pytest.mark.parametrize(
    ["fixture_file", "thumbnailer"],
    [
        (
            "sample.pdf",
            PDFThumbnailer,
        ),
        (
            "sample.png",
            ImageThumbnailer,
        ),
    ],
)
def test_preview_render(cwd, fixture_file, thumbnailer, snapshot):
    file_path: Path = cwd / "fixtures" / fixture_file
    img = thumbnailer.render(file_path, size=200)

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    assert img_bytes.read() == snapshot(extension_class=PNGImageSnapshotExtension)
