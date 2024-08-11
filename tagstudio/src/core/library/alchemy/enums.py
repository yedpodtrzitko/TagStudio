import enum
from dataclasses import dataclass


class TagColor(enum.IntEnum):
    DEFAULT = 1
    BLACK = 2
    DARK_GRAY = 3
    GRAY = 4
    LIGHT_GRAY = 5
    WHITE = 6
    LIGHT_PINK = 7
    PINK = 8
    RED = 9
    RED_ORANGE = 10
    ORANGE = 11
    YELLOW_ORANGE = 12
    YELLOW = 13
    LIME = 14
    LIGHT_GREEN = 15
    MINT = 16
    GREEN = 17
    TEAL = 18
    CYAN = 19
    LIGHT_BLUE = 20
    BLUE = 21
    BLUE_VIOLET = 22
    VIOLET = 23
    PURPLE = 24
    LAVENDER = 25
    BERRY = 26
    MAGENTA = 27
    SALMON = 28
    AUBURN = 29
    DARK_BROWN = 30
    BROWN = 31
    LIGHT_BROWN = 32
    BLONDE = 33
    PEACH = 34
    WARM_GRAY = 35
    COOL_GRAY = 36
    OLIVE = 37


class SearchMode(enum.IntEnum):
    """Operational modes for item searching."""

    AND = 0
    OR = 1


class ItemType(enum.Enum):
    ENTRY = 0
    COLLATION = 1
    TAG_GROUP = 2


@dataclass
class FilterState:
    """Represent a state of the Library grid view."""

    page_index: int = 0
    page_size: int = 100
    name: str | None = None
    id: int | None = None
    tag_id: int | None = None
    search_mode: SearchMode = SearchMode.AND  # TODO - actually implement this

    # default_search: str = "name"

    def __post_init__(self):
        # strip query automatically
        self.name = self.name and self.name.strip()
        self.id = self.id and int(self.id)
        self.tag_id = self.tag_id and int(self.tag_id)

    @property
    def summary(self) -> str | int | None:
        """Show query summary"""
        return self.name or self.id or None

    @property
    def limit(self):
        return self.page_size

    @property
    def offset(self):
        return self.page_size * self.page_index
