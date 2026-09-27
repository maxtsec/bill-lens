import os

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def database_url(variable: str = "DATABASE_URL") -> str:
    value = os.environ.get(variable)
    if not value:
        raise ValueError(f"{variable} must be set")
    if make_url(value).drivername != "postgresql+psycopg":
        raise ValueError(f"{variable} must use postgresql+psycopg")
    return value


def make_engine() -> Engine:
    return create_engine(database_url(), pool_pre_ping=True, hide_parameters=True)
