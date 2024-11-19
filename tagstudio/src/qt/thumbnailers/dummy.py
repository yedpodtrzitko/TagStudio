from pathlib import Path

from PIL import Image

from ._base import ThumbnailBase


class DummyThumbnailer(ThumbnailBase):
    EXTENSIONS = ("__DUMMY__",)

    @classmethod
    def render(cls, filepath: Path, size):
        # return dummy image
        return Image.new("RGB", (size, size), color="#1e1e1e")


THUMBNAILER = DummyThumbnailer
