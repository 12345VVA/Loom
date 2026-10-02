"""
Loom 管理工具
"""

import typer
from sqlmodel import Session, SQLModel

from app.core.config import settings
from app.core.database import DATABASE_URL, engine, init_db
from app.modules import bootstrap_modules
from app.modules.base.service.auth_service import AuthService

cli = typer.Typer(help="Loom Management CLI")


@cli.command()
def rebuild():
    """彻底重建数据库：DROP 所有应用表（保留 alembic_version 与扩展）后重新初始化所有数据"""
    print("正在准备重建数据库...")
    # alembic_version 不属于 SQLModel.metadata，会被保留，迁移版本标记不受影响。
    print(f"[{DATABASE_URL.split('://', 1)[0]}] DROP 所有应用表以彻底重建...")
    SQLModel.metadata.drop_all(engine)
    print("应用表已清除。")

    print("正在创建新数据库架构...")
    init_db()

    with Session(engine) as session:
        print("正在同步模块菜单与初始化数据...")
        bootstrap_modules(session)

        print("执行基础引导逻辑 (AuthService.bootstrap_defaults)...")
        AuthService(session).bootstrap_defaults()

    print("数据库重建并初始化完成！")


@cli.command()
def init_menu():
    """重新初始化数据库菜单并同步代码中的配置"""
    print("正在初始化数据库...")
    init_db()
    with Session(engine) as session:
        print("正在同步模块菜单...")
        bootstrap_modules(session)

        print("执行基础引导逻辑 (AuthService.bootstrap_defaults)...")
        AuthService(session).bootstrap_defaults()

    print("菜单重新初始化完成！")


@cli.command()
def info():
    """查看当前应用配置信息"""
    print(f"应用名称: {settings.APP_NAME}")
    print(f"版本: {settings.APP_VERSION}")
    print(f"运行模式: {'development' if settings.DEBUG else 'production'}")
    print(f"数据库后端: {DATABASE_URL.split('://', 1)[0]}")


if __name__ == "__main__":
    cli()
