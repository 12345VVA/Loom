"""
数据库配置
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.orm import SessionTransactionOrigin
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.framework.models.entity import BaseEntity
from app.modules.ai.model import ai as _ai_models  # noqa: F401
from app.modules.base.model import auth as _base_auth_models  # noqa: F401
from app.modules.base.model import sys as _base_sys_models  # noqa: F401
from app.modules.dict.model import dict as _dict_models  # noqa: F401
from app.modules.media.model import media as _media_models  # noqa: F401
from app.modules.notification.model import notification as _notification_models  # noqa: F401
from app.modules.task.model import task as _task_models  # noqa: F401
from app.modules.workflow.model import workflow as _workflow_models  # noqa: F401
from app.modules.workflow_eval.model import eval_run as _workflow_eval_eval_run_models  # noqa: F401
from app.modules.workflow_eval.model import test_set as _workflow_eval_test_set_models  # noqa: F401


@event.listens_for(BaseEntity, "before_update", propagate=True)
def timestamp_before_update(mapper, connection, target):
    """在更新前自动刷新 updated_at 字段"""
    target.updated_at = datetime.now(timezone.utc)


BASE_DIR = Path(__file__).resolve().parents[3]


def normalize_database_url(database_url: str) -> str:
    """将 sqlite 相对路径标准化为项目根目录下的绝对路径"""
    if not database_url.startswith("sqlite:///"):
        return database_url

    raw_path = database_url.removeprefix("sqlite:///")
    db_path = Path(raw_path)
    if not db_path.is_absolute():
        db_path = BASE_DIR / raw_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.resolve().as_posix()}"


DATABASE_URL = normalize_database_url(settings.DATABASE_URL)

engine_kwargs = {
    "echo": settings.db_echo_enabled,
    "pool_pre_ping": settings.DB_POOL_PRE_PING,
}
if "sqlite" in DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
        }
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)


def init_db():
    """初始化数据库"""
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_compatible_schema()
    _ensure_indexes()


def get_db_path() -> Path | None:
    """获取数据库文件路径 (仅适用于 SQLite)"""
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL.removeprefix("sqlite:///"))


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

    已处于事务中时复用外层事务，交给外层提交/回滚；否则在当前上下文内提交或回滚。
    """
    transaction_state = session.get_transaction()
    has_pending_outer_work = bool(session.new or session.dirty or session.deleted)
    if transaction_state is not None and (
        transaction_state.origin is not SessionTransactionOrigin.AUTOBEGIN or has_pending_outer_work
    ):
        yield session
        return

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise


def _ensure_sqlite_compatible_schema() -> None:
    is_sqlite = "sqlite" in DATABASE_URL

    # standard_columns 含 sqlite 专属语法（PRIMARY KEY AUTOINCREMENT），仅 sqlite 后端补齐；
    # PG 等后端的 id/created_at 等标准字段由 create_all 建表时确定，不在此补。
    # specific_columns（下方）为 ADD COLUMN 通用语法，sqlite / pg 均补，保证旧库新增字段自动迁移。
    standard_columns = {
        "id": "ALTER TABLE {table} ADD COLUMN id INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at": "ALTER TABLE {table} ADD COLUMN created_at DATETIME",
        "updated_at": "ALTER TABLE {table} ADD COLUMN updated_at DATETIME",
        "delete_time": "ALTER TABLE {table} ADD COLUMN delete_time DATETIME",
    } if is_sqlite else {}

    # 各个表特有的缺失字段逻辑
    specific_columns = {
        "sys_role": {
            "remark": "ALTER TABLE sys_role ADD COLUMN remark VARCHAR",
        },
        "sys_menu": {
            "icon": "ALTER TABLE sys_menu ADD COLUMN icon VARCHAR",
            "keep_alive": "ALTER TABLE sys_menu ADD COLUMN keep_alive BOOLEAN DEFAULT 1",
            "is_show": "ALTER TABLE sys_menu ADD COLUMN is_show BOOLEAN DEFAULT 1",
        },
        "sys_user": {
            "nick_name": "ALTER TABLE sys_user ADD COLUMN nick_name VARCHAR",
            "head_img": "ALTER TABLE sys_user ADD COLUMN head_img VARCHAR",
            "phone": "ALTER TABLE sys_user ADD COLUMN phone VARCHAR",
            "remark": "ALTER TABLE sys_user ADD COLUMN remark VARCHAR",
            "password_version": "ALTER TABLE sys_user ADD COLUMN password_version INTEGER DEFAULT 1",
            "password_changed_at": "ALTER TABLE sys_user ADD COLUMN password_changed_at DATETIME",
        },
        "task_info": {
            "notify_enabled": "ALTER TABLE task_info ADD COLUMN notify_enabled BOOLEAN DEFAULT 0",
            "notify_on_success": "ALTER TABLE task_info ADD COLUMN notify_on_success BOOLEAN DEFAULT 0",
            "notify_on_failure": "ALTER TABLE task_info ADD COLUMN notify_on_failure BOOLEAN DEFAULT 1",
            "notify_on_timeout": "ALTER TABLE task_info ADD COLUMN notify_on_timeout BOOLEAN DEFAULT 1",
            "notify_recipients": "ALTER TABLE task_info ADD COLUMN notify_recipients VARCHAR",
            "notify_template_code": "ALTER TABLE task_info ADD COLUMN notify_template_code VARCHAR",
            "notify_timeout_ms": "ALTER TABLE task_info ADD COLUMN notify_timeout_ms INTEGER DEFAULT 30000",
        },
        "notification_message": {
            "is_recalled": "ALTER TABLE notification_message ADD COLUMN is_recalled BOOLEAN DEFAULT 0",
            "recalled_at": "ALTER TABLE notification_message ADD COLUMN recalled_at DATETIME",
            "recalled_by": "ALTER TABLE notification_message ADD COLUMN recalled_by INTEGER",
        },
        "ai_provider": {
            "api_key_cipher": "ALTER TABLE ai_provider ADD COLUMN api_key_cipher VARCHAR",
            "api_key_mask": "ALTER TABLE ai_provider ADD COLUMN api_key_mask VARCHAR",
            "sort_order": "ALTER TABLE ai_provider ADD COLUMN sort_order INTEGER DEFAULT 0",
        },
        "ai_model": {
            "sort_order": "ALTER TABLE ai_model ADD COLUMN sort_order INTEGER DEFAULT 0",
        },
        "ai_model_profile": {
            "sort_order": "ALTER TABLE ai_model_profile ADD COLUMN sort_order INTEGER DEFAULT 0",
            "timeout": "ALTER TABLE ai_model_profile ADD COLUMN timeout INTEGER",
            "retry_count": "ALTER TABLE ai_model_profile ADD COLUMN retry_count INTEGER DEFAULT 0",
            "retry_delay_seconds": "ALTER TABLE ai_model_profile ADD COLUMN retry_delay_seconds INTEGER DEFAULT 0",
        },
        "ai_model_call_log": {
            "user_id": "ALTER TABLE ai_model_call_log ADD COLUMN user_id INTEGER",
            "cost_micro_usd": "ALTER TABLE ai_model_call_log ADD COLUMN cost_micro_usd INTEGER DEFAULT 0",
            "currency": "ALTER TABLE ai_model_call_log ADD COLUMN currency VARCHAR DEFAULT 'USD'",
            "workflow_instance_id": "ALTER TABLE ai_model_call_log ADD COLUMN workflow_instance_id INTEGER",
        },
        "ai_generation_task": {
            "task_type": "ALTER TABLE ai_generation_task ADD COLUMN task_type VARCHAR DEFAULT 'chat'",
            "scenario": "ALTER TABLE ai_generation_task ADD COLUMN scenario VARCHAR DEFAULT 'default'",
            "profile_code": "ALTER TABLE ai_generation_task ADD COLUMN profile_code VARCHAR",
            "status": "ALTER TABLE ai_generation_task ADD COLUMN status VARCHAR DEFAULT 'pending'",
            "progress": "ALTER TABLE ai_generation_task ADD COLUMN progress INTEGER DEFAULT 0",
            "request_payload": "ALTER TABLE ai_generation_task ADD COLUMN request_payload VARCHAR",
            "result_payload": "ALTER TABLE ai_generation_task ADD COLUMN result_payload VARCHAR",
            "error_message": "ALTER TABLE ai_generation_task ADD COLUMN error_message VARCHAR",
            "celery_task_id": "ALTER TABLE ai_generation_task ADD COLUMN celery_task_id VARCHAR",
            "created_by": "ALTER TABLE ai_generation_task ADD COLUMN created_by INTEGER",
            "started_at": "ALTER TABLE ai_generation_task ADD COLUMN started_at DATETIME",
            "finished_at": "ALTER TABLE ai_generation_task ADD COLUMN finished_at DATETIME",
            "retry_count": "ALTER TABLE ai_generation_task ADD COLUMN retry_count INTEGER DEFAULT 0",
        },
        "ai_governance_rule": {
            "code": "ALTER TABLE ai_governance_rule ADD COLUMN code VARCHAR",
            "name": "ALTER TABLE ai_governance_rule ADD COLUMN name VARCHAR",
            "scope_type": "ALTER TABLE ai_governance_rule ADD COLUMN scope_type VARCHAR DEFAULT 'global'",
            "user_id": "ALTER TABLE ai_governance_rule ADD COLUMN user_id INTEGER",
            "profile_id": "ALTER TABLE ai_governance_rule ADD COLUMN profile_id INTEGER",
            "period": "ALTER TABLE ai_governance_rule ADD COLUMN period VARCHAR DEFAULT 'day'",
            "max_requests": "ALTER TABLE ai_governance_rule ADD COLUMN max_requests INTEGER",
            "max_tokens": "ALTER TABLE ai_governance_rule ADD COLUMN max_tokens INTEGER",
            "max_cost_micro_usd": "ALTER TABLE ai_governance_rule ADD COLUMN max_cost_micro_usd INTEGER",
            "max_concurrent": "ALTER TABLE ai_governance_rule ADD COLUMN max_concurrent INTEGER",
            "mode": "ALTER TABLE ai_governance_rule ADD COLUMN mode VARCHAR DEFAULT 'enforce'",
            "notify_enabled": "ALTER TABLE ai_governance_rule ADD COLUMN notify_enabled BOOLEAN DEFAULT 1",
            "is_active": "ALTER TABLE ai_governance_rule ADD COLUMN is_active BOOLEAN DEFAULT 1",
            "sort_order": "ALTER TABLE ai_governance_rule ADD COLUMN sort_order INTEGER DEFAULT 0",
        },
        "ai_governance_event": {
            "rule_id": "ALTER TABLE ai_governance_event ADD COLUMN rule_id INTEGER",
            "user_id": "ALTER TABLE ai_governance_event ADD COLUMN user_id INTEGER",
            "profile_id": "ALTER TABLE ai_governance_event ADD COLUMN profile_id INTEGER",
            "model_id": "ALTER TABLE ai_governance_event ADD COLUMN model_id INTEGER",
            "provider_id": "ALTER TABLE ai_governance_event ADD COLUMN provider_id INTEGER",
            "event_type": "ALTER TABLE ai_governance_event ADD COLUMN event_type VARCHAR DEFAULT 'allowed'",
            "metric": "ALTER TABLE ai_governance_event ADD COLUMN metric VARCHAR DEFAULT 'request'",
            "current_value": "ALTER TABLE ai_governance_event ADD COLUMN current_value INTEGER DEFAULT 0",
            "limit_value": "ALTER TABLE ai_governance_event ADD COLUMN limit_value INTEGER DEFAULT 0",
            "window_start": "ALTER TABLE ai_governance_event ADD COLUMN window_start DATETIME",
            "window_end": "ALTER TABLE ai_governance_event ADD COLUMN window_end DATETIME",
            "message": "ALTER TABLE ai_governance_event ADD COLUMN message VARCHAR",
            "notified": "ALTER TABLE ai_governance_event ADD COLUMN notified BOOLEAN DEFAULT 0",
        },
        "ai_runtime_invocation": {
            "invocation_id": "ALTER TABLE ai_runtime_invocation ADD COLUMN invocation_id VARCHAR",
            "user_id": "ALTER TABLE ai_runtime_invocation ADD COLUMN user_id INTEGER",
            "profile_id": "ALTER TABLE ai_runtime_invocation ADD COLUMN profile_id INTEGER",
            "model_id": "ALTER TABLE ai_runtime_invocation ADD COLUMN model_id INTEGER",
            "provider_id": "ALTER TABLE ai_runtime_invocation ADD COLUMN provider_id INTEGER",
            "status": "ALTER TABLE ai_runtime_invocation ADD COLUMN status VARCHAR DEFAULT 'running'",
            "started_at": "ALTER TABLE ai_runtime_invocation ADD COLUMN started_at DATETIME",
            "finished_at": "ALTER TABLE ai_runtime_invocation ADD COLUMN finished_at DATETIME",
        },
        "workflow_instance": {
            "celery_task_id": "ALTER TABLE workflow_instance ADD COLUMN celery_task_id VARCHAR",
            "user_id": "ALTER TABLE workflow_instance ADD COLUMN user_id INTEGER",
            "version_id": "ALTER TABLE workflow_instance ADD COLUMN version_id INTEGER",
            "failed_node_id": "ALTER TABLE workflow_instance ADD COLUMN failed_node_id VARCHAR",
        },
        "workflow_execution_log": {
            "payload_type": "ALTER TABLE workflow_execution_log ADD COLUMN payload_type VARCHAR DEFAULT 'full'",
            "diff_base_log_id": "ALTER TABLE workflow_execution_log ADD COLUMN diff_base_log_id INTEGER",
            "input_storage_ref": "ALTER TABLE workflow_execution_log ADD COLUMN input_storage_ref VARCHAR",
            "output_storage_ref": "ALTER TABLE workflow_execution_log ADD COLUMN output_storage_ref VARCHAR",
        },
        "workflow_eval_case_result": {
            "actual_output_storage_ref": "ALTER TABLE workflow_eval_case_result ADD COLUMN actual_output_storage_ref VARCHAR",
            "tags": "ALTER TABLE workflow_eval_case_result ADD COLUMN tags VARCHAR",
        },
        "workflow_eval_test_case": {
            "tags": "ALTER TABLE workflow_eval_test_case ADD COLUMN tags VARCHAR",
        },
        "workflow_eval_run": {
            "definition_version_id": "ALTER TABLE workflow_eval_run ADD COLUMN definition_version_id INTEGER",
            "test_set_snapshot": "ALTER TABLE workflow_eval_run ADD COLUMN test_set_snapshot TEXT",
        },
        "workflow_definition": {
            "user_id": "ALTER TABLE workflow_definition ADD COLUMN user_id INTEGER",
            "current_version_id": "ALTER TABLE workflow_definition ADD COLUMN current_version_id INTEGER",
            "draft_version_id": "ALTER TABLE workflow_definition ADD COLUMN draft_version_id INTEGER",
        },
        "media_asset": {
            "asset_type": "ALTER TABLE media_asset ADD COLUMN asset_type VARCHAR DEFAULT 'file'",
            "source_type": "ALTER TABLE media_asset ADD COLUMN source_type VARCHAR DEFAULT 'upload'",
            "source_task_id": "ALTER TABLE media_asset ADD COLUMN source_task_id INTEGER",
            "provider_code": "ALTER TABLE media_asset ADD COLUMN provider_code VARCHAR",
            "model_code": "ALTER TABLE media_asset ADD COLUMN model_code VARCHAR",
            "profile_code": "ALTER TABLE media_asset ADD COLUMN profile_code VARCHAR",
            "original_url": "ALTER TABLE media_asset ADD COLUMN original_url VARCHAR",
            "storage_url": "ALTER TABLE media_asset ADD COLUMN storage_url VARCHAR",
            "file_name": "ALTER TABLE media_asset ADD COLUMN file_name VARCHAR",
            "mime_type": "ALTER TABLE media_asset ADD COLUMN mime_type VARCHAR",
            "md5": "ALTER TABLE media_asset ADD COLUMN md5 VARCHAR",
            "size_bytes": "ALTER TABLE media_asset ADD COLUMN size_bytes INTEGER DEFAULT 0",
            "width": "ALTER TABLE media_asset ADD COLUMN width INTEGER",
            "height": "ALTER TABLE media_asset ADD COLUMN height INTEGER",
            "duration_seconds": "ALTER TABLE media_asset ADD COLUMN duration_seconds FLOAT",
            "prompt": "ALTER TABLE media_asset ADD COLUMN prompt VARCHAR",
            "params_payload": "ALTER TABLE media_asset ADD COLUMN params_payload VARCHAR",
            "status": "ALTER TABLE media_asset ADD COLUMN status VARCHAR DEFAULT 'pending'",
            "error_message": "ALTER TABLE media_asset ADD COLUMN error_message VARCHAR",
            "created_by": "ALTER TABLE media_asset ADD COLUMN created_by INTEGER",
        },
    }

    # 所有需要检查标准字段的表列表
    tables_to_check = [
        "sys_department",
        "sys_role",
        "sys_menu",
        "sys_user",
        "sys_param",
        "sys_log",
        "sys_login_log",
        "dict_type",
        "dict_info",
        "task_info",
        "task_log",
        "notification_message",
        "notification_recipient",
        "notification_template",
        "notification_rule",
        "ai_provider",
        "ai_model",
        "ai_model_profile",
        "ai_model_call_log",
        "ai_generation_task",
        "ai_governance_rule",
        "ai_governance_event",
        "ai_runtime_invocation",
        "media_asset",
        "workflow_definition",
        "workflow_definition_version",
        "workflow_instance",
        "workflow_execution_log",
        "workflow_eval_case_result",
        "workflow_eval_test_case",
        "workflow_eval_run",
        "sys_user_role",
        "sys_role_menu",
        "sys_role_department",
    ]

    inspector = inspect(engine)
    with engine.begin() as connection:
        existing_tables = set(inspector.get_table_names())

        for table_name in tables_to_check:
            if table_name not in existing_tables:
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}

            # 1. 检查并补齐标准字段 (delete_time, updated_at)
            for col_name, ddl_template in standard_columns.items():
                if col_name not in existing_columns:
                    try:
                        connection.execute(text(ddl_template.format(table=table_name)))
                    except Exception as e:
                        print(f"Failed to add standard column {col_name} to {table_name}: {e}")

            # 2. 检查并补齐特定表字段
            if table_name in specific_columns:
                for col_name, ddl in specific_columns[table_name].items():
                    if col_name not in existing_columns:
                        try:
                            connection.execute(text(ddl))
                        except Exception as e:
                            print(f"Failed to add specific column {col_name} to {table_name}: {e}")


# 幂等索引清单：每条 = (索引名, 表名, 列 SQL 片段, 可选 WHERE)。
# Field(index=True) 仅对 create_all 新建表生效，现有库不会自动补索引；这里为现有库补齐查询关键索引。
# 复合索引优先服务统计聚合（按时间范围扫描）与分页（keyset），单列索引由 create_all 对新表建立，此处为旧库补齐。
INDEX_DEFINITIONS: list[tuple[str, str, str, str | None]] = [
    # ai_model_call_log：统计看板/日志统计(P0-1)的主查询路径——按 created_at 范围扫描
    ("ix_ai_model_call_log_created_at", "ai_model_call_log", "created_at", None),
    ("ix_ai_model_call_log_status_created_at", "ai_model_call_log", "status, created_at", None),
    ("ix_ai_model_call_log_user_id_created_at", "ai_model_call_log", "user_id, created_at", None),
    ("ix_ai_model_call_log_model_id_created_at", "ai_model_call_log", "model_id, created_at", None),
    # workflow_execution_log：节点日志按实例 + 时间排序/分页(T7)
    ("ix_workflow_execution_log_instance_id_created_at", "workflow_execution_log", "instance_id, created_at", None),
    # workflow_instance：实例列表按定义 + 时间查询
    ("ix_workflow_instance_definition_id_created_at", "workflow_instance", "definition_id, created_at", None),
    # workflow_eval：回归对比（同测试集按时间）与 P95 排序（同 run 按 latency）的复合索引（T9）
    ("ix_workflow_eval_run_test_set_id_created_at", "workflow_eval_run", "test_set_id, created_at", None),
    ("ix_workflow_eval_case_result_eval_run_id_latency_ms", "workflow_eval_case_result", "eval_run_id, latency_ms", None),
    ("ix_workflow_eval_case_result_eval_run_id_case_key", "workflow_eval_case_result", "eval_run_id, case_key", None),
    ("ix_workflow_eval_test_case_test_set_id_case_key", "workflow_eval_test_case", "test_set_id, case_key", None),
    # workflow_definition_version：版本历史（按定义+时间）与状态过滤（查 draft/发布版）
    ("ix_workflow_definition_version_definition_id_created_at", "workflow_definition_version", "definition_id, created_at", None),
    ("ix_workflow_definition_version_definition_id_status", "workflow_definition_version", "definition_id, status", None),
]


def _ensure_indexes() -> None:
    """为现有库幂等补建查询关键索引（CREATE INDEX IF NOT EXISTS）。

    与 _ensure_sqlite_compatible_schema 的补列机制互补。SQLite 与 PostgreSQL 均支持
    `CREATE INDEX IF NOT EXISTS` 与部分索引（WHERE 子句）。生产 PG 大表可设
    SKIP_INDEX_ENSURE=True 跳过，由 DBA 在维护窗口用 CREATE INDEX CONCURRENTLY 建立。
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
