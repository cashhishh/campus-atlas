from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL

DB_URL = DATABASE_URL
engine = create_engine(DB_URL, connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Minimal forward-only migration: add columns introduced after the first defence.

    `create_all` creates new tables but never alters existing ones, so an older
    campusatlas.db would otherwise miss the Phase 5 columns.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    ddl_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN "{column.name}" {ddl_type}'))


def init_db():
    from .models import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    from .seed import seed

    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
