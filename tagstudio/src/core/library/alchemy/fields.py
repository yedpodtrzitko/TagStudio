from __future__ import annotations

import datetime
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Union, Any

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

if TYPE_CHECKING:
    from .models import Entry, Tag

Field = Union["TextField", "TagBoxField", "DatetimeField"]
FieldType = Union["TextFieldTypes", "TagBoxTypes", "DateTimeTypes"]


class TextFieldTypes(Enum):
    text_line = "Text Line"
    text_box = "Text Box"


class TagBoxTypes(Enum):
    meta_tag_box = "Meta Tags"
    tag_box = "Tags"
    tag_content_box = "Content Tags"


class DateTimeTypes(Enum):
    datetime = "Datetime"


class TextField(Base):
    __tablename__ = "text_fields"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    type: Mapped[TextFieldTypes]

    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id"))
    entry: Mapped["Entry"] = relationship()

    value: Mapped[str | None]
    name: Mapped[str]

    def __init__(
        self,
        name: str,
        type,
        value: str | None = None,
        entry: Entry | None = None,
        entry_id: int | None = None,
    ):
        self.name = name
        self.type = type
        self.value = value
        self.entry_id = entry_id

        if entry:
            self.entry = entry
        super().__init__()

    def __key(self):
        return (self.type, self.name, self.value)

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, value: object) -> bool:
        if isinstance(value, TextField):
            return self.__key() == value.__key()
        elif isinstance(value, TagBoxField):
            return False
        elif isinstance(value, DatetimeField):
            return False
        raise NotImplementedError


class TagBoxField(Base):
    __tablename__ = "tag_box_fields"
    __table_args__ = (UniqueConstraint("entry_id", "type", name="uq_entry_id_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[TagBoxTypes] = mapped_column(default=TagBoxTypes.tag_box)

    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id"))
    entry: Mapped[Entry] = relationship(foreign_keys=[entry_id])

    tags: Mapped[set[Tag]] = relationship(secondary="tag_fields")
    name: Mapped[str]
    # TODO - implement this
    order: Mapped[int] = mapped_column(default=0)  # position in the list

    def __init__(
        self,
        name: str,
        tags: set[Tag] | None = None,
        entry: Entry | None = None,
        entry_id=entry_id,
        type=TagBoxTypes.tag_box,
    ):
        self.name = name
        self.tags = tags or set()
        self.type = type
        self.entry_id = entry_id

        if entry:
            self.entry = entry
        super().__init__()

    def __key(self):
        # tags are not bound to session, dont show them
        return (
            self.id,
            self.type,
            self.name,
        )  # str(self.tag_ids))

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, value: object) -> bool:
        if isinstance(value, TagBoxField):
            return self.__key() == value.__key()
        raise NotImplementedError


class DatetimeField(Base):
    __tablename__ = "datetime_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[DateTimeTypes]

    entry_id: Mapped[int] = mapped_column(ForeignKey("entries.id"))
    entry: Mapped[Entry] = relationship()

    value: Mapped[datetime.datetime | None]
    name: Mapped[str]

    def __init__(
        self,
        name: str,
        value: datetime.datetime | None = None,
        entry: Entry | None = None,
        entry_id: int | None = None,
        type=DateTimeTypes.datetime,
    ):
        self.name = name
        self.type = type
        self.value = value

        self.entry_id = entry_id

        if entry:
            self.entry = entry
        super().__init__()

    def __key(self):
        return (self.type, self.name, self.value)

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, value: object) -> bool:
        if isinstance(value, DatetimeField):
            return self.__key() == value.__key()
        raise NotImplementedError


@dataclass
class DefaultField:
    id: int
    name: str
    class_: Any
    type: TextFieldTypes | TagBoxTypes | DateTimeTypes


class DefaultFields(Enum):
    TITLE = DefaultField(
        id=0, name="Title", class_=TextField, type=TextFieldTypes.text_line
    )
    AUTHOR = DefaultField(
        id=1, name="Author", class_=TextField, type=TextFieldTypes.text_line
    )
    ARTIST = DefaultField(
        id=2, name="Artist", class_=TextField, type=TextFieldTypes.text_line
    )
    GUEST_ARTIST = DefaultField(
        id=3, name="Guest Artist", class_=TextField, type=TextFieldTypes.text_line
    )
    COMPOSER = DefaultField(
        id=4, name="Composer", class_=TextField, type=TextFieldTypes.text_line
    )
    URL = DefaultField(
        id=5, name="URL", class_=TextField, type=TextFieldTypes.text_line
    )
    SOURCE = DefaultField(
        id=6, name="Source", class_=TextField, type=TextFieldTypes.text_line
    )
    PUBLISHER = DefaultField(
        id=7, name="Publisher", class_=TextField, type=TextFieldTypes.text_line
    )
    DESCRIPTION = DefaultField(
        id=8, name="Description", class_=TextField, type=TextFieldTypes.text_box
    )
    NOTES = DefaultField(
        id=9, name="Notes", class_=TextField, type=TextFieldTypes.text_box
    )
    COMMENTS = DefaultField(
        id=10, name="Comments", class_=TextField, type=TextFieldTypes.text_box
    )
    TAGS = DefaultField(
        id=11, name="Tags", class_=TagBoxField, type=TagBoxTypes.tag_box
    )
    TAGS_CONTENT = DefaultField(
        id=12, name="Content Tags", class_=TagBoxField, type=TagBoxTypes.tag_content_box
    )
    TAGS_META = DefaultField(
        id=13, name="Meta Tags", class_=TagBoxField, type=TagBoxTypes.meta_tag_box
    )
    DATE = DefaultField(
        id=14, name="Date", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_CREATED = DefaultField(
        id=15, name="Date Created", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_MODIFIED = DefaultField(
        id=16, name="Date Modified", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_TAKEN = DefaultField(
        id=17, name="Date Taken", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_PUBLISHED = DefaultField(
        id=18, name="Date Published", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_UPLOADED = DefaultField(
        id=19, name="Date Uploaded", class_=DatetimeField, type=DateTimeTypes.datetime
    )
    DATE_RELEASED = DefaultField(
        id=20, name="Date Released", class_=DatetimeField, type=DateTimeTypes.datetime
    )
