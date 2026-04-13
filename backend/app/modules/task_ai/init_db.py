"""
Task 模块初始化资源占位
"""
from sqlmodel import Session


def run(session: Session) -> None:
    _ = session
