import enum


class WindowContent(enum.Enum):
    LANDING_PAGE = 0
    LIBRARY_EMPTY = 1
    LIBRARY_CONTENT = 2


class ThumbSize(enum.IntEnum):
    MINI = 76
    SMALL = 96
    MEDIUM = 128
    LARGE = 192
    X_LARGE = 256
    XX_LARGE = 512

    @property
    def tuple(self):
        return self.value, self.value
