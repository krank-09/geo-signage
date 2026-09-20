import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


log = logging.getLogger("database")


def sync_schema() -> None:
    """Create missing tables and add missing columns/indexes to existing ones.

    There are no migrations, so a database created by an older version is upgraded in place. Only additive changes
    are handled (new nullable columns, new tables, new indexes); anything else still needs a reset.
    """
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(dialect=engine.dialect)}'
                    conn.execute(text(ddl))
                    log.info("Schema upgrade: added %s.%s", table.name, col.name)
            for index in table.indexes:
                index.create(conn, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
