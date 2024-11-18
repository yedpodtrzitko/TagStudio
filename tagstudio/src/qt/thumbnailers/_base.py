from abc import ABC, abstractmethod
from pathlib import Path

from PIL.Image import Image


class ThumbnailBase(ABC):
    EXTENSIONS: tuple[str, ...] = ()

    @classmethod
    @abstractmethod
    def render(cls, filepath: Path, size) -> Image:
        raise NotImplementedError
