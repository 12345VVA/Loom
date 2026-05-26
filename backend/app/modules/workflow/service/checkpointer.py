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
        from langgraph.checkpoint.sqlite import SqliteSaver

        db_path = get_db_path()
        if db_path is not None:
            checkpoint_dir = db_path.parent
        else:
            checkpoint_dir = Path("data")
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / "workflow_checkpoints.db"

        conn_string = f"sqlite:///{checkpoint_path.resolve().as_posix()}"
        _checkpointer = SqliteSaver.from_conn_string(conn_string)

        # 启用 WAL 模式以支持并发读写
        import sqlite3

        raw_conn = sqlite3.connect(str(checkpoint_path.resolve()))
        try:
            raw_conn.execute("PRAGMA journal_mode=WAL")
        finally:
            raw_conn.close()

        logger.info("工作流 Checkpoint 后端: SqliteSaver (%s)", checkpoint_path)

    elif backend == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver
        from app.core.database import DATABASE_URL

        _checkpointer = PostgresSaver.from_conn_string(DATABASE_URL)
        _checkpointer.setup()
        logger.info("工作流 Checkpoint 后端: PostgresSaver（已建表）")

    else:
        from langgraph.checkpoint.memory import MemorySaver

        logger.warning(
            "未知的 WORKFLOW_CHECKPOINT_BACKEND 值 '%s'，已回退为 MemorySaver",
            settings.WORKFLOW_CHECKPOINT_BACKEND,
        )
        _checkpointer = MemorySaver()

    return _checkpointer
