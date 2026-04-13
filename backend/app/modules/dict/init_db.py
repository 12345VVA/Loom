"""
Dict 模块初始化资源
"""
from sqlmodel import Session, select
from app.modules.dict.model.dict import DictType, DictInfo

def run(session: Session) -> None:
    status_dict = session.exec(select(DictType).where(DictType.key == "status")).first()
    if status_dict is None:
        status_dict = DictType(name="状态", key="status")
        session.add(status_dict)
        session.commit()
        session.refresh(status_dict)

    if status_dict.id is not None:
        existing_values = list(session.exec(select(DictInfo).where(DictInfo.type_id == status_dict.id)).all())
        if not existing_values:
            session.add(DictInfo(type_id=status_dict.id, name="禁用", value="0", order_num=0))
            session.add(DictInfo(type_id=status_dict.id, name="启用", value="1", order_num=1))

    session.commit()
