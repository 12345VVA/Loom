"""
数据库配置
"""
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings
from app.modules.base.model import auth as _base_auth_models  # noqa: F401
from app.modules.base.model.sys import SysLog, SysLoginLog, SysParam
from app.modules.base.model import sys as _base_sys_models  # noqa: F401
from app.modules.dict.model import dict as _dict_models  # noqa: F401
from app.modules.task.model import task as _task_models  # noqa: F401
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
    }

    # 所有需要检查标准字段的表列表
    tables_to_check = [
        "sys_department", "sys_role", "sys_menu", "sys_user",
        "sys_param", "sys_log", "sys_login_log", 
        "dict_type", "dict_info", "task_info", "task_log",
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
