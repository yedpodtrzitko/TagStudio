import enum


class SettingItems(str, enum.Enum):
    """List of setting item names."""

    START_LOAD_LAST = "start_load_last"
    LAST_LIBRARY = "last_library"
    LIBS_LIST = "libs_list"
    WINDOW_SHOW_LIBS = "window_show_libs"


class Theme(str, enum.Enum):
    COLOR_BG = "#65000000"
    COLOR_HOVER = "#65AAAAAA"
    COLOR_PRESSED = "#65EEEEEE"


class FieldID(int, enum.Enum):
    TITLE = 0
    AUTHOR = 1
    ARTIST = 2
    DESCRIPTION = 4
    NOTES = 5
    TAGS = 6
    CONTENT_TAGS = 7
    META_TAGS = 8
    DATE_PUBLISHED = 14
    SOURCE = 21
