"""
Base 模块初始化资源占位
"""
from sqlmodel import Session
from sqlmodel import select

from app.modules.base.model.sys import SysParam


def run(session: Session) -> None:
    if session.exec(select(SysParam).where(SysParam.key_name == "logKeep")).first() is None:
        session.add(SysParam(name="日志保存天数", key_name="logKeep", data="7", data_type=0))

    session.commit()
