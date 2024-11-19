import io
from pathlib import Path

import pytest
from src.qt.thumbnailers.epub import EpubThumbnail
from src.qt.thumbnailers.image import ImageThumbnail
from src.qt.thumbnailers.image_vector import SVGThumbnail
from src.qt.thumbnailers.opendoc import OpendocThumbnail
from src.qt.thumbnailers.pdf import PDFThumbnail
from syrupy.extensions.image import PNGImageSnapshotExtension


@pytest.mark.parametrize(
    ["fixture_file", "thumbnailer"],
    [
        (
            "sample.pdf",
            PDFThumbnail,
        ),
        (
            "sample.png",
            ImageThumbnail,
        ),
        (
            "sample.svg",
            SVGThumbnail,
        ),
        (
            "sample.odt",
            OpendocThumbnail,
        ),
        (
            "sample.ods",
            OpendocThumbnail,
        ),
        (
            "sample.epub",
            EpubThumbnail,
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
