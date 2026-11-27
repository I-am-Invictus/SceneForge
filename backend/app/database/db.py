from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _enable_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def migrate_legacy_columns(target_engine=None) -> None:
    """SQLite `create_all` never adds columns to existing tables, so apply
    small, idempotent ALTERs for columns added after the initial schema."""
    target_engine = target_engine or engine
    with target_engine.begin() as conn:
        rows = conn.exec_driver_sql("PRAGMA table_info(assets)").fetchall()
        columns = {row[1] for row in rows}
        if not columns:  # table does not exist yet
            return
        if "description" not in columns:
            conn.exec_driver_sql("ALTER TABLE assets ADD COLUMN description TEXT")
        if "tags" not in columns:
            conn.exec_driver_sql("ALTER TABLE assets ADD COLUMN tags TEXT")


def init_db() -> None:
    from app import models  # noqa: F401  (register models on the metadata)

    Base.metadata.create_all(engine)
    migrate_legacy_columns(engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
