from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session


def path_in_db(path: Path, engine: Engine) -> bool:
    from .library import Entry

    with Session(engine) as session, session.begin():
        result = session.execute(
            select(Entry.id).where(Entry.path == path)
        ).one_or_none()

        result_bool = bool(result)

    return result_bool
