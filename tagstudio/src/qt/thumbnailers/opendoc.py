import zipfile
from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image
from src.qt.thumbnailers import ThumbnailBase

logger = structlog.get_logger(__name__)


class OpendocThumbnail(ThumbnailBase):
    EXTENSIONS = ("odt", "ods")

    @classmethod
    def render(cls, filepath: Path, size) -> Image.Image:
        file_path_within_zip = "Thumbnails/thumbnail.png"
        with zipfile.ZipFile(filepath, "r") as zip_file:
            if file_path_within_zip in zip_file.namelist():
                file_data = zip_file.read(file_path_within_zip)
                thumb_im = Image.open(BytesIO(file_data))
                if thumb_im:
                    im = Image.new("RGB", thumb_im.size, color="#1e1e1e")
                    im.paste(thumb_im)
            else:
                logger.error("Couldn't render thumbnail", filepath=filepath)

        return im


THUMBNAILER = OpendocThumbnail
