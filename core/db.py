from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        Path("data").mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            settings.db_url,
            connect_args={"check_same_thread": False},
        )
    return _engine


_ADDED_COLUMNS = {
    "conversation": {"base_prompt": "TEXT"},
    "designversion": {
        "design_model": "JSON",
        "revisions": "JSON",
        "instruction": "TEXT",
    },
    "diagram": {"warnings": "JSON"},
}


def _migrate(engine) -> None:
    # create_all never alters existing tables, so add new nullable columns by hand.
    with engine.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
            for name, sql_type in columns.items():
                if existing and name not in existing:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}")


def init_db() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
    Path(get_settings().cache_dir).mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _migrate(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    # expire_on_commit=False so attributes remain readable after commit
    # (Streamlit often uses ORM rows outside the session block).
    session = Session(get_engine(), expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
