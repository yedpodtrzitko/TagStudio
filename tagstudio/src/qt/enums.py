import enum


class WindowContent(enum.Enum):
    LANDING_PAGE = 0
    LIBRARY_EMPTY = 1
    LIBRARY_CONTENT = 2


class ThumbSize(enum.Enum):
    MEDIUM = (256, 256)
    LARGE = (512, 512)
