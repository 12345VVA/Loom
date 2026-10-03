from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlmodel import SQLModel

from alembic import context
from app.core.database import DATABASE_URL

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def include_object(obj, name, type_, reflected, compare_to):
    """排除 langgraph checkpoint 系表：由 PostgresSaver.setup() 自建自管，
    不在 SQLModel.metadata——否则 autogenerate/check 会把它们当多余表要求删除。"""
    if type_ == "table" and name and name.startswith("checkpoint"):
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 直接用 DATABASE_URL 构造 engine，避免 configparser 对 URL 中的百分号
    # （如密码编码 %40）做插值而抛 "invalid interpolation syntax"。
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
