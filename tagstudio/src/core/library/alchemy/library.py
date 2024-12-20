import re
import shutil
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from os import makedirs
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog
from alembic import command
from alembic.config import Config
from PIL import Image
from sqlalchemy import (
    URL,
    Engine,
    NullPool,
    and_,
    create_engine,
    delete,
    event,
    func,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    Session,
    aliased,
    contains_eager,
    make_transient,
    selectinload,
)
from src.qt.enums import ThumbSize

from ...constants import (
    BACKUP_FOLDER_NAME,
    PROJECT_ROOT,
    TAG_ARCHIVED,
    TAG_FAVORITE,
    TS_FOLDER_NOINDEX,
)
from ...enums import LibraryPrefs
from .db import make_tables
from .enums import FieldTypeEnum, FilterState, TagColor
from .fields import (
    BaseField,
    DatetimeField,
    TagBoxField,
    TextField,
    _FieldID,
)
from .joins import TagField, TagSubtag
from .models import Entry, Folder, Preferences, Tag, TagAlias, ValueType

logger = structlog.get_logger(__name__)


class MissingFieldAction(Enum):
    SKIP = 0
    CREATE = 1
    RAISE = 2


def slugify(input_string: str) -> str:
    # Convert to lowercase and normalize unicode characters
    slug = unicodedata.normalize("NFKD", input_string.lower())

    # Remove non-word characters (except hyphens and spaces)
    slug = re.sub(r"[^\w\s-]", "", slug).strip()

    # Replace spaces with hyphens
    slug = re.sub(r"[-\s]+", "-", slug)

    return slug


def get_default_tags() -> tuple[Tag, ...]:
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

    return archive_tag, favorite_tag


@dataclass(frozen=True)
class SearchResult:
    """Wrapper for search results.

    Attributes:
        total_count(int): total number of items for given query, might be different than len(items).
        items(list[Entry]): for current page (size matches filter.page_size).
    """

    total_count: int
    items: list[Entry]

    def __bool__(self) -> bool:
        """Boolean evaluation for the wrapper.

        :return: True if there are items in the result.
        """
        return self.total_count > 0

    def __len__(self) -> int:
        """Return the total number of items in the result."""
        return len(self.items)

    def __getitem__(self, index: int) -> Entry:
        """Allow to access items via index directly on the wrapper."""
        return self.items[index]

    def __iter__(self):
        return iter(self.items)


@dataclass
class LibraryStatus:
    """Keep status of library opening operation."""

    success: bool
    storage_path: Path | str | None = None
    message: str | None = None


class Library:
    """Class for the Library object, and all CRUD operations made upon it."""

    storage_path: Path | str | None = None
    engine: Engine | None

    FILENAME: str = "ts_library.sqlite"
    DATADIR: str = ".TagStudio"

    def close(self):
        if self.engine:
            self.engine.dispose()
        self.storage_path = None

    def migrate(self, db_url: str):
        config_path = PROJECT_ROOT / "alembic.ini"
        alembic_cfg = Config(str(config_path))
        alembic_cfg.set_main_option("sqlalchemy.url", db_url)
        command.upgrade(alembic_cfg, "head")

    def get_thumbnail(self, entry: Entry, size: ThumbSize) -> tuple[bool, Image.Image | None]:
        """Return thumbnail for given Entry."""
        # logger.info("get_thumbnail", entry=entry, size=size, storage_path=self.storage_path)

        if not entry or not isinstance(self.storage_path, Path):
            return False, None

        thumb_path = self.get_thumbnail_path(entry, size)
        if thumb_path.exists():
            return True, Image.open(thumb_path)

        return False, None

    def get_folder_thumbnail_path(self, folder_id: int) -> Path:
        """Return path to thumbnail for given folder."""
        assert isinstance(self.storage_path, Path)
        return self.storage_path / self.DATADIR / "thumbnails" / str(folder_id)

    def get_thumbnail_path(self, entry: Entry, size: ThumbSize) -> Path:
        """Return path to thumbnail for given Entry."""
        return self.get_folder_thumbnail_path(entry.folder_id) / size.name / f"{entry.id}.png"

    def save_thumbnail(self, entry: Entry, size: ThumbSize, image: Image.Image):
        """Save thumbnail for given Entry."""
        if not (entry and self.storage_path):
            return

        thumb_path = self.get_thumbnail_path(entry, size)
        logger.info("save_thumbnail", entry=entry, size=size, thumb_path=thumb_path)
        makedirs(thumb_path.parent, exist_ok=True)
        image.save(thumb_path)

    def init_db(self, use_migrations: bool, connection_string: URL, is_new: bool):
        logger.info(
            "initializing database",
            storage_path=self.storage_path,
            connection_string=connection_string,
            use_migrations=use_migrations,
            is_new=is_new,
        )

        if not use_migrations:
            make_tables(self.engine)
        else:
            self.migrate(connection_string.render_as_string(hide_password=False))

        if is_new:
            # tag IDs < 1000 are reserved
            # create tag and delete it to bump the autoincrement sequence
            # TODO - find a better way
            with self.engine.connect() as conn:
                conn.execute(text("INSERT INTO tags (id, name, color) VALUES (999, 'temp', 1)"))
                conn.execute(text("DELETE FROM tags WHERE id = 999"))
                conn.commit()

    def open_library(self, storage_path: Path | str, use_migrations: bool = True) -> LibraryStatus:
        if storage_path == ":memory:":
            self.storage_path = storage_path
            is_new = True
        else:
            self.storage_path = Path(storage_path) / self.DATADIR / self.FILENAME
            if is_new := not self.storage_path.exists():
                makedirs(self.storage_path.parent, exist_ok=True)
                (self.storage_path.parent / TS_FOLDER_NOINDEX).touch()
                self.storage_path.touch()

        connection_string = URL.create(
            drivername="sqlite",
            database=str(self.storage_path),
        )
        # NOTE: File-based databases should use NullPool to create new DB connection in order to
        # keep connections on separate threads, which prevents the DB files from being locked
        # even after a connection has been closed.
        # SingletonThreadPool (the default for :memory:) should still be used for in-memory DBs.
        # More info can be found on the SQLAlchemy docs:
        # https://docs.sqlalchemy.org/en/20/changelog/migration_07.html
        # Under -> sqlite-the-sqlite-dialect-now-uses-nullpool-for-file-based-databases
        poolclass = None if self.storage_path == ":memory:" else NullPool

        logger.info(
            "opening library",
            storage_path=storage_path,
            connection_string=connection_string,
            is_new=is_new,
        )

        self.engine = create_engine(connection_string, poolclass=poolclass)

        def _fk_pragma_on_connect(dbapi_con, con_record):
            dbapi_con.execute("pragma foreign_keys=ON")

        event.listen(self.engine, "connect", _fk_pragma_on_connect)

        with Session(self.engine) as session:
            self.init_db(use_migrations, connection_string, is_new)

            tags = get_default_tags()

            if is_new:
                try:
                    session.add_all(tags)
                    session.commit()
                except IntegrityError:
                    # default tags may exist already
                    logger.exception("default tags already exist")
                    session.rollback()

            for pref in LibraryPrefs:
                try:
                    session.add(Preferences(key=pref.name, value=pref.default))
                    session.commit()
                except IntegrityError:
                    logger.debug("preference already exists", pref=pref)
                    session.rollback()

            if is_new:
                for field in _FieldID:
                    try:
                        session.add(
                            ValueType(
                                key=field.name,
                                name=field.value.name,
                                type=field.value.type,
                                position=field.value.id,
                                is_default=field.value.is_default,
                            )
                        )
                        session.commit()
                    except IntegrityError:
                        session.rollback()

            """
            # check if folder matching current path exists already
            self.folder = session.scalar(select(Folder).where(Folder.path == library_dir))
            if not self.folder:
                folder = Folder(
                    path=library_dir,
                    uuid=str(uuid4()),
                )
                session.add(folder)
                session.expunge(folder)

                session.commit()
                self.folder = folder
            """

        # everything is fine, set the library path
        self.storage_path = storage_path
        return LibraryStatus(success=True, storage_path=storage_path)

    @property
    def default_fields(self) -> list[BaseField]:
        with Session(self.engine) as session:
            types = session.scalars(
                select(ValueType).where(
                    # check if field is default
                    ValueType.is_default.is_(True)
                )
            )
            return [x.as_field for x in types]

    def delete_item(self, item):
        logger.info("deleting item", item=item)
        with Session(self.engine) as session:
            session.delete(item)
            session.commit()

    def remove_field_tag(self, entry: Entry, tag_id: int, field_key: str) -> bool:
        assert isinstance(field_key, str), f"field_key is {type(field_key)}"
        with Session(self.engine) as session:
            # find field matching entry and field_type
            field = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry.id,
                        TagBoxField.type_key == field_key,
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
        with Session(self.engine) as session:
            entry = session.scalar(select(Entry).where(Entry.id == entry_id))
            if not entry:
                return None
            session.expunge(entry)
            make_transient(entry)
            return entry

    def add_folder(self, path: Path | str) -> Folder | None:
        if isinstance(path, str):
            path = Path(path)

        logger.info("add_folder", path=path)

        with Session(self.engine) as session:
            folder = Folder(path=path, uuid=str(uuid4()))

            try:
                session.add(folder)
                session.commit()
            except IntegrityError:
                session.rollback()
                logger.exception("add_folder.IntegrityError")
                return None

            session.refresh(folder)
            session.expunge(folder)
            return folder

    def get_folders(self) -> list[Folder]:
        with Session(self.engine) as session:
            folders = list(session.scalars(select(Folder)))
            session.expunge_all()
            return folders

    def remove_folder(self, folder: Folder) -> bool:
        folder_id = folder.id

        with Session(self.engine) as session:
            session.delete(folder)
            try:
                session.commit()
            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return False

        try:
            thumb_path = self.get_folder_thumbnail_path(folder_id)
            logger.info("removing folder thumbnails", path=thumb_path)
            assert self.storage_path
            assert self.DATADIR

            shutil.rmtree(thumb_path)
        except Exception as e:
            logger.exception(e)

        return True

    @property
    def entries_count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count(Entry.id)))

    def get_entries(self, with_joins: bool = False) -> Iterator[Entry]:
        """Load entries without joins."""
        with Session(self.engine) as session:
            stmt = select(Entry)
            if with_joins:
                # load Entry with all joins and all tags
                stmt = (
                    stmt.outerjoin(Entry.text_fields)
                    .outerjoin(Entry.datetime_fields)
                    .outerjoin(Entry.boolean_fields)
                    .outerjoin(Entry.tag_box_fields)
                    .outerjoin(Entry.folder)
                )
                stmt = stmt.options(
                    contains_eager(Entry.text_fields),
                    contains_eager(Entry.datetime_fields),
                    contains_eager(Entry.boolean_fields),
                    contains_eager(Entry.tag_box_fields).selectinload(TagBoxField.tags),
                )

            stmt = stmt.distinct()

            entries = session.execute(stmt).scalars()
            if with_joins:
                entries = entries.unique()

            for entry in entries:
                yield entry
                session.expunge(entry)

    @property
    def tags(self) -> list[Tag]:
        with Session(self.engine) as session:
            # load all tags and join subtags
            tags_query = select(Tag).options(selectinload(Tag.subtags))
            tags = session.scalars(tags_query).unique()
            tags_list = list(tags)

            for tag in tags_list:
                session.expunge(tag)

        return list(tags_list)

    def add_entries(self, items: list[Entry]) -> list[int]:
        """Add multiple Entry records to the Library."""
        assert items

        with Session(self.engine) as session:
            # add all items

            try:
                session.add_all(items)
                session.commit()
            except IntegrityError:
                session.rollback()
                logger.exception("add_entries.IntegrityError")
                return []

            new_ids = [item.id for item in items]

            session.expunge_all()

        return new_ids

    def remove_entries(self, entry_ids: list[int]) -> None:
        """Remove Entry items matching supplied IDs from the Library."""
        with Session(self.engine) as session:
            session.query(Entry).where(Entry.id.in_(entry_ids)).delete()
            session.commit()

    def get_path_entry(self, path: Path) -> Entry | None:
        """Check if item with given path is in library already."""
        with Session(self.engine) as session:
            return session.scalar(select(Entry).where(Entry.path == path))

    def get_paths(self, glob: str | None = None) -> list[str]:
        with Session(self.engine) as session:
            paths = session.scalars(select(Entry.path)).unique()

        path_strings: list[str] = list(map(lambda x: x.as_posix(), paths))
        return path_strings

    def search_library(
        self,
        search: FilterState,
    ) -> SearchResult:
        """Filter library by search query.

        :return: number of entries matching the query and one page of results.
        """
        assert isinstance(search, FilterState)
        assert self.engine

        with Session(self.engine, expire_on_commit=False) as session:
            statement = select(Entry)

            if search.tag:
                SubtagAlias = aliased(Tag)  # noqa: N806
                statement = (
                    statement.join(Entry.tag_box_fields)
                    .join(TagBoxField.tags)
                    .outerjoin(Tag.aliases)
                    .outerjoin(SubtagAlias, Tag.subtags)
                    .where(
                        or_(
                            Tag.name.ilike(search.tag),
                            Tag.shorthand.ilike(search.tag),
                            TagAlias.name.ilike(search.tag),
                            SubtagAlias.name.ilike(search.tag),
                        )
                    )
                )
            elif search.tag_id is not None:
                statement = (
                    statement.join(Entry.tag_box_fields)
                    .join(TagBoxField.tags)
                    .where(Tag.id == search.tag_id)
                )

            elif search.id:
                statement = statement.where(Entry.id == search.id)
            elif search.name:
                statement = select(Entry).where(
                    and_(
                        Entry.path.ilike(f"%{search.name}%"),
                        # dont match directory name (ie. has following slash)
                        ~Entry.path.ilike(f"%{search.name}%/%"),
                    )
                )
            elif search.path:
                statement = statement.where(Entry.path.ilike(f"%{search.path}%"))

            extensions = self.prefs(LibraryPrefs.EXTENSION_LIST)
            is_exclude_list = self.prefs(LibraryPrefs.IS_EXCLUDE_LIST)

            if not search.id:  # if `id` is set, we don't need to filter by extensions
                if extensions and is_exclude_list:
                    statement = statement.where(Entry.suffix.notin_(extensions))
                elif extensions:
                    statement = statement.where(Entry.suffix.in_(extensions))

                if search.exclude_folders:
                    statement = statement.where(Entry.folder_id.notin_(search.exclude_folders))
                elif search.include_folders:
                    statement = statement.where(Entry.folder_id.in_(search.include_folders))

            statement = statement.options(
                selectinload(Entry.folder),
                selectinload(Entry.text_fields),
                selectinload(Entry.datetime_fields),
                selectinload(Entry.boolean_fields),
                selectinload(Entry.tag_box_fields)
                .joinedload(TagBoxField.tags)
                .options(selectinload(Tag.aliases), selectinload(Tag.subtags)),
            )

            query_count = select(func.count()).select_from(statement.alias("entries"))
            count_all: int = session.execute(query_count).scalar()

            statement = statement.limit(search.limit).offset(search.offset)

            logger.info(
                "searching library",
                filter=search,
                query_full=str(statement.compile(compile_kwargs={"literal_binds": True})),
            )

            res = SearchResult(
                total_count=count_all,
                items=list(session.scalars(statement).unique()),
            )

            session.expunge_all()

            return res

    def search_tags(
        self,
        search: FilterState,
    ) -> list[Tag]:
        """Return a list of Tag records matching the query."""
        with Session(self.engine) as session:
            query = select(Tag)
            query = query.options(
                selectinload(Tag.subtags),
                selectinload(Tag.aliases),
            ).limit(search.limit)

            if search.tag:
                query = query.where(
                    or_(
                        Tag.name.icontains(search.tag),
                        Tag.shorthand.icontains(search.tag),
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

        with Session(self.engine) as session:
            tag = session.scalar(select(Tag).where(Tag.id == tag_id))
            if tag is None:
                raise ValueError(f"No tag found with id {tag_id}.")

            subtag_ids = tag.subtag_ids

        all_subtags.update(subtag_ids)

        for sub_id in subtag_ids:
            all_subtags.update(self.get_all_child_tag_ids(sub_id))

        return list(all_subtags)

    def update_entry_path(self, entry_id: int | Entry, path: Path) -> None:
        if isinstance(entry_id, Entry):
            entry_id = entry_id.id

        with Session(self.engine) as session:
            update_stmt = (
                update(Entry)
                .where(
                    and_(
                        Entry.id == entry_id,
                    )
                )
                .values(path=path)
            )

            session.execute(update_stmt)
            session.commit()

    def remove_tag_from_field(self, tag: Tag, field: TagBoxField) -> None:
        with Session(self.engine) as session:
            field_ = session.scalars(select(TagBoxField).where(TagBoxField.id == field.id)).one()

            tag = session.scalars(select(Tag).where(Tag.id == tag.id)).one()

            field_.tags.remove(tag)
            session.add(field_)
            session.commit()

    def update_field_position(
        self,
        field_class: type[BaseField],
        field_type: str,
        entry_ids: list[int] | int,
    ):
        if isinstance(entry_ids, int):
            entry_ids = [entry_ids]

        with Session(self.engine) as session:
            for entry_id in entry_ids:
                rows = list(
                    session.scalars(
                        select(field_class)
                        .where(
                            and_(
                                field_class.entry_id == entry_id,
                                field_class.type_key == field_type,
                            )
                        )
                        .order_by(field_class.id)
                    )
                )

                # Reassign `order` starting from 0
                for index, row in enumerate(rows):
                    row.position = index
                    session.add(row)
                    session.flush()
                if rows:
                    session.commit()

    def remove_entry_field(
        self,
        field: BaseField,
        entry_ids: list[int],
    ) -> None:
        FieldClass = type(field)  # noqa: N806

        logger.info(
            "remove_entry_field",
            field=field,
            entry_ids=entry_ids,
            field_type=field.type,
            cls=FieldClass,
            pos=field.position,
        )

        with Session(self.engine) as session:
            # remove all fields matching entry and field_type
            delete_stmt = delete(FieldClass).where(
                and_(
                    FieldClass.position == field.position,
                    FieldClass.type_key == field.type_key,
                    FieldClass.entry_id.in_(entry_ids),
                )
            )

            session.execute(delete_stmt)

            session.commit()

        # recalculate the remaining positions
        # self.update_field_position(type(field), field.type, entry_ids)

    def update_entry_field(
        self,
        entry_ids: list[int] | int,
        field: BaseField,
        content: str | datetime | set[Tag],
    ):
        if isinstance(entry_ids, int):
            entry_ids = [entry_ids]

        FieldClass = type(field)  # noqa: N806

        with Session(self.engine) as session:
            update_stmt = (
                update(FieldClass)
                .where(
                    and_(
                        FieldClass.position == field.position,
                        FieldClass.type == field.type,
                        FieldClass.entry_id.in_(entry_ids),
                    )
                )
                .values(value=content)
            )

            session.execute(update_stmt)
            session.commit()

    @property
    def field_types(self) -> dict[str, ValueType]:
        with Session(self.engine) as session:
            return {x.key: x for x in session.scalars(select(ValueType)).all()}

    def get_value_type(self, field_key: str) -> ValueType:
        with Session(self.engine) as session:
            field = session.scalar(select(ValueType).where(ValueType.key == field_key))
            session.expunge(field)
            return field

    def add_entry_field_type(
        self,
        entry_ids: list[int] | int,
        *,
        field: ValueType | None = None,
        field_id: _FieldID | str | None = None,
        value: str | datetime | list[str] | None = None,
    ) -> bool:
        logger.info(
            "add_field_to_entry",
            entry_ids=entry_ids,
            field_type=field,
            field_id=field_id,
            value=value,
        )
        # supply only instance or ID, not both
        assert bool(field) != (field_id is not None)

        if isinstance(entry_ids, int):
            entry_ids = [entry_ids]

        if not field:
            if isinstance(field_id, _FieldID):
                field_id = field_id.name
            field = self.get_value_type(field_id)

        field_model: TextField | DatetimeField | TagBoxField
        if field.type in (FieldTypeEnum.TEXT_LINE, FieldTypeEnum.TEXT_BOX):
            field_model = TextField(
                type_key=field.key,
                value=value or "",
            )
        elif field.type == FieldTypeEnum.TAGS:
            field_model = TagBoxField(
                type_key=field.key,
            )

            if value:
                assert isinstance(value, list)
                for tag in value:
                    field_model.tags.add(Tag(name=tag))

        elif field.type == FieldTypeEnum.DATETIME:
            field_model = DatetimeField(
                type_key=field.key,
                value=value,
            )
        else:
            raise NotImplementedError(f"field type not implemented: {field.type}")

        with Session(self.engine) as session:
            try:
                for entry_id in entry_ids:
                    field_model.entry_id = entry_id
                    session.add(field_model)
                    session.flush()

                session.commit()
            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return False
                # TODO - trigger error signal

        # recalculate the positions of fields
        self.update_field_position(
            field_class=type(field_model),
            field_type=field.key,
            entry_ids=entry_ids,
        )
        return True

    def add_tag(
        self,
        tag: Tag,
        subtag_ids: set[int] | None = None,
        alias_names: set[str] | None = None,
        alias_ids: set[int] | None = None,
    ) -> Tag | None:
        with Session(self.engine, expire_on_commit=False) as session:
            try:
                session.add(tag)
                session.flush()

                if subtag_ids is not None:
                    self.update_subtags(tag, subtag_ids, session)

                if alias_ids is not None and alias_names is not None:
                    self.update_aliases(tag, alias_ids, alias_names, session)

                session.commit()

                session.expunge(tag)
                return tag

            except IntegrityError as e:
                logger.exception(e)
                session.rollback()
                return None

    def add_field_tag(
        self,
        entry: Entry,
        tag: Tag,
        field_key: str | None = None,
        missing_field: MissingFieldAction = MissingFieldAction.SKIP,
    ) -> bool:
        field_key = field_key or _FieldID.TAGS.name

        with Session(self.engine) as session:
            # find field matching entry and field_type
            field = session.scalars(
                select(TagBoxField).where(
                    and_(
                        TagBoxField.entry_id == entry.id,
                        TagBoxField.type_key == field_key,
                    )
                )
            ).first()

            if not field:
                if missing_field == MissingFieldAction.SKIP:
                    logger.error("no field found", entry=entry, field_key=field_key)
                    return False
                elif missing_field == MissingFieldAction.RAISE:
                    raise ValueError(f"Field not found for entry {entry.id} and key {field_key}")

            try:
                if not field:
                    field = TagBoxField(
                        type_key=field_key,
                        entry_id=entry.id,
                        position=0,
                    )
                    session.add(field)
                    session.flush()

                # create record for `TagField` table
                if not tag.id:
                    session.add(tag)
                    session.flush()

                tag_field = TagField(
                    tag_id=tag.id,
                    field_id=field.id,
                )

                session.add(tag_field)
                session.commit()
                logger.info("tag added to field", tag=tag, field=field, entry_id=entry.id)

                return True
            except IntegrityError as e:
                logger.exception(e)
                session.rollback()

                return False

    def save_library_backup_to_disk(self) -> Path:
        assert isinstance(self.storage_path, Path)
        makedirs(str(self.storage_path / BACKUP_FOLDER_NAME), exist_ok=True)

        filename = f'ts_library_backup_{datetime.now(UTC).strftime("%Y_%m_%d_%H%M%S")}.sqlite'

        target_path = self.storage_path / self.DATADIR / BACKUP_FOLDER_NAME / filename

        shutil.copy2(
            self.storage_path / self.DATADIR / self.FILENAME,
            target_path,
        )

        return target_path

    def get_tag(self, tag_id: int) -> Tag:
        with Session(self.engine) as session:
            tags_query = select(Tag).options(selectinload(Tag.subtags), selectinload(Tag.aliases))
            tag = session.scalar(tags_query.where(Tag.id == tag_id))

            session.expunge(tag)
            for subtag in tag.subtags:
                session.expunge(subtag)

            for alias in tag.aliases:
                session.expunge(alias)

        return tag

    def get_alias(self, tag_id: int, alias_id: int) -> TagAlias:
        with Session(self.engine) as session:
            alias_query = select(TagAlias).where(TagAlias.id == alias_id, TagAlias.tag_id == tag_id)
            alias = session.scalar(alias_query.where(TagAlias.id == alias_id))

        return alias

    def add_subtag(self, base_id: int, new_tag_id: int) -> bool:
        if base_id == new_tag_id:
            return False

        # open session and save as parent tag
        with Session(self.engine) as session:
            subtag = TagSubtag(
                parent_id=base_id,
                child_id=new_tag_id,
            )

            try:
                session.add(subtag)
                session.commit()
                return True
            except IntegrityError:
                session.rollback()
                logger.exception("IntegrityError")
                return False

    def remove_subtag(self, base_id: int, remove_tag_id: int) -> bool:
        with Session(self.engine) as session:
            p_id = base_id
            r_id = remove_tag_id
            remove = session.query(TagSubtag).filter_by(parent_id=p_id, child_id=r_id).one()
            session.delete(remove)
            session.commit()

        return True

    def update_tag(
        self,
        tag: Tag,
        subtag_ids: set[int] | None = None,
        alias_names: set[str] | None = None,
        alias_ids: set[int] | None = None,
    ) -> None:
        """Edit a Tag in the Library."""
        self.add_tag(tag, subtag_ids, alias_names, alias_ids)

    def update_aliases(self, tag, alias_ids, alias_names, session):
        prev_aliases = session.scalars(select(TagAlias).where(TagAlias.tag_id == tag.id)).all()

        for alias in prev_aliases:
            if alias.id not in alias_ids or alias.name not in alias_names:
                session.delete(alias)
            else:
                alias_ids.remove(alias.id)
                alias_names.remove(alias.name)

        for alias_name in alias_names:
            alias = TagAlias(alias_name, tag.id)
            session.add(alias)

    def update_subtags(self, tag, subtag_ids, session):
        if tag.id in subtag_ids:
            subtag_ids.remove(tag.id)

        # load all tag's subtag to know which to remove
        prev_subtags = session.scalars(select(TagSubtag).where(TagSubtag.parent_id == tag.id)).all()

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

    def prefs(self, key: LibraryPrefs) -> Any:
        # load given item from Preferences table
        with Session(self.engine) as session:
            return session.scalar(select(Preferences).where(Preferences.key == key.name)).value

    def set_prefs(self, key: LibraryPrefs, value: Any) -> None:
        # set given item in Preferences table
        with Session(self.engine) as session:
            # load existing preference and update value
            pref = session.scalar(select(Preferences).where(Preferences.key == key.name))
            pref.value = value
            session.add(pref)
            session.commit()
            # TODO - try/except

    def mirror_entry_fields(self, *entries: Entry) -> None:
        """Mirror fields among multiple Entry items."""
        fields = {}
        # load all fields
        existing_fields = {field.type_key for field in entries[0].fields}
        for entry in entries:
            for entry_field in entry.fields:
                fields[entry_field.type_key] = entry_field

        # assign the field to all entries
        for entry in entries:
            for field_key, field in fields.items():
                if field_key not in existing_fields:
                    self.add_entry_field_type(
                        entry_ids=entry.id,
                        field_id=field.type_key,
                        value=field.value,
                    )
