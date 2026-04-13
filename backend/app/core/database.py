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

engine = create_engine(
    DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)


def init_db():
    """初始化数据库"""
    SQLModel.metadata.create_all(engine)
    _ensure_sqlite_compatible_schema()


def get_session():
    """获取数据库会话"""
    with Session(engine) as session:
        yield session


def _ensure_sqlite_compatible_schema() -> None:
    if "sqlite" not in DATABASE_URL:
        return

    required_columns = {
        "sys_department": {
            "updated_at": "ALTER TABLE sys_department ADD COLUMN updated_at DATETIME",
        },
        "sys_role": {
            "remark": "ALTER TABLE sys_role ADD COLUMN remark VARCHAR",
            "updated_at": "ALTER TABLE sys_role ADD COLUMN updated_at DATETIME",
        },
        "sys_menu": {
            "icon": "ALTER TABLE sys_menu ADD COLUMN icon VARCHAR",
            "keep_alive": "ALTER TABLE sys_menu ADD COLUMN keep_alive BOOLEAN DEFAULT 1",
            "is_show": "ALTER TABLE sys_menu ADD COLUMN is_show BOOLEAN DEFAULT 1",
            "updated_at": "ALTER TABLE sys_menu ADD COLUMN updated_at DATETIME",
        },
        "sys_user": {
            "nick_name": "ALTER TABLE sys_user ADD COLUMN nick_name VARCHAR",
            "head_img": "ALTER TABLE sys_user ADD COLUMN head_img VARCHAR",
            "phone": "ALTER TABLE sys_user ADD COLUMN phone VARCHAR",
            "remark": "ALTER TABLE sys_user ADD COLUMN remark VARCHAR",
            "updated_at": "ALTER TABLE sys_user ADD COLUMN updated_at DATETIME",
        },
    }
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in required_columns.items():
            if table_name not in inspector.get_table_names():
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(ddl))
