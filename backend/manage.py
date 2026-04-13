"""
Loom 管理工具
"""
import typer
from sqlmodel import Session
from app.core.database import engine, init_db
from app.modules import bootstrap_modules
from app.modules.base.service.auth_service import AuthService
from app.core.config import settings

cli = typer.Typer(help="Loom Management CLI")

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
    print(f"当前环境: {settings.ENV}")

if __name__ == "__main__":
    cli()
