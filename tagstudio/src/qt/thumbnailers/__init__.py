from pathlib import Path
from typing import Type

from src.qt.thumbnailers._base import ThumbnailBase


def fill_registry() -> dict[str, Type[ThumbnailBase]]:
    from . import dummy, image, pdf

    registry = {}

    for module in (image, pdf, dummy):
        for ext in module.THUMBNAILER.EXTENSIONS:
            registry[ext] = module.THUMBNAILER

    return registry


def get_thumbnailer(filepath: Path) -> Type[ThumbnailBase]:
    ext_lower = filepath.suffix.lstrip(".").lower()
    thumbnailer = REGISTRY.get(ext_lower)
    if not thumbnailer:
        thumbnailer = REGISTRY.get("__DUMMY__")
    return thumbnailer


REGISTRY: dict[str, Type[ThumbnailBase]] = fill_registry()
