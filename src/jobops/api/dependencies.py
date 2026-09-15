from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.orm import Session, sessionmaker

from jobops.config import get_settings
from jobops.db import build_engine, build_session_factory


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    engine = build_engine(get_settings().database_url)
    return build_session_factory(engine)


def get_session() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
