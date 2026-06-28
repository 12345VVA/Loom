from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

from alembic import context
from app.core.database import DATABASE_URL
from app.modules.ai.model import ai as _ai_models  # noqa: F401
from app.modules.base.model import auth as _auth_models  # noqa: F401
from app.modules.base.model import sys as _sys_models  # noqa: F401
from app.modules.dict.model import dict as _dict_models  # noqa: F401
from app.modules.media.model import media as _media_models  # noqa: F401
from app.modules.notification.model import notification as _notification_models  # noqa: F401
from app.modules.task.model import task as _task_models  # noqa: F401
from app.modules.workflow.model import workflow as _workflow_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 直接用 DATABASE_URL 构造 engine，避免 configparser 对 URL 中的百分号
    # （如密码编码 %40）做插值而抛 "invalid interpolation syntax"。
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
