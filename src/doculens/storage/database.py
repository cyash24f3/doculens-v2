from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker

from doculens.config import Settings
from doculens.storage.models import Base, Workspace


class Database:
    def __init__(self, settings: Settings):
        sqlite = settings.database_url.startswith("sqlite")
        if sqlite:
            Path("var").mkdir(exist_ok=True)
        self.engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            **({"connect_args": {"check_same_thread": False, "timeout": 30}} if sqlite else {}),
        )
        if sqlite:

            @event.listens_for(self.engine, "connect")
            def connect(dbapi_connection, _):
                dbapi_connection.isolation_level = None
                dbapi_connection.execute("PRAGMA foreign_keys=ON")
                dbapi_connection.execute("PRAGMA journal_mode=WAL")

            @event.listens_for(self.engine, "begin")
            def begin(conn):
                conn.exec_driver_sql("BEGIN")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def transaction(self, write: bool = False):
        with self.sessions() as session:
            if write and self.engine.dialect.name == "sqlite":
                # Serialize writers before the first read, avoiding read-to-write upgrade races.
                session.connection().exec_driver_sql("ROLLBACK")
                session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def initialize_test_schema(self):
        # Production/CLI startup uses Alembic, never implicit schema creation.
        Base.metadata.create_all(self.engine)
        self.seed_workspaces()

    def seed_workspaces(self):
        with self.transaction(write=True) as session:
            for scope in ("sample", "private"):
                if not session.get(Workspace, scope):
                    session.add(Workspace(id=scope, revision=0))

    def lock_scope(self, session: Session, scope: str, read: bool = False) -> Workspace:
        return session.execute(
            select(Workspace).where(Workspace.id == scope).with_for_update(read=read)
        ).scalar_one()
