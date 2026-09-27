from alembic.config import Config

from tests.helpers import ROOT


def migration_config(connection):
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config
