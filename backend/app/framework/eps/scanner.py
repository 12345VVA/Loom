"""
EPS 模型列扫描器
"""
from __future__ import annotations

import datetime
from typing import Any, get_args, get_origin, Union

from pydantic import BaseModel


def scan_model_columns(model: Any) -> list[dict[str, Any]]:
    """
    扫描 Pydantic/SQLModel 模型并导出列元数据。
    """
    if not model or not hasattr(model, "model_fields"):
        return []

    columns: list[dict[str, Any]] = []
    fields = model.model_fields

    for name, field in fields.items():
        # 处理类型
        annotation = field.annotation
        origin = get_origin(annotation)
        args = get_args(annotation)

        is_nullable = False
        if origin is Union:
            # 判断是否包含 NoneType
            if type(None) in args:
                is_nullable = True
                # 提取实际类型
                actual_types = [t for t in args if t is not type(None)]
                base_type = actual_types[0] if actual_types else str
            else:
                base_type = args[0] if args else str
        else:
            base_type = annotation

        # 类型映射器
        eps_type = _map_python_type_to_eps(base_type)
        
        # 提取枚举选项
        enum_options = _extract_enum_options(base_type)

        # 提取验证规则
        validate = _extract_validation_rules(field)

        columns.append(
            {
                "propertyName": name,
                "prop": name,  # 对齐 Cool-Admin 的 prop 字段
                "type": eps_type,
                "comment": field.description or name,
                "label": field.description or name,  # 对齐 Cool-Admin 的 label 字段
                "nullable": is_nullable or not field.is_required(),
                "required": field.is_required() and not is_nullable,
                "dict": enum_options if enum_options else None,
                "validate": validate if validate else None
            }
        )

    return columns


def _extract_validation_rules(field: Any) -> dict[str, Any]:
    """从 FieldInfo 中提取 Pydantic 验证规则"""
    rules = {}
    
    # Pydantic v2 直接在 FieldInfo 对象上有这些属性，或者在 metadata 中
    attrs = ["max_length", "min_length", "pattern", "gt", "lt", "ge", "le"]
    for attr in attrs:
        val = getattr(field, attr, None)
        if val is not None:
            rules[attr] = val
        
    # 如果属性上没有，尝试从 metadata 列表里找 (某些自定义验证器)
    if not rules and hasattr(field, "metadata"):
        for meta in field.metadata:
            for attr in attrs:
                if hasattr(meta, attr):
                    rules[attr] = getattr(meta, attr)
                    
    return rules


def _extract_enum_options(py_type: Any) -> list[dict[str, Any]] | None:
    """提取枚举类的成员作为字典选项"""
    from enum import Enum
    if isinstance(py_type, type) and issubclass(py_type, Enum):
        return [{"label": str(e.name), "value": e.value} for e in py_type]
    return None


def _map_python_type_to_eps(py_type: Any) -> str:
    """将 Python 类型映射为前端识别的类型字符串"""
    from enum import Enum
    if py_type in (int, float):
        return "number"
    if py_type is bool:
        return "boolean"
    if py_type in (datetime.datetime, datetime.date):
        return "datetime"
    if isinstance(py_type, type) and issubclass(py_type, Enum):
        return "select"  # 枚举通常映射为选择器
    # 默认作为字符串处理
    return "string"
