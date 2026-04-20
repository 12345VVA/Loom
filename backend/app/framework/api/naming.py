"""统一命名转换：snake_case ↔ camelCase"""

def to_camel(name: str) -> str:
    """snake_case → camelCase"""
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])

# 语义差异字段的全局映射表
# key = 数据库字段名 (snake_case)
# value = 前端字段名 (camelCase 或其他)
FIELD_ALIASES: dict[str, str] = {
    "sort_order": "orderNum",
    "is_active": "status",
    "path": "router",
    "component": "viewPath",
    "permission": "perms",
    "full_name": "name",
    "created_at": "createTime",
    "updated_at": "updateTime",
    "delete_time": "deleteTime",
    "role_ids": "roleIdList",
    "menu_ids": "menuIdList",
    "department_ids": "departmentIdList",
    "password_version": "passwordVersion",
}

def resolve_alias(field_name: str) -> str:
    """解析字段别名：优先使用语义映射，否则 camelCase 转换"""
    return FIELD_ALIASES.get(field_name, to_camel(field_name))
