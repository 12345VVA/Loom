"""测试公共工具：统一引擎工厂，替代各测试文件自造的 create_engine 轮子。"""

from __future__ import annotations

import os

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine


def make_test_engine(tables: list | None = None):
    """测试 engine 工厂：优先 TEST_DATABASE_URL，缺省内存 SQLite。

    缺省形态为内存库 + 单连接 StaticPool（inspect 一致性与跨线程共享的前提，
    见 .cursor/rules/testing.mdc）。tables=[...] 时仅建指定表，
    避免无关表进入测试库（如需隔离全局 metadata 的场景）。
    """
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        engine = create_engine(url, pool_pre_ping=True)
    else:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if tables:
        SQLModel.metadata.create_all(engine, tables=tables)
    return engine
