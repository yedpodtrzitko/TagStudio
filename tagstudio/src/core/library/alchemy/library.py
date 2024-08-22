import datetime
import time
from pathlib import Path
from typing import Iterator, Literal, Any

import structlog
from sqlalchemy import and_, or_, select, create_engine, Engine, func
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.orm import (
    Session,
    contains_eager,
    selectinload,
    make_transient,
)

from .db import make_tables
from .enums import TagColor, FilterState
from .fields import (
    DatetimeField,
    Field,
    TagBoxField,
    TagBoxTypes,
    TextField,
    DefaultFields,
    DefaultField,
)
from .joins import TagSubtag, TagField
from .models import Entry, Preferences, Tag, TagAlias
from ...constants import LibraryPrefs, TS_FOLDER_NAME, TAG_ARCHIVED, TAG_FAVORITE

LIBRARY_FILENAME: str = "ts_library.sqlite"

logger = structlog.get_logger(__name__)

import re
import unicodedata


def slugify(input_string: str) -> str:
    # Convert to lowercase and normalize unicode characters
    slug = unicodedata.normalize("NFKD", input_string.lower())

    # Remove non-word characters (except hyphens and spaces)
    slug = re.sub(r"[^\w\s-]", "", slug).strip()

    # Replace spaces with hyphens
    slug = re.sub(r"[-\s]+", "-", slug)

    return slug


def get_default_tags() -> list[Tag]:
    archive_tag = Tag(
        id=TAG_ARCHIVED,
        name="Archived",
        aliases={TagAlias(name="Archive")},
        color=TagColor.RED,
    )

    favorite_tag = Tag(
        id=TAG_FAVORITE,
        name="Favorite",
        aliases={
            TagAlias(name="Favorited"),
            TagAlias(name="Favorites"),
        },
        color=TagColor.YELLOW,
    )

    return [archive_tag, favorite_tag]


class Library:
    """Class for the Library object, and all CRUD operations made upon it."""

    library_dir: Path | str
    missing_files: list[str]
    dupe_files: list[str]
    engine: Engine | None
    dupe_entries: list[Entry]  # TODO

    def __init__(self):
        self.clear_internal_vars()

    def open_library(self, library_dir: Path | str) -> None:
        self.clear_internal_vars()

        if library_dir == ":memory:":
            connection_string = f"sqlite:///{library_dir}"
            self.library_dir = library_dir
        else:
            self.library_dir = Path(library_dir)
            self.verify_ts_folders(self.library_dir)

            connection_string = (
                f"sqlite:///{self.library_dir / TS_FOLDER_NAME / LIBRARY_FILENAME}"
            )

        logger.info("opening library", connection_string=connection_string)
        self.engine = create_engine(connection_string)
        with Session(self.engine) as session:
            make_tables(self.engine)

            tags = get_default_tags()
            try:
                session.add_all(tags)
                session.commit()
            except IntegrityError:
                # default tags may exist already
                session.rollback()

            for pref in LibraryPrefs:
                try:
                    session.add(Preferences(key=pref.name, value=pref.value))
                    session.commit()
                except IntegrityError:
                    logger.error("pref already exists", pref=pref)
                    session.rollback()

    def delete_item(self, item):
        logger.info("deleting item", item=item)
        with Session(self.engine) as session:
            session.delete(item)
            session.commit()

    def remove_field_tag(self, entry: Entry, tag_id: int, field_type: TagBoxTypes):
        with Session(self.engine) as session:
            # find field matching entry and field_type
            field = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry.id,
                        TagBoxField.type == field_type,
                    )
                )
            ).first()

            if not field:
                logger.error("no field found", entry=entry, field=field)
                return False

            try:
                # find the record in `TagField` table and delete it
                tag_field = session.scalars(
                    select(TagField).where(
                        and_(
                            TagField.tag_id == tag_id,
                            TagField.field_id == field.id,
                        )
                    )
                ).first()
                if tag_field:
                    session.delete(tag_field)
                    session.commit()
                    return True
            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return False

    def get_entry(self, entry_id: int) -> Entry | None:
        """Load entry without joins."""
        with Session(self.engine) as session, session.begin():
            entry = session.scalar(select(Entry).where(Entry.id == entry_id))
            if not entry:
                return None
            session.expunge(entry)
            make_transient(entry)
            return entry

    @property
    def entries(self) -> list[Entry]:
        """Load all entries with joins.
        Debugging purposes only.
        """
        with Session(self.engine) as session:
            stmt = (
                select(Entry)
                .outerjoin(Entry.text_fields)
                .outerjoin(Entry.datetime_fields)
                .outerjoin(Entry.tag_box_fields)
                .options(
                    contains_eager(Entry.text_fields),
                    contains_eager(Entry.datetime_fields),
                    contains_eager(Entry.tag_box_fields).selectinload(TagBoxField.tags),
                )
                .distinct()
            )

            entries = session.execute(stmt).scalars().unique().all()

            session.expunge_all()

            return list(entries)

    @property
    def tags(self) -> list[Tag]:
        with Session(self.engine) as session, session.begin():
            # load all tags and join subtags
            tags_query = select(Tag).options(selectinload(Tag.subtags))
            tags = session.scalars(tags_query).unique()
            tags_list = list(tags)

            for tag in tags_list:
                session.expunge(tag)
                for subtag in tag.subtags:
                    session.expunge(subtag)

        return list(tags_list)

    def save_library_to_disk(self):
        logger.error("save_library_to_disk to be implemented")

    def verify_ts_folders(self, library_dir: Path) -> None:
        """Verify/create folders required by TagStudio."""
        if library_dir is None:
            raise ValueError("No path set.")

        if not library_dir.exists():
            raise ValueError("Invalid library directory.")

        full_ts_path = library_dir / TS_FOLDER_NAME
        if not full_ts_path.exists():
            logger.info("creating library directory", dir=full_ts_path)
            full_ts_path.mkdir(parents=True, exist_ok=True)

    def verify_default_tags(self, tag_list: list) -> list:
        """
        Ensure that the default builtin tags  are present in the Library's
        save file. Takes in and returns the tag dictionary from the JSON file.
        """
        missing: list = []

        for m in missing:
            tag_list.append(m)

        return tag_list

    def clear_internal_vars(self):
        """Clear the internal variables of the Library object."""
        self.library_dir = None
        self.missing_files = []
        self.dupe_files = []
        self.ignored_extensions = []
        self.missing_matches = {}

    def refresh_dir(self) -> Iterator[int]:
        """Scan a directory for files, and add those relative filenames to internal variables."""
        if self.library_dir is None:
            raise ValueError("No library path set.")

        # Scans the directory for files, keeping track of:
        #   - Total file count
        start_time = time.time()
        self.files_not_in_library: list[Path] = []
        self.dir_file_count = 0

        assert isinstance(self.library_dir, Path)
        for path in self.library_dir.glob("**/*"):
            str_path = str(path)
            if (
                path.is_dir()
                or "$RECYCLE.BIN" in str_path
                or TS_FOLDER_NAME in str_path
                or "tagstudio_thumbs" in str_path
            ):
                continue

            suffix = path.suffix.lower().lstrip(".")
            if suffix in self.ignored_extensions:
                continue

            self.dir_file_count += 1
            relative_path = path.relative_to(self.library_dir)
            # TODO - load these in batch somehow
            if not self.has_item(path=relative_path):
                logger.info("item not in library yet", path=relative_path)
                self.files_not_in_library.append(relative_path)

            end_time = time.time()
            # Yield output every 1/30 of a second
            if (end_time - start_time) > 0.034:
                yield self.dir_file_count

    def has_item(self, path: Path) -> bool:
        """Check if item with given path is in library already."""
        with Session(self.engine) as session, session.begin():
            # check if item with given path is in the database
            query = select(Entry).where(Entry.path == path)
            res = session.scalar(query)
            logger.debug(
                "check item presence",
                # query=str(query),
                path=path,
                present=bool(res),
            )
            return bool(res)

    def add_entries(self, items: list[Entry]) -> list[int]:
        """Add multiple Entry records to the Library."""
        if not items:
            return []

        with Session(self.engine) as session, session.begin():
            # add all items
            session.add_all(items)
            session.flush()

            new_ids = [item.id for item in items]

            session.expunge_all()

            session.commit()

        return new_ids

    def refresh_missing_files(self) -> Iterator[int]:
        """Track the number of Entries that point to an invalid file path."""
        self.missing_files.clear()

        if self.library_dir is None:
            raise ValueError("No library path set.")

        for i, entry in enumerate(self.entries):
            full_path = self.library_dir / entry.path
            if not full_path.exists() or not full_path.is_file():
                self.missing_files.append(str(full_path))
            yield i

    def remove_entry(self, entry_id: int) -> None:
        """Remove an Entry from the Library."""
        with Session(self.engine) as session, session.begin():
            entry = session.scalar(select(Entry).where(Entry.id == entry_id))
            if entry is None:
                raise ValueError("")
            session.delete(entry)

    def add_new_files_as_entries(self) -> list[int]:
        """Add files from the `files_not_in_library` list to the Library as Entries. Returns list of added indices."""
        entries = []
        for path in self.files_not_in_library:
            entries.append(
                Entry(
                    path=path,
                )
            )

        return self.add_entries(entries)

    def search_library(
        self,
        search: FilterState,
    ) -> tuple[int, list[Entry]]:
        """Filter library by search query.

        :return: number of entries matching the query and one page of results.
        """
        assert isinstance(search, FilterState)
        assert self.engine

        with Session(self.engine, expire_on_commit=False) as session:
            statement = select(Entry)

            if search.name:
                statement = (
                    statement.join(Entry.tag_box_fields)
                    .join(TagBoxField.tags)
                    .where(
                        or_(
                            Tag.name == search.name,
                            Tag.shorthand == search.name,
                        )
                    )
                )

            elif search.id:
                statement = statement.where(Entry.id == search.id)
            elif search.tag_id:
                # TODO
                statement = statement.where(Tag.id == search.tag_id)

            extensions = self.prefs(LibraryPrefs.EXTENSION_LIST)
            is_exclude_list = self.prefs(LibraryPrefs.IS_EXCLUDE_LIST)
            if extensions and is_exclude_list:
                statement = statement.where(
                    Entry.path.notilike(f"%.{','.join(extensions)}")
                )
            elif extensions:
                statement = statement.where(
                    Entry.path.ilike(f"%.{','.join(extensions)}")
                )

            statement = statement.options(
                selectinload(Entry.text_fields),
                selectinload(Entry.datetime_fields),
                selectinload(Entry.tag_box_fields)
                .joinedload(TagBoxField.tags)
                .options(selectinload(Tag.aliases), selectinload(Tag.subtags)),
            )

            query_count = select(func.count()).select_from(statement.alias("entries"))
            count_all: int = session.execute(query_count).scalar()

            # ADD limit and offset
            statement = statement.limit(search.limit).offset(search.offset)

            logger.info(
                "searching library",
                filter=search,
                query_full=str(
                    statement.compile(compile_kwargs={"literal_binds": True})
                ),
            )

            entries_ = list(session.scalars(statement).unique())

            [make_transient(x) for x in entries_]  # type: ignore
            session.expunge_all()

            return count_all, list(entries_)

    def search_tags(
        self,
        search: FilterState,
    ) -> list[Tag]:
        """Return a list of Tag records matching the query."""

        with Session(self.engine) as session, session.begin():
            query = select(Tag)
            query = query.options(
                selectinload(Tag.subtags),
                selectinload(Tag.aliases),
            )

            if search.name:
                query = query.where(
                    or_(
                        Tag.name == search.name,
                        Tag.shorthand == search.name,
                        # Tag.id == search.query,
                    )
                )

            tags = session.scalars(query)

            res = list(tags)

            logger.info(
                "searching tags",
                search=search,
                statement=str(query),
                results=len(res),
            )

            session.expunge_all()
            return res

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
        with Session(self.engine) as session:
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
        with Session(self.engine) as session:
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
                    # TODO
                    field_.value = content  # type: ignore
                else:
                    raise NotImplementedError

    def add_field_to_entry(
        self,
        entry: Entry,
        field_id: int | None = None,
        field: DefaultFields | None = None,
    ) -> bool:
        # TODO - improve this
        default_field: DefaultField
        if field:
            default_field = field.value
        elif field_id is not None:
            default_field = [x.value for x in DefaultFields if x.value.id == field_id][
                0
            ]
        else:
            raise ValueError("missing field identifier")

        logger.info(
            "found field type",
            entry=entry,
            field_id=field_id,
            field_type=default_field.class_,
        )

        field_model: Any  # make mypy happy
        if default_field.class_ == TextField:
            field_model = TextField(
                name=default_field.name,
                type=default_field.type,
                value="",
                entry_id=entry.id,
            )
        elif default_field.class_ == TagBoxField:
            field_model = TagBoxField(
                name=default_field.name,
                type=default_field.type,
                entry_id=entry.id,
            )
        elif default_field.class_ == DatetimeField:
            field_model = DatetimeField(
                name=default_field.name,
                type=default_field.type,
                entry_id=entry.id,
            )

        with Session(self.engine) as session:
            try:
                session.add(field_model)
                session.commit()
                return True
            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return False
                # TODO - trigger error signal

    def add_tag(self, tag: Tag, subtag_ids: list[int] | None = None) -> Tag | None:
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                session.add(tag)
                session.flush()

                for subtag_id in subtag_ids or []:
                    subtag = TagSubtag(
                        parent_id=tag.id,
                        child_id=subtag_id,
                    )
                    session.add(subtag)

                session.commit()

                session.expunge(tag)
                return tag

            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return None

    def add_field_tag(self, entry: Entry, tag: Tag, field_type: TagBoxTypes) -> bool:
        with Session(self.engine) as session:
            # find field matching entry and field_type
            field = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry.id,
                        TagBoxField.type == field_type,
                    )
                )
            ).first()

            if not field:
                logger.error("no field found", entry=entry, field_type=field_type)
                return False

            try:
                field.tags = field.tags | {tag}
                session.add(field)
                session.commit()
                return True
            except InvalidRequestError as e:
                logger.exception(e)
                session.rollback()
                return False

    def save_library_backup_to_disk(self, *args, **kwargs):
        logger.error("save_library_backup_to_disk to be implemented")

    def get_tag(self, tag_id: int) -> Tag:
        with Session(self.engine) as session:
            tags_query = select(Tag).options(selectinload(Tag.subtags))
            tag = session.scalar(tags_query.where(Tag.id == tag_id))

            session.expunge(tag)
            for subtag in tag.subtags:
                session.expunge(subtag)

        return tag

    def add_subtag(self, base_id: int, new_tag_id: int) -> bool:
        # open session and save as parent tag
        with Session(self.engine) as session:
            tag = TagSubtag(
                parent_id=base_id,
                child_id=new_tag_id,
            )

            try:
                session.add(tag)
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                logger.exception("IntegrityError")
                return False

    def update_tag(self, tag: Tag, subtag_ids: list[int]) -> None:
        """
        Edit a Tag in the Library.
        """
        # TODO - maybe merge this with add_tag?

        if tag.shorthand:
            tag.shorthand = slugify(tag.shorthand)

        if tag.aliases:
            # TODO
            ...

        # save the tag
        with Session(self.engine) as session:
            try:
                # update the existing tag
                session.add(tag)
                session.flush()

                # load all tag's subtag to know which to remove
                prev_subtags = session.scalars(
                    select(TagSubtag).where(TagSubtag.parent_id == tag.id)
                ).all()

                for subtag in prev_subtags:
                    if subtag.child_id not in subtag_ids:
                        session.delete(subtag)
                    else:
                        # no change, remove from list
                        subtag_ids.remove(subtag.child_id)

                # create remaining items
                for subtag_id in subtag_ids:
                    # add new subtag
                    subtag = TagSubtag(
                        parent_id=tag.id,
                        child_id=subtag_id,
                    )
                    session.add(subtag)

                session.commit()
            except IntegrityError:
                session.rollback()
                logger.exception("IntegrityError")

    def refresh_dupe_entries(self, filename: str) -> None:
        logger.info("refreshing dupe entries", filename=filename)
        # TODO - implement this
        raise NotImplementedError

    def fix_missing_files(self) -> None:
        logger.error("fix_missing_files to be implemented")

    def refresh_dupe_files(self, filename: str):
        logger.error("refresh_dupe_files to be implemented")

    def remove_missing_files(self):
        logger.error("remove_missing_files to be implemented")

    def get_entry_id_from_filepath(self, item):
        logger.error("get_entry_id_from_filepath to be implemented")

    def mirror_entry_fields(self, items: list):
        logger.error("mirror_entry_fields to be implemented")

    def merge_dupe_entries(self):
        logger.error("merge_dupe_entries to be implemented")

    def prefs(self, key: LibraryPrefs) -> Any:
        # load given item from Preferences table
        with Session(self.engine) as session:
            return session.scalar(
                select(Preferences).where(Preferences.key == key.name)
            ).value

    def set_prefs(self, key: LibraryPrefs, value: Any) -> None:
        # set given item in Preferences table
        with Session(self.engine) as session:
            # load existing preference and update value
            pref = session.scalar(
                select(Preferences).where(Preferences.key == key.name)
            )
            pref.value = value
            session.add(pref)
            session.commit()
            # TODO - try/except
