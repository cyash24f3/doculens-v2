from alembic import context
from sqlalchemy import create_engine

from doculens.config import Settings
from doculens.storage.models import Base


def run():
    engine = create_engine((context.config.attributes.get("settings") or Settings()).database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
