from pathlib import Path

VERSION: str = "9.5.0"  # Major.Minor.Patch
VERSION_BRANCH: str = "EXPERIMENTAL"  # Usually "" or "Pre-Release"

# The folder & file names where TagStudio keeps its data relative to a library.
BACKUP_FOLDER_NAME: str = "backups"
COLLAGE_FOLDER_NAME: str = "collages"
TS_FOLDER_NOINDEX: str = ".ts_noindex"

FONT_SAMPLE_TEXT: str = (
    """ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!?@$%(){}[]"""
)
FONT_SAMPLE_SIZES: list[int] = [10, 15, 20]

TAG_FAVORITE = 1
TAG_ARCHIVED = 0

PROJECT_ROOT = Path(__file__).parents[2]
