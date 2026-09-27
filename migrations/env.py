from alembic import context
from sqlalchemy import create_engine, pool

from bill_lens.db.config import database_url
from bill_lens.db.models import Base


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata,
                      compare_type=True, compare_server_default=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=database_url(), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    migrate(context.config.attributes["connection"])
else:
    engine = create_engine(database_url(), poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()
