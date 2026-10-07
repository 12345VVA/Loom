"""
Dict 模块初始化资源
"""

from sqlmodel import Session, select

from app.modules.dict.model.dict import DictInfo, DictType


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
            session.add(DictInfo(type_id=status_dict.id, name="禁用", value="0", sort_order=0))
            session.add(DictInfo(type_id=status_dict.id, name="启用", value="1", sort_order=1))

    # AI 模型能力标签字典
    cap_dict = session.exec(select(DictType).where(DictType.key == "ai_model_capability")).first()
    if cap_dict is None:
        cap_dict = DictType(name="模型能力标签", key="ai_model_capability")
        session.add(cap_dict)
        session.commit()
        session.refresh(cap_dict)

    if cap_dict.id is not None:
        existing_caps = list(session.exec(select(DictInfo).where(DictInfo.type_id == cap_dict.id)).all())
        if not existing_caps:
            default_capabilities = [
                ("对话", "chat", 1),
                ("流式输出", "stream", 2),
                ("工具调用", "tools", 3),
                ("思考推理", "thinking", 4),
                ("JSON模式", "json", 5),
                ("视觉理解", "vision", 6),
                ("向量嵌入", "embedding", 7),
                ("语义重排", "rerank", 8),
                ("图像生成", "image", 9),
                ("文生图", "text-to-image", 10),
                ("图生图", "image-to-image", 11),
                ("音频处理", "audio", 12),
                ("视频生成", "video", 13),
            ]
            for name, value, order in default_capabilities:
                session.add(DictInfo(type_id=cap_dict.id, name=name, value=value, sort_order=order))

    session.commit()
