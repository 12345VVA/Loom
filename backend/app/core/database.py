"""
数据库配置
"""
from pathlib import Path
from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlalchemy.orm import SessionTransactionOrigin
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings
from app.modules.base.model import auth as _base_auth_models  # noqa: F401
from app.modules.base.model.sys import SysLog, SysLoginLog, SysParam
from app.modules.base.model import sys as _base_sys_models  # noqa: F401
from app.modules.dict.model import dict as _dict_models  # noqa: F401
from app.modules.task.model import task as _task_models  # noqa: F401
from app.modules.notification.model import notification as _notification_models  # noqa: F401
from app.modules.ai.model import ai as _ai_models  # noqa: F401
from app.modules.media.model import media as _media_models  # noqa: F401
from sqlalchemy import event
from datetime import datetime
from app.framework.models.entity import BaseEntity


@event.listens_for(BaseEntity, "before_update", propagate=True)
def timestamp_before_update(mapper, connection, target):
    """在更新前自动刷新 updated_at 字段"""
    target.updated_at = datetime.utcnow()


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
    "echo": settings.DEBUG,
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


def get_db_path() -> Path | None:
    """获取数据库文件路径 (仅适用于 SQLite)"""
    if not DATABASE_URL.startswith("sqlite:///"):
        return None
    return Path(DATABASE_URL.removeprefix("sqlite:///"))


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
    if "sqlite" not in DATABASE_URL:
        return

    # 定义所有基于 BaseEntity 的表及其标准可选字段
    # delete_time 是最近新增的，许多旧表可能由于 create_all 不会自动 ALTER 而缺失
    standard_columns = {
        "id": "ALTER TABLE {table} ADD COLUMN id INTEGER PRIMARY KEY AUTOINCREMENT",
        "created_at": "ALTER TABLE {table} ADD COLUMN created_at DATETIME",
        "updated_at": "ALTER TABLE {table} ADD COLUMN updated_at DATETIME",
        "delete_time": "ALTER TABLE {table} ADD COLUMN delete_time DATETIME",
    }

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
        "sys_department", "sys_role", "sys_menu", "sys_user",
        "sys_param", "sys_log", "sys_login_log", 
        "dict_type", "dict_info", "task_info", "task_log",
        "notification_message", "notification_recipient", "notification_template", "notification_rule",
        "ai_provider", "ai_model", "ai_model_profile", "ai_model_call_log", "ai_generation_task",
        "media_asset",
        "sys_user_role", "sys_role_menu", "sys_role_department"
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
