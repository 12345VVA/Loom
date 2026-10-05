"""
工作流 Checkpoint 持久化存储工厂。
根据配置返回 MemorySaver / PostgresSaver 实例。
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_checkpointer = None


def get_checkpointer():
    """
    返回全局唯一的 LangGraph Checkpointer 实例。
    根据 WORKFLOW_CHECKPOINT_BACKEND 配置选择后端：
    - "memory": MemorySaver（进程内，仅测试/临时用途）
    - "postgres": PostgresSaver（默认，持久化生产后端）
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    backend = (settings.WORKFLOW_CHECKPOINT_BACKEND or "memory").strip().lower()

    if backend == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
        logger.info("工作流 Checkpoint 后端: MemorySaver（进程内，重启后数据丢失）")

    elif backend == "postgres":
        # PostgresSaver.from_conn_string 被 @contextmanager 装饰，
        # 返回上下文管理器而非实例，不能直接用作单例。这里用显式 Connection + setup() 建表。
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        from app.core.database import DATABASE_URL

        # DATABASE_URL 形如 postgresql+psycopg://user:pass@host/db，
        # psycopg3 的 connect 不识别 SQLAlchemy 的 +psycopg 方言后缀，需剥离为 postgresql://
        if not DATABASE_URL.startswith("postgresql+psycopg://"):
            raise ValueError(
                f"WORKFLOW_CHECKPOINT_BACKEND=postgres 要求 DATABASE_URL 为 PostgreSQL 连接串，"
                f"当前方言不匹配: {DATABASE_URL.split('://', 1)[0]}"
            )
        pg_conn_str = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        conn = Connection.connect(pg_conn_str, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        _checkpointer = PostgresSaver(conn)
        _checkpointer.setup()
        logger.info("工作流 Checkpoint 后端: PostgresSaver（已建表）")

    else:
        # 未知 backend 不再静默降级为 MemorySaver（会掩盖配置错误，导致 paused 实例重启后无法恢复）
        raise ValueError(
            f"未知的 WORKFLOW_CHECKPOINT_BACKEND 值 '{settings.WORKFLOW_CHECKPOINT_BACKEND}'，可选值：memory / postgres"
        )

    return _checkpointer


def close_checkpointer() -> None:
    """关闭 checkpointer 持有的底层连接（psycopg Connection）。

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


def delete_thread_best_effort(thread_id: str) -> bool:
    """删除指定 thread 的全部 checkpoint 数据（实例删除级联用，best-effort）。

    直接多态调用 saver 原生 delete_thread（postgres 删 checkpoints+checkpoint_blobs+
    checkpoint_writes、memory 清内存 dict），不手写 SQL。
    失败仅告警返回 False——残留 checkpoint 只占存储，无功能影响。
    """
    try:
        saver = get_checkpointer()
        delete = getattr(saver, "delete_thread", None)
        if delete is None:
            logger.warning("checkpointer 不支持 delete_thread，跳过 thread=%s", thread_id)
            return False
        delete(thread_id)
        return True
    except Exception:
        logger.warning("checkpoint 清理失败 thread=%s", thread_id, exc_info=True)
        return False


import contextlib
from collections.abc import AsyncGenerator
from typing import Any

# P0：async saver 本身每任务新建（Celery 每任务 asyncio.run 独立 event loop，而
# AsyncPostgresSaver 绑定创建时的 loop，进程级单例复用会报跨 loop 错误），但
# setup()（DDL 建表 + 迁移检查，幂等）进程级只需一次。标志守卫跳过重复执行；
# 不加 asyncio.Lock——模块级锁会绑定首个创建它的 loop，eval 并发首轮的竞态
# 最多重复执行一次幂等 setup()，无害。
_async_setup_done = False


@contextlib.asynccontextmanager
async def get_async_checkpointer() -> AsyncGenerator[Any, None]:
    """
    返回异步版本的 LangGraph Checkpointer 上下文管理器。
    用于 Celery 或其他异步执行环境，以满足 astream 等异步流的要求。
    """
    global _async_setup_done
    backend = (settings.WORKFLOW_CHECKPOINT_BACKEND or "memory").strip().lower()

    if backend == "memory":
        # MemorySaver 是同步的，但 langgraph 对其提供了宽松的异步兼容或我们可以直接包装
        # 如果新版强求 AsyncSaver，我们可以实现一个简单的包装，或看 MemorySaver 是否自带异步。
        # 事实上 MemorySaver 是安全的进程内字典，通常支持 async
        from langgraph.checkpoint.memory.aio import AsyncMemorySaver

        saver = AsyncMemorySaver()
        logger.info("工作流 Checkpoint 后端: AsyncMemorySaver")
        yield saver

    elif backend == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        from app.core.database import DATABASE_URL

        pg_conn_str = DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
        # 如果 URL 包含 asyncpg，我们需要适配 AsyncPostgresSaver。
        # AsyncPostgresSaver 默认使用 psycopg_pool，所以我们要确保 connection string 兼容
        pg_conn_str = pg_conn_str.replace("postgresql+asyncpg://", "postgresql://", 1)

        async with AsyncPostgresSaver.from_conn_string(pg_conn_str) as saver:
            if not _async_setup_done:
                await saver.setup()
                _async_setup_done = True
            logger.info("工作流 Checkpoint 后端: AsyncPostgresSaver")
            yield saver

    else:
        raise ValueError(
            f"未知的 WORKFLOW_CHECKPOINT_BACKEND 值 '{settings.WORKFLOW_CHECKPOINT_BACKEND}'，可选值：memory / postgres"
        )
