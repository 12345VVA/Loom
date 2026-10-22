"""asset 模块初始化资源：受控 dict 大类种子（决策 #34，词表边界）。

分类/分组维度一律走受控 dict；自由 tags 仅承载搜索关键词不承载分类语义。
"""

from sqlmodel import Session, select

from app.modules.dict.model.dict import DictInfo, DictType

# (dict key, 展示名, 默认词条 [(name, value, sort)])
_ASSET_DICT_TYPES = (
    (
        "asset_character_type",
        "角色类型",
        [("主角", "protagonist", 1), ("配角", "supporting", 2), ("反派", "villain", 3), ("Q版", "chibi", 4)],
    ),
    (
        "asset_scene_type",
        "场景类型",
        [("室内", "indoor", 1), ("室外", "outdoor", 2), ("奇幻", "fantasy", 3), ("城市场景", "urban", 4)],
    ),
    (
        "asset_style_category",
        "画风大类",
        [("写实", "realistic", 1), ("动漫", "anime", 2), ("水彩", "watercolor", 3), ("3D渲染", "render3d", 4)],
    ),
)


def run(session: Session) -> None:
    for key, name, entries in _ASSET_DICT_TYPES:
        dict_type = session.exec(select(DictType).where(DictType.key == key)).first()
        if dict_type is None:
            dict_type = DictType(name=name, key=key)
            session.add(dict_type)
            session.commit()
            session.refresh(dict_type)

        if dict_type.id is None:
            continue
        existing = session.exec(select(DictInfo).where(DictInfo.type_id == dict_type.id)).all()
        if existing:
            continue
        for entry_name, value, order in entries:
            session.add(DictInfo(type_id=dict_type.id, name=entry_name, value=value, sort_order=order))

    session.commit()
