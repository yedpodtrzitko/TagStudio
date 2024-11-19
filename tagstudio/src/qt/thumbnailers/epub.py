import zipfile
from io import BytesIO
from pathlib import Path

import structlog
from PIL import Image
from src.qt.thumbnailers import ThumbnailBase

logger = structlog.get_logger(__name__)


class EpubThumbnail(ThumbnailBase):
    EXTENSIONS = ("epub",)

    @classmethod
    def render(cls, filepath: Path, size) -> Image.Image | None:
        try:
            with zipfile.ZipFile(filepath, "r") as zip_file:
                for file_name in zip_file.namelist():
                    if file_name.lower().endswith(
                        (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg")
                    ):
                        image_data = zip_file.read(file_name)
                        return Image.open(BytesIO(image_data))
        except Exception as e:
            logger.error("Couldn't render thumbnail", filepath=filepath, error=e)
            # TODO - add fallback image here?

        return None


THUMBNAILER = EpubThumbnail
