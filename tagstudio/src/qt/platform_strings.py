# Copyright (C) 2024 Travis Abendshien (CyanVoxel).
# Licensed under the GPL-3.0 License.
# Created for TagStudio: https://github.com/CyanVoxel/TagStudio

"""A collection of platform-dependant strings."""

import sys


class BaseStrings:
    open_file_str = "Open in file explorer"
    keybind_open_lib = "Ctrl+O"
    keybind_new_lib = "Ctrl+N"


class MacOSStrings(BaseStrings):
    open_file_str = "Reveal in Finder"
    keybind_open_lib = "⌘+O"
    keybind_new_lib = "⌘+N"


class WindowsStrings(BaseStrings):
    open_file_str = "Open in Explorer"


def get_translation_class():
    if sys.platform == "darwin":
        return MacOSStrings
    elif sys.platform == "win32":
        return WindowsStrings

    return BaseStrings


PlatformStrings = get_translation_class()
