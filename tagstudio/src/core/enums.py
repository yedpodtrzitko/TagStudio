import enum


class SettingItems(enum.StrEnum):
    """List of setting item names."""

    START_LOAD_LAST = "start_load_last"
    LAST_LIBRARY = "last_storage"
    LIBS_LIST = "libs_list"
    WINDOW_SHOW_LIBS = "window_show_libs"
    WINDOW_SHOW_DIRS = "window_show_dirs"
    AUTOPLAY = "autoplay_videos"


class Theme(str, enum.Enum):
    COLOR_BG = "#65000000"
    COLOR_HOVER = "#65AAAAAA"
    COLOR_PRESSED = "#65EEEEEE"
    COLOR_DISABLED = "#65F39CAA"
    COLOR_DISABLED_BG = "#65440D12"


class MacroID(enum.Enum):
    AUTOFILL = "autofill"
    SIDECAR = "sidecar"
    BUILD_URL = "build_url"
    MATCH = "match"
    CLEAN_URL = "clean_url"
