from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image
from PySide6.QtCore import QBuffer, QFile, QFileDevice, QIODeviceBase, QSizeF
from PySide6.QtGui import QImage
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions
from src.qt.helpers.image_effects import replace_transparent_pixels

from ._base import ThumbnailBase

logger = structlog.get_logger(__name__)


class PDFThumbnail(ThumbnailBase):
    EXTENSIONS = ("pdf",)

    @classmethod
    def render(cls, filepath: Path, size: int) -> Image.Image:
        file = QFile(filepath)
        success: bool = file.open(
            QIODeviceBase.OpenModeFlag.ReadOnly, QFileDevice.Permission.ReadUser
        )
        if not success:
            logger.error("Couldn't render thumbnail", filepath=filepath)
            return None

        document = QPdfDocument()
        document.load(file)
        # Transform page_size in points to pixels with proper aspect ratio
        page_size: QSizeF = document.pagePointSize(0)
        ratio_hw: float = page_size.height() / page_size.width()
        if ratio_hw >= 1:
            page_size *= size / page_size.height()
        else:
            page_size *= size / page_size.width()
        # Enlarge image for antialiasing
        scale_factor = 2.5
        page_size *= scale_factor
        # Render image with no anti-aliasing for speed
        render_options = QPdfDocumentRenderOptions()
        render_options.setRenderFlags(
            QPdfDocumentRenderOptions.RenderFlag.TextAliased
            | QPdfDocumentRenderOptions.RenderFlag.ImageAliased
            | QPdfDocumentRenderOptions.RenderFlag.PathAliased
        )
        # Convert QImage to PIL Image
        qimage: QImage = document.render(0, page_size.toSize(), render_options)
        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.ReadWrite)
        try:
            qimage.save(buffer, "PNG")
            im = Image.open(BytesIO(buffer.buffer().data()))
            # Replace transparent pixels with white (otherwise Background defaults to transparent)
            return replace_transparent_pixels(im)
        finally:
            buffer.close()


THUMBNAILER = PDFThumbnail
