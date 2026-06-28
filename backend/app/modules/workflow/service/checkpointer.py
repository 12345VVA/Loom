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
