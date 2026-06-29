"""
工作流 Checkpoint 持久化存储工厂。
根据配置返回 MemorySaver / SqliteSaver / PostgresSaver 实例。
"""

import logging
from pathlib import Path

from app.core.config import settings
from app.core.database import get_db_path

logger = logging.getLogger(__name__)

_checkpointer = None


def get_checkpointer():
    """
    返回全局唯一的 LangGraph Checkpointer 实例。
    根据 WORKFLOW_CHECKPOINT_BACKEND 配置选择后端：
    - "memory": MemorySaver（进程内，默认值）
    - "sqlite": SqliteSaver（开发环境推荐）
    - "postgres": PostgresSaver（生产环境推荐）
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    backend = (settings.WORKFLOW_CHECKPOINT_BACKEND or "memory").strip().lower()

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        logger.info("工作流 Checkpoint 后端: MemorySaver（进程内，重启后数据丢失）")

    elif backend == "sqlite":
        # 注意：SqliteSaver.from_conn_string 被 @contextmanager 装饰，返回的是上下文管理器而非
        # SqliteSaver 实例，不能直接用作单例。这里用显式构造 + setup() 建表。
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = get_db_path()
        if db_path is not None:
            checkpoint_dir = db_path.parent
        else:
            checkpoint_dir = Path("data")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / "workflow_checkpoints.db"

        # 单连接 + WAL + busy_timeout：langgraph 对同步 saver 的 async 方法会派发到线程池，
        # 故连接需跨线程可用（check_same_thread=False）并容忍并发写冲突。
        conn = sqlite3.connect(str(checkpoint_path.resolve()), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        _checkpointer = SqliteSaver(conn)
        _checkpointer.setup()  # 建检查点表（幂等）

        logger.info("工作流 Checkpoint 后端: SqliteSaver (%s)", checkpoint_path)

    elif backend == "postgres":
        # 与 sqlite 分支同理：PostgresSaver.from_conn_string 被 @contextmanager 装饰，
        # 返回上下文管理器而非实例，不能直接用作单例。这里用显式 Connection + setup() 建表。
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        from app.core.database import DATABASE_URL

        # DATABASE_URL 形如 postgresql+psycopg://user:pass@host/db，
        # psycopg3 的 connect 不识别 SQLAlchemy 的 +psycopg 方言后缀，需剥离为 postgresql://
        pg_conn_str = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        conn = Connection.connect(pg_conn_str, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        _checkpointer = PostgresSaver(conn)
        _checkpointer.setup()
        logger.info("工作流 Checkpoint 后端: PostgresSaver（已建表）")

    else:
        # 未知 backend 不再静默降级为 MemorySaver（会掩盖配置错误，导致 paused 实例重启后无法恢复）
        raise ValueError(
            f"未知的 WORKFLOW_CHECKPOINT_BACKEND 值 '{settings.WORKFLOW_CHECKPOINT_BACKEND}'，"
            "可选值：memory / sqlite / postgres"
        )

    return _checkpointer


def close_checkpointer() -> None:
    """关闭 checkpointer 持有的底层连接（sqlite3 / psycopg Connection）。

    在应用 shutdown 时调用，与 get_checkpointer 对称：启动时按配置创建单例，关闭时释放，
    避免 Connection 单例永久占用（进程结束前）。MemorySaver 无底层连接则跳过。
    """
    global _checkpointer
    saver = _checkpointer
    if saver is None:
        return
    conn = getattr(saver, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception as e:
            logger.warning("关闭 checkpointer 连接失败: %s", e)
    _checkpointer = None


import contextlib
from typing import Any, AsyncGenerator

@contextlib.asynccontextmanager
async def get_async_checkpointer() -> AsyncGenerator[Any, None]:
    """
    返回异步版本的 LangGraph Checkpointer 上下文管理器。
    用于 Celery 或其他异步执行环境，以满足 astream 等异步流的要求。
    """
    backend = (settings.WORKFLOW_CHECKPOINT_BACKEND or "memory").strip().lower()

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        # MemorySaver 是同步的，但 langgraph 对其提供了宽松的异步兼容或我们可以直接包装
        # 如果新版强求 AsyncSaver，我们可以实现一个简单的包装，或看 MemorySaver 是否自带异步。
        # 事实上 MemorySaver 是安全的进程内字典，通常支持 async
        from langgraph.checkpoint.memory.aio import AsyncMemorySaver
        saver = AsyncMemorySaver()
        logger.info("工作流 Checkpoint 后端: AsyncMemorySaver")
        yield saver

    elif backend == "sqlite":
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        db_path = get_db_path()
        if db_path is not None:
            checkpoint_dir = db_path.parent
        else:
            checkpoint_dir = Path("data")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / "workflow_checkpoints.db"

        conn_str = f"sqlite:///{checkpoint_path.resolve()}"
        async with AsyncSqliteSaver.from_conn_string(conn_str) as saver:
            await saver.setup()
            logger.info("工作流 Checkpoint 后端: AsyncSqliteSaver (%s)", checkpoint_path)
            yield saver

    elif backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from app.core.database import DATABASE_URL

        pg_conn_str = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        # 如果 URL 包含 asyncpg，我们需要适配 AsyncPostgresSaver。
        # AsyncPostgresSaver 默认使用 psycopg_pool，所以我们要确保 connection string 兼容
        pg_conn_str = pg_conn_str.replace("postgresql+asyncpg://", "postgresql://", 1)
        
        async with AsyncPostgresSaver.from_conn_string(pg_conn_str) as saver:
            await saver.setup()
            logger.info("工作流 Checkpoint 后端: AsyncPostgresSaver")
            yield saver

    else:
        raise ValueError(
            f"未知的 WORKFLOW_CHECKPOINT_BACKEND 值 '{settings.WORKFLOW_CHECKPOINT_BACKEND}'，"
            "可选值：memory / sqlite / postgres"
        )
