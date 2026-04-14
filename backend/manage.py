"""
Loom 管理工具
"""
import typer
from sqlmodel import Session
from app.core.database import engine, init_db, get_db_path
from app.modules import bootstrap_modules
from app.modules.base.service.auth_service import AuthService
from app.core.config import settings
import os

cli = typer.Typer(help="Loom Management CLI")

@cli.command()
def rebuild():
    """彻底重建数据库：删除旧数据库文件并重新初始化所有数据"""
    print("正在准备重建数据库...")
    db_path = get_db_path()
    
    if db_path and db_path.exists():
        print(f"检测到现有数据库: {db_path}")
        # 尝试关闭所有连接并删除文件
        engine.dispose()
        try:
            os.remove(db_path)
            print("旧数据库文件已成功删除。")
        except Exception as e:
            print(f"删除失败: {e}")
            return
    
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
    print(f"当前环境: {settings.ENV}")

if __name__ == "__main__":
    cli()
