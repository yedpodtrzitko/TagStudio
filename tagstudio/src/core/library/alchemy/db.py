from pathlib import Path

import structlog
from sqlalchemy import Dialect, Engine, String, TypeDecorator
from sqlalchemy.orm import DeclarativeBase

logger = structlog.getLogger(__name__)


class PathType(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value: Path, dialect: Dialect):
        if value is not None:
            return Path(value).as_posix()
        return None

    def process_result_value(self, value: str, dialect: Dialect):
        if value is not None:
            return Path(value)
        return None


class Base(DeclarativeBase):
    type_annotation_map = {Path: PathType}


def make_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
