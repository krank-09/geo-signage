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


# Columns that used to be globally unique but are now unique per client (see the composite indexes in models.py).
LEGACY_UNIQUE_COLUMNS = {"zones": "name", "device_groups": "name"}


def _drop_legacy_unique(conn, inspector) -> None:
    """Remove the old single-column UNIQUE(name) so two clients can each have a 'Delhi Zone'."""
    from sqlalchemy.schema import CreateTable

    for table_name, column in LEGACY_UNIQUE_COLUMNS.items():
        legacy = [u for u in inspector.get_unique_constraints(table_name) if u["column_names"] == [column]]
        if engine.dialect.name == "sqlite" and not legacy:
            # The inspector misses an inline column-level UNIQUE; ask SQLite directly for unique indexes on this column.
            for _, idx_name, is_unique, *_rest in conn.execute(text(f"PRAGMA index_list({table_name})")).all():
                cols = [r[2] for r in conn.execute(text(f"PRAGMA index_info({idx_name})")).all()]
                if is_unique and cols == [column]:
                    legacy.append({"name": idx_name, "column_names": cols})
        if not legacy:
            continue
        table = Base.metadata.tables[table_name]
        if engine.dialect.name == "sqlite":
            # SQLite cannot drop a constraint: build the new table, copy the rows over, swap.
            tmp = table.to_metadata(Base.metadata, name=f"{table_name}__new")
            conn.execute(text(f"DROP TABLE IF EXISTS {tmp.name}"))
            conn.execute(CreateTable(tmp))                     # indexes are separate DDL, so none exist yet
            cols = ", ".join(c.name for c in table.columns)
            conn.execute(text(f"INSERT INTO {tmp.name} ({cols}) SELECT {cols} FROM {table_name}"))
            conn.execute(text(f"DROP TABLE {table_name}"))
            conn.execute(text(f"ALTER TABLE {tmp.name} RENAME TO {table_name}"))
            Base.metadata.remove(tmp)
        else:
            for u in legacy:
                conn.execute(text(f'ALTER TABLE {table_name} DROP CONSTRAINT "{u["name"]}"'))
        log.info("Schema upgrade: %s.%s is now unique per client instead of globally", table_name, column)


def sync_schema() -> None:
    """Create missing tables and add missing columns/indexes to existing ones.

    There are no migrations, so a database created by an older version is upgraded in place: new nullable columns, new
    tables, new indexes, and the one non-additive change the multi-client model needs (zone/group names unique per
    client). Anything beyond that still needs a reset.
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
    with engine.begin() as conn:
        _drop_legacy_unique(conn, inspect(conn))
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                index.create(conn, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
