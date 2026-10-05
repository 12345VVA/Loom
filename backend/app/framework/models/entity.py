"""
通用语言基类实体（门面 re-export）

M9：BaseEntity 定义已下沉 core 层（app/core/models/entity.py），解除
core→framework 的唯一反向依赖。历史引用方（framework 内部与各业务模块
model）经由此路径拿到同一类对象，SQLAlchemy 事件监听与 mapper 注册不受影响。
"""

from app.core.models.entity import BaseEntity as BaseEntity

__all__ = ["BaseEntity"]
