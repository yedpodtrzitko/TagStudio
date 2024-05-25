import datetime
import logging
import time
from pathlib import Path
from typing import Iterator, Literal

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ...core.constants import BACKUP_FOLDER_NAME, COLLAGE_FOLDER_NAME, TS_FOLDER_NAME
from ...core.json_typing import JsonTag
from .db import make_engine, make_tables
from .enums import EntrySearchResult, SearchResult, TagColor, TagInfo
from .fields import (
    DEFAULT_FIELDS,
    DatetimeField,
    Field,
    TagBoxField,
    TagBoxTypes,
    TextField,
)
from .models import Entry, Tag, TagAlias
from .queries import path_in_db

LIBRARY_FILENAME: str = "ts_library.sqlite"

logger = logging.getLogger(__name__)


def get_library_defaults() -> list[Tag]:
    archive_tag = Tag(
        name="Archived",
        aliases={TagAlias(name="Archive")},
        color=TagColor.red,
    )

    favorite_tag = Tag(
        name="Favorite",
        aliases={
            TagAlias(name="Favorited"),
            TagAlias(name="Favorites"),
        },
        color=TagColor.yellow,
    )

    return [archive_tag, favorite_tag]


class Library:
    """Class for the Library object, and all CRUD operations made upon it."""

    # Cache common tags
    __favorite_tag = None
    __archived_tag = None

    @property
    def entries(self) -> list[Entry]:
        with Session(self.engine) as session, session.begin():
            entries = list(session.scalars(select(Entry)).all())
            session.expunge_all()
        return entries

    @property
    def tags(self) -> list[Tag]:
        with Session(self.engine) as session, session.begin():
            tags = list(session.scalars(select(Tag)).all())
            session.expunge_all()
        return tags

    @property
    def archived_tag(self) -> Tag:
        if self.__archived_tag is None:
            with Session(self.engine) as session, session.begin():
                tag = session.scalars(select(Tag).where(Tag.name == "Archived")).one()
                session.expunge(tag)
            self.__archived_tag = tag
        return self.__archived_tag

    @property
    def favorite_tag(self) -> Tag:
        if self.__favorite_tag is None:
            with Session(self.engine) as session, session.begin():
                tag = session.scalars(select(Tag).where(Tag.name == "Favorite")).one()
                session.expunge(tag)
            self.__favorite_tag = tag
        return self.__favorite_tag

    def __init__(self) -> None:
        # Library Info =========================================================
        self.library_dir: Path | None = None
        # Collations ===========================================================
        # List of every Collation object.
        self.collations: list = []
        # File Interfacing =====================================================
        self.dir_file_count: int = -1
        self.files_not_in_library: list[str] = []
        self.missing_files: list[str] = []
        self.dupe_files: list[tuple[str, str, int]] = []
        self.filename_to_entry_id_map: dict[str, int] = {}
        self.default_ext_blacklist: list[str] = ["json", "xmp", "aae"]
        self.ignored_extensions: list[str] = self.default_ext_blacklist

    def save_library_to_disk(self):
        logger.error("to be implemented")

    def create_library(self, path: str | Path) -> bool:
        """Creates an SQLite DB at path.
        Args:
            path (str): Path for database
        Returns:
            bool: True if created, False if error.
        """

        if isinstance(path, str):
            path = Path(path)

        # If '.TagStudio' is the name, raise path by one.
        if TS_FOLDER_NAME == path.name:
            path = path.parent

        try:
            self.clear_internal_vars()
            self.library_dir = path
            self.verify_ts_folders()

            connection_string = f"sqlite:///{path / TS_FOLDER_NAME / LIBRARY_FILENAME}"
            self.engine = make_engine(connection_string=connection_string)
            make_tables(engine=self.engine)

            session = Session(self.engine)
            with session.begin():
                session.add_all(get_library_defaults())

        except Exception as e:
            logger.exception(e)
            return False

        return True

    def verify_ts_folders(self) -> None:
        """Verifies/creates folders required by TagStudio."""

        if self.library_dir is None:
            raise ValueError("No path set.")

        full_ts_path = self.library_dir / TS_FOLDER_NAME
        full_backup_path = full_ts_path / BACKUP_FOLDER_NAME
        full_collage_path = full_ts_path / COLLAGE_FOLDER_NAME

        for path in [full_ts_path, full_backup_path, full_collage_path]:
            if not path.exists() and not path.is_dir():
                path.mkdir(parents=True, exist_ok=True)

    def verify_default_tags(self, tag_list: list[JsonTag]) -> list[JsonTag]:
        """
        Ensures that the default builtin tags  are present in the Library's
        save file. Takes in and returns the tag dictionary from the JSON file.
        """
        missing: list[JsonTag] = []

        for m in missing:
            tag_list.append(m)

        return tag_list

    def open_library(self, path: str | Path) -> bool:
        """Opens an SQLite DB at path.
        Args:
            path (str): Path for database
        Returns:
            bool: True if exists/opened, False if not.
        """
        if isinstance(path, str):
            path = Path(path)

        # If '.TagStudio' is the name, raise path by one.
        if TS_FOLDER_NAME == path.name:
            path = path.parent

        sqlite_path = path / TS_FOLDER_NAME / LIBRARY_FILENAME

        if sqlite_path.exists() and sqlite_path.is_file():
            # TODO - dry with "create_library()"
            logging.info(f"[LIBRARY] Opening Library {sqlite_path}")
            connection_string = f"sqlite:///{sqlite_path}"
            self.engine = make_engine(connection_string=connection_string)
            make_tables(engine=self.engine)
            self.library_dir = path

            return True
        else:
            logging.info("[LIBRARY] Creating Library")
            return self.create_library(path=path)

    def clear_internal_vars(self):
        """Clears the internal variables of the Library object."""
        self.library_dir = None
        self.missing_matches = {}
        self.dir_file_count = -1
        self.files_not_in_library.clear()
        self.missing_files.clear()
        self.filename_to_entry_id_map = {}
        self.ignored_extensions = self.default_ext_blacklist

    def refresh_dir(self) -> Iterator[int]:
        """Scans a directory for files, and adds those relative filenames to internal variables."""

        if self.library_dir is None:
            raise ValueError("No library path set.")

        self.dir_file_count = 0

        # Scans the directory for files, keeping track of:
        #   - Total file count
        start_time = time.time()
        for path in self.library_dir.glob("**/*"):
            str_path = str(path)
            if (
                not path.is_dir()
                and "$RECYCLE.BIN" not in str_path
                and TS_FOLDER_NAME not in str_path
                and "tagstudio_thumbs" not in str_path
            ):
                suffix = path.suffix.lower()
                if suffix != "" and suffix[0] == ".":
                    suffix = suffix[1:]

                if suffix not in self.ignored_extensions:
                    self.dir_file_count += 1

                    relative_path = path.relative_to(self.library_dir)
                    if not path_in_db(path=relative_path, engine=self.engine):
                        self.add_entry_to_library(entry=Entry(path=relative_path))

            end_time = time.time()
            # Yield output every 1/30 of a second
            if (end_time - start_time) > 0.034:
                yield self.dir_file_count
                start_time = time.time()

    def refresh_missing_files(self) -> Iterator[int]:
        """Tracks the number of Entries that point to an invalid file path."""
        self.missing_files.clear()

        if self.library_dir is None:
            raise ValueError("No library path set.")

        for i, entry in enumerate(self.entries):
            full_path = self.library_dir / entry.path
            if not full_path.exists() or not full_path.is_file():
                self.missing_files.append(str(full_path))
            yield i

    def remove_entry(self, entry_id: int) -> None:
        """Removes an Entry from the Library."""

        with Session(self.engine) as session, session.begin():
            entry = session.scalar(select(Entry).where(Entry.id == entry_id))
            if entry is None:
                raise ValueError("")
            session.delete(entry)

    # TODO
    def refresh_dupe_entries(self):
        """
        Refreshes the list of duplicate Entries.
        A duplicate Entry is defined as an Entry pointing to a file that one or more
        other Entries are also pointing to.\n
        `dupe_entries = tuple(int, list[int])`
        """
        pass

    # TODO
    def merge_dupe_entries(self):
        """
        Merges duplicate Entries.
        A duplicate Entry is defined as an Entry pointing to a file that one or more
        other Entries are also pointing to.\n
        `dupe_entries = tuple(int, list[int])`
        """
        pass

    # TODO
    def refresh_dupe_files(self):
        """
        Refreshes the list of duplicate files.
        A duplicate file is defined as an identical or near-identical file as determined
        by a DupeGuru results file.
        """
        pass

    # TODO
    def remove_missing_files(self):
        pass

    # TODO
    def remove_missing_matches(self, fixed_indices: list[int]):
        pass

    # TODO
    def fix_missing_files(self):
        """
        Attempts to repair Entries that point to invalid file paths.
        """

        pass

    # TODO
    def _match_missing_file(self, file: str) -> list[str]:
        """
        Tries to find missing entry files within the library directory.
        Works if files were just moved to different subfolders and don't have duplicate names.
        """

        # self.refresh_missing_files()

        matches = [""]

        return matches

    # TODO
    def count_tag_entry_refs(self) -> None:
        """
        Counts the number of entry references for each tag. Stores results
        in `tag_entry_ref_map`.
        """
        pass

    def add_entry_to_library(self, entry: Entry) -> int:
        with Session(self.engine) as session, session.begin():
            session.add(entry)
            session.flush()
            id = entry.id
        return id

    def add_new_files_as_entries(self) -> list[int]:
        """Adds files from the `files_not_in_library` list to the Library as Entries. Returns list of added indices."""
        new_ids: list[int] = []
        for file in self.files_not_in_library:
            path = Path(file)
            # print(os.path.split(file))
            entry = Entry(
                path=path.parent,
            )
            self.add_entry_to_library(entry)
            new_ids.append(entry.id)
        # self._map_filenames_to_entry_ids()
        return new_ids

    def get_entry(self, entry_id: int) -> Entry:
        """Returns an Entry object given an Entry ID."""
        with Session(self.engine) as session, session.begin():
            entry = session.scalar(select(Entry).where(Entry.id == entry_id))
            session.expunge(entry)

        if entry is None:
            raise ValueError(f"Entry with id {entry_id} not found.")

        return entry

    def get_entry_and_fields(self, entry_id: int) -> Entry:
        """Returns an Entry object given an Entry ID."""
        with Session(self.engine) as session, session.begin():
            entry = session.scalars(
                select(Entry).where(Entry.id == entry_id).limit(1)
            ).one()

            _ = entry.fields
            for tag in entry.tags:
                tag.subtags
                tag.alias_strings

            session.expunge_all()

        return entry

    def get_collation(self, collation_id: int):
        """Returns a Collation object given an Collation ID."""
        return self.collations[self._collation_id_to_index_map[int(collation_id)]]

    # TODO
    def search_library(
        self,
        query: str | None = None,
        entries: bool = True,
        collations: bool = True,
        tag_groups: bool = True,
    ) -> list[SearchResult]:
        """
        Uses a search query to generate a filtered results list.
        Returns a list of SearchResult.
        """
        if not hasattr(self, "engine"):
            return []

        results: list[SearchResult] = []
        with Session(self.engine) as session, session.begin():
            statement = select(Entry)

            if query:
                tag_id: int | None = None

                if "tag_id:" in query:
                    potential_tag_id = query.split(":")[-1].strip()
                    if potential_tag_id.isdigit():
                        tag_id = int(potential_tag_id)
                    statement = (
                        statement.join(Entry.tag_box_fields)
                        .join(TagBoxField.tags)
                        .where(Tag.id == tag_id)
                    )
                elif ":" not in query:
                    # for now assume plain string is tag
                    tag_value = query.strip()
                    # check if Tag.name or Tag.shorthand matches the tag_value
                    statement = (
                        statement.join(Entry.tag_box_fields)
                        .join(TagBoxField.tags)
                        .where(or_(Tag.name == tag_value, Tag.shorthand == tag_value))
                    )
                else:
                    statement = statement.where(Entry.path.like(f"%{query}%"))

            entries_ = session.scalars(statement)

            for entry in entries_:
                results.append(
                    EntrySearchResult(
                        id=entry.id,
                        path=entry.path,
                        favorited=entry.favorited,
                        archived=entry.archived,
                    )
                )

        return results

    # TODO
    def search_tags(
        self,
        query: str,
        include_cluster: bool = False,
        ignore_builtin: bool = False,
        threshold: int = 1,
        context: list[str] | None = None,
    ) -> list[Tag]:
        """Returns a list of Tag IDs returned from a string query."""

        return self.tags

    def get_all_child_tag_ids(self, tag_id: int) -> list[int]:
        """Recursively traverse a Tag's subtags and return a list of all children tags."""

        all_subtags: set[int] = {tag_id}

        with Session(self.engine) as session, session.begin():
            tag = session.scalar(select(Tag).where(Tag.id == tag_id))
            if tag is None:
                raise ValueError(f"No tag found with id {tag_id}.")

            subtag_ids = tag.subtag_ids

        all_subtags.update(subtag_ids)

        for sub_id in subtag_ids:
            all_subtags.update(self.get_all_child_tag_ids(sub_id))

        return list(all_subtags)

    # TODO
    def filter_field_templates(self, query: str) -> list[int]:
        """Returns a list of Field Template IDs returned from a string query."""

        matches: list[int] = []

        return matches

    def update_tag(self, tag_info: TagInfo) -> None:
        """
        Edits a Tag in the Library.
        This function undoes and redos the following parts of the 'add_tag_to_library()' process:\n
        - Un-maps the old Tag name, shorthand, and aliases from the Tag ID
        and re-maps the new strings to its ID via '_map_tag_names_to_tag_id()'.\n
        - Un
        """

        with Session(self.engine) as session, session.begin():
            tag_to_update = session.scalars(
                select(Tag).where(Tag.id == tag_info.id)
            ).one()

            tag_to_update.name = tag_info.name
            tag_to_update.shorthand = tag_info.shorthand
            tag_to_update.color = tag_info.color
            tag_to_update.icon = tag_info.icon

            for old_alias in tag_to_update.aliases:
                session.delete(old_alias)

            tag_to_update.aliases = set(
                [TagAlias(name=name) for name in tag_info.aliases]
            )

            subtags = session.scalars(
                select(Tag).where(Tag.id.in_(tag_info.subtag_ids))
            ).all()
            parent_tags = session.scalars(
                select(Tag).where(Tag.id.in_(tag_info.parent_tag_ids))
            ).all()

            tag_to_update.subtags.clear()
            tag_to_update.subtags.update(subtags)

            tag_to_update.parent_tags.clear()
            tag_to_update.parent_tags.update(parent_tags)

            session.add(tag_to_update)
            session.commit()
            session.close_all()

    # TODO
    def remove_tag(self, tag_id: int) -> None:
        """
        Removes a Tag from the Library.
        Disconnects it from all internal lists and maps, then remaps others as needed.
        """
        pass

    def update_entry_path(self, entry: int | Entry, path: str) -> None:
        if isinstance(entry, Entry):
            entry = entry.id

        with Session(self.engine) as session, session.begin():
            entry_object = session.scalars(select(Entry).where(Entry.id == entry)).one()

            entry_object.path = Path(path)

    def add_generic_data_to_entry(self):
        raise NotImplementedError

    def remove_tag_from_field(self, tag: Tag, field: TagBoxField) -> None:
        with Session(self.engine) as session, session.begin():
            field_ = session.scalars(
                select(TagBoxField).where(TagBoxField.id == field.id)
            ).one()

            tag = session.scalars(select(Tag).where(Tag.id == tag.id)).one()

            field_.tags.remove(tag)

    def remove_field(
        self,
        field: Field,
        entry_ids: list[int],
    ) -> None:
        with Session(self.engine) as session, session.begin():
            fields = session.scalars(
                select(field.__class__).where(
                    and_(
                        field.__class__.name == field.name,
                        field.__class__.entry_id.in_(entry_ids),
                    )
                )
            )

            for field_ in fields:
                session.delete(field_)

    def update_field(
        self,
        field: Field,
        content: str | datetime.datetime | set[Tag],
        entry_ids: list[int],
        mode: Literal["replace", "append", "remove"],
    ):
        with Session(self.engine) as session, session.begin():
            fields = session.scalars(
                select(field.__class__).where(
                    and_(
                        field.__class__.name == field.name,
                        field.__class__.entry_id.in_(entry_ids),
                    )
                )
            )
            for field_ in fields:
                if mode == "replace":
                    field_.value = content
                else:
                    raise NotImplementedError

    def add_field_to_entry(self, entry_id: int, field_id: int) -> None:
        with Session(self.engine) as session, session.begin():
            entry = session.scalars(select(Entry).where(Entry.id == entry_id)).one()

            default_field = DEFAULT_FIELDS[field_id]
            if default_field.class_ == TextField:
                entry.text_fields.append(
                    TextField(
                        name=default_field.name, type=default_field.type_, value=""
                    )
                )
            elif default_field.class_ == TagBoxField:
                entry.tag_box_fields.append(
                    TagBoxField(name=default_field.name, type=default_field.type_)
                )
            elif default_field.class_ == DatetimeField:
                entry.datetime_fields.append(
                    DatetimeField(name=default_field.name, type=default_field.type_)
                )
            else:
                raise ValueError("Unknown field.")

    def get_field_from_stale(self, stale_field: Field, session: Session) -> Field:
        return session.scalars(
            select(stale_field.__class__).where(
                stale_field.__class__.id == stale_field.id
            )
        ).one()

    def create_tag(self, tag_info: TagInfo) -> None:
        with Session(self.engine) as session, session.begin():
            subtags = set(
                session.scalars(
                    select(Tag).where(Tag.id.in_(tag_info.subtag_ids))
                ).all()
            )
            parent_tags = set(
                session.scalars(
                    select(Tag).where(Tag.id.in_(tag_info.parent_tag_ids))
                ).all()
            )

            session.add(
                Tag(
                    name=tag_info.name,
                    shorthand=tag_info.shorthand,
                    aliases=set([TagAlias(name=name) for name in tag_info.aliases]),
                    parent_tags=parent_tags,
                    subtags=subtags,
                    color=tag_info.color,
                    icon=tag_info.icon,
                )
            )

    def get_tag(
        self,
        tag: int | Tag,
        with_subtags: bool = False,
        with_parents: bool = False,
        with_aliases: bool = False,
    ) -> Tag:
        if isinstance(tag, Tag):
            tag = tag.id

        with Session(self.engine) as session, session.begin():
            tag_object = session.scalars(select(Tag).where(Tag.id == tag)).one()

            if with_subtags:
                _ = tag_object.subtags

            if with_parents:
                _ = tag_object.parent_tags

            if with_aliases:
                _ = tag_object.aliases
                _ = tag_object.alias_strings

            session.expunge(tag_object)

        return tag_object

    def get_tag_display_name(
        self,
        tag: int | Tag,
    ) -> str:
        if isinstance(tag, Tag):
            tag = tag.id

        with Session(self.engine) as session, session.begin():
            tag_object = session.scalars(select(Tag).where(Tag.id == tag)).one()

            return tag_object.display_name

    def add_tag_to_field(
        self,
        tag: int | Tag,
        field: TagBoxField,
    ) -> None:
        if isinstance(tag, Tag):
            tag = tag.id

        with Session(self.engine) as session, session.begin():
            tag_object = session.scalars(select(Tag).where(Tag.id == tag)).one()

            field_ = session.scalars(
                select(TagBoxField).where(TagBoxField.id == field.id)
            ).one()

            field_.tags.add(tag_object)

    def add_tag_to_entry_meta_tags(self, tag: int | Tag, entry_id: int) -> None:
        if isinstance(tag, Tag):
            tag = tag.id

        with Session(self.engine) as session, session.begin():
            meta_tag_box = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry_id,
                        TagBoxField.type == TagBoxTypes.meta_tag_box,
                    )
                )
            ).one()
            tag = session.scalars(select(Tag).where(Tag.id == tag)).one()

            meta_tag_box.tags.add(tag)

    def remove_tag_from_entry_meta_tags(self, tag: int | Tag, entry_id: int) -> None:
        if isinstance(tag, Tag):
            tag = tag.id

        with Session(self.engine) as session, session.begin():
            meta_tag_box = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry_id,
                        TagBoxField.type == TagBoxTypes.meta_tag_box,
                    )
                )
            ).one()
            tag = session.scalars(select(Tag).where(Tag.id == tag)).one()

            meta_tag_box.tags.remove(tag)

    def closing_database_session(self):
        with Session(self.engine) as session, session.begin():
            return session

    def entry_archived_favorited_status(self, entry: int | Entry) -> tuple[bool, bool]:
        if isinstance(entry, Entry):
            entry = entry.id
        with Session(self.engine) as session, session.begin():
            entry_ = session.scalars(select(Entry).where(Entry.id == entry)).one()

            return (entry_.archived, entry_.favorited)

    def save_library_backup_to_disk(self, *args, **kwargs):
        logger.error("to be implemented")

    def get_field_attr(self, *args, **kwargs):
        return None
