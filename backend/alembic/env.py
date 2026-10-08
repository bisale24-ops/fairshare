from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import config as app_config
from app import models  # noqa: F401  (registers tables)
from app.db import Base

cfg = context.config
if cfg.config_file_name:
    fileConfig(cfg.config_file_name)
target_metadata = Base.metadata


def run() -> None:
    url = cfg.attributes.get("url") or app_config.DATABASE_URL
    engine = create_engine(url)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run()
