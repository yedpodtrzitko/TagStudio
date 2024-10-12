import io

from src.qt.widgets.thumb_renderer import ThumbRenderer
from syrupy.extensions.image import PNGImageSnapshotExtension


def test_pdf_preview(cwd, snapshot):
    renderer = ThumbRenderer()

    pdf_path = cwd / "fixtures" / "test.pdf"

    img = renderer._pdf_thumb(pdf_path, 200)

    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    assert img_bytes.read() == snapshot(extension_class=PNGImageSnapshotExtension)
