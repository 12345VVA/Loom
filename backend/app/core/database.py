"""
数据库配置
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import SessionTransactionOrigin
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.models.entity import BaseEntity


def _autodiscover_models() -> None:
    """自动导入 app.modules 下所有业务模块的 model，确保 metadata 收录全量表。"""
    from importlib import import_module
    from pathlib import Path

    modules_root = Path(__file__).resolve().parents[1] / "modules"
    if not modules_root.exists():
        return

    for module_dir in sorted(
        path for path in modules_root.iterdir() if path.is_dir() and not path.name.startswith("__")
    ):
        model_root = module_dir / "model"
        if not model_root.exists() or not model_root.is_dir():
            continue

        for py_file in sorted(model_root.rglob("*.py")):
            if py_file.name == "__init__.py":
                continue
            relative_parts = py_file.relative_to(model_root).with_suffix("").parts
            module_path = ".".join(("app", "modules", module_dir.name, "model", *relative_parts))
            import_module(module_path)


_autodiscover_models()


@event.listens_for(BaseEntity, "before_update", propagate=True)
def timestamp_before_update(mapper, connection, target):
    """在更新前自动刷新 updated_at 字段"""
    target.updated_at = datetime.now(UTC)


DATABASE_URL = settings.DATABASE_URL

engine_kwargs = {
    "echo": settings.db_echo_enabled,
    "pool_pre_ping": settings.DB_POOL_PRE_PING,
    "pool_size": settings.DB_POOL_SIZE,
    "max_overflow": settings.DB_MAX_OVERFLOW,
    "pool_recycle": settings.DB_POOL_RECYCLE,
}

engine = create_engine(DATABASE_URL, **engine_kwargs)


def init_db():
    """初始化数据库"""
    SQLModel.metadata.create_all(engine)
    _ensure_indexes()


@contextmanager
def SessionLocal():
    """创建独立的数据库会话（用于后台任务等无法依赖 FastAPI DI 的场景）"""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session


@contextmanager
def transaction(session: Session) -> Iterator[Session]:
    """
    统一事务上下文。

    - 显式 BEGIN（调用者主动 ``session.begin()``）：复用外层事务，由外层提交/回滚。
    - AUTOBEGIN（session 自动开启的事务）：由本上下文负责提交。修复 P1-6——此前当
      session 处于 AUTOBEGIN 且已有 pending 写入时，误判为外层工作而静默不提交，
      导致写入丢失。
    - SAVEPOINT（嵌套事务）：仅释放/回滚到最近 savepoint，不影响外层事务。
    - 无活跃事务：由本上下文开启并提交。
    """
    transaction_state = session.get_transaction()

    # 显式 BEGIN：复用外层事务，交给外层提交/回滚
    if transaction_state is not None and transaction_state.origin is SessionTransactionOrigin.BEGIN:
        yield session
        return

    is_savepoint = transaction_state is not None and transaction_state.origin is SessionTransactionOrigin.BEGIN_NESTED

    try:
        yield session
        if is_savepoint:
            # 嵌套事务：仅释放 savepoint，不提交外层事务
            transaction_state.commit()
        else:
            # AUTOBEGIN 或无事务：提交整个事务，避免 pending 写入静默丢失
            session.commit()
    except Exception:
        if is_savepoint:
            transaction_state.rollback()
        else:
            session.rollback()
        raise


# 幂等索引清单：每条 = (索引名, 表名, 列 SQL 片段, 可选 WHERE)。
# Field(index=True) 仅对 create_all 新建表生效，现有库不会自动补索引；这里为现有库补齐查询关键索引。
# 复合索引优先服务统计聚合（按时间范围扫描）与分页（keyset），单列索引由 create_all 对新表建立，此处为旧库补齐。
INDEX_DEFINITIONS: list[tuple[str, str, str, str | None]] = [
    # ai_model_call_log：统计看板/日志统计(P0-1)的主查询路径——按 created_at 范围扫描
    ("ix_ai_model_call_log_created_at", "ai_model_call_log", "created_at", None),
    ("ix_ai_model_call_log_status_created_at", "ai_model_call_log", "status, created_at", None),
    ("ix_ai_model_call_log_user_id_created_at", "ai_model_call_log", "user_id, created_at", None),
    ("ix_ai_model_call_log_model_id_created_at", "ai_model_call_log", "model_id, created_at", None),
    # media_asset：工作流产物按实例反查（资源库归属筛选 / 实例产物溯源）
    ("ix_media_asset_workflow_instance_id", "media_asset", "workflow_instance_id", None),
    # workflow_execution_log：节点日志按实例 + 时间排序/分页(T7)
    ("ix_workflow_execution_log_instance_id_created_at", "workflow_execution_log", "instance_id, created_at", None),
    # workflow_instance：实例列表按定义 + 时间查询
    ("ix_workflow_instance_definition_id_created_at", "workflow_instance", "definition_id, created_at", None),
    # workflow_eval：回归对比（同测试集按时间）与 P95 排序（同 run 按 latency）的复合索引（T9）
    ("ix_workflow_eval_run_test_set_id_created_at", "workflow_eval_run", "test_set_id, created_at", None),
    (
        "ix_workflow_eval_case_result_eval_run_id_latency_ms",
        "workflow_eval_case_result",
        "eval_run_id, latency_ms",
        None,
    ),
    ("ix_workflow_eval_case_result_eval_run_id_case_key", "workflow_eval_case_result", "eval_run_id, case_key", None),
    ("ix_workflow_eval_test_case_test_set_id_case_key", "workflow_eval_test_case", "test_set_id, case_key", None),
    # workflow_definition_version：版本历史（按定义+时间）与状态过滤（查 draft/发布版）
    (
        "ix_workflow_definition_version_definition_id_created_at",
        "workflow_definition_version",
        "definition_id, created_at",
        None,
    ),
    (
        "ix_workflow_definition_version_definition_id_status",
        "workflow_definition_version",
        "definition_id, status",
        None,
    ),
    # ai_runtime_invocation：cancel 按 task 定位 running invocation（Field(index=True) 的旧库补齐）
    ("ix_ai_runtime_invocation_task_id", "ai_runtime_invocation", "task_id", None),
]


def _ensure_indexes() -> None:
    """为现有库幂等补建查询关键索引（CREATE INDEX IF NOT EXISTS）。

    `CREATE INDEX IF NOT EXISTS` 与部分索引（WHERE 子句）为 PostgreSQL 原生支持。
    生产 PG 大表可设 SKIP_INDEX_ENSURE=True 跳过，由 DBA 在维护窗口用
    CREATE INDEX CONCURRENTLY 建立。
    """
    if settings.SKIP_INDEX_ENSURE:
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # 收集涉及的现有索引名，跳过已存在项，避免重复 DDL
    existing_indexes: set[str] = set()
    for table_name in {item[1] for item in INDEX_DEFINITIONS}:
        if table_name in existing_tables:
            for ix in inspector.get_indexes(table_name):
                if ix.get("name"):
                    existing_indexes.add(ix["name"])

    created = 0
    with engine.begin() as connection:
        for index_name, table_name, columns, where_clause in INDEX_DEFINITIONS:
            if table_name not in existing_tables:
                continue
            if index_name in existing_indexes:
                continue
            sql = f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({columns})"
            if where_clause:
                sql += f" WHERE {where_clause}"
            try:
                connection.execute(text(sql))
                created += 1
            except Exception as e:
                print(f"Failed to create index {index_name} on {table_name}: {e}")
    if created:
        print(f"[db] ensured {created} missing index(es).")
