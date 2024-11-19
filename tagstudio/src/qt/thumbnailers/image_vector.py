from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PySide6.QtCore import QBuffer
from PySide6.QtGui import QImage, QPainter, Qt
from PySide6.QtSvg import QSvgRenderer
from src.qt.thumbnailers import ThumbnailBase


class SVGThumbnail(ThumbnailBase):
    EXTENSIONS = ("svg",)

    @classmethod
    def render(cls, filepath: Path, size: int) -> Image.Image:
        svg = QSvgRenderer(str(filepath))
        if not svg.isValid():
            raise UnidentifiedImageError

        image = QImage(size, size, QImage.Format.Format_ARGB32)
        image.fill("#1e1e1e")

        painter: QPainter = QPainter(image)
        svg.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        svg.render(painter)
        painter.end()

        buffer = QBuffer()
        buffer.open(QBuffer.OpenModeFlag.ReadWrite)
        image.save(buffer, "PNG")

        im = Image.new("RGB", (size, size), color="#1e1e1e")
        im.paste(Image.open(BytesIO(buffer.data().data())))
        im = im.convert(mode="RGB")

        buffer.close()
        return im


THUMBNAILER = SVGThumbnail
