from pathlib import Path
from typing import Type

from src.qt.thumbnailers._base import ThumbnailBase


def fill_registry() -> dict[str, Type[ThumbnailBase]]:
    from . import dummy, image, pdf

    registry = {}

    for module in (image, pdf, dummy):
        for ext in module.Thumbnailer.EXTENSIONS:
            registry[ext] = module.Thumbnailer

    return registry


def get_thumbnailer(filepath: Path) -> Type[ThumbnailBase]:
    ext_lower = filepath.suffix.lstrip(".").lower()
    thumber = REGISTRY.get(ext_lower)
    if not thumber:
        thumber = REGISTRY.get("__DUMMY__")
    return thumber


REGISTRY: dict[str, Type[ThumbnailBase]] = fill_registry()
