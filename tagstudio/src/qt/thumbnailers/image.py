from pathlib import Path

import structlog
from PIL import Image, ImageOps

from ._base import ThumbnailBase

logger = structlog.get_logger(__name__)


class ImageThumbnail(ThumbnailBase):
    EXTENSIONS = ("jpg", "jpeg", "png", "gif", "bmp", "tiff", "webp")

    @classmethod
    def render(cls, filepath: Path, size: int) -> Image.Image:
        im = Image.open(filepath)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert(mode="RGBA")

        if im.mode == "RGBA":
            new_bg = Image.new("RGB", im.size, color="#1e1e1e")
            new_bg.paste(im, mask=im.getchannel(3))
            im = new_bg

        return ImageOps.exif_transpose(im)


THUMBNAILER = ImageThumbnail
