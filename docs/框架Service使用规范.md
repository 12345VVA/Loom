# 框架 Service 使用规范

> 版本：v1.0
> 生效日期：2026-04-21
> 适用范围：所有后端 Service 层开发

---

## 一、概述

Service 层是业务逻辑的核心层，负责数据处理、业务规则执行、事务管理等。本项目提供 `BaseAdminCrudService` 基类，封装了标准的 CRUD 操作，支持软删除、树形结构、关联查询等高级特性。

### 1.1 核心特性

1. **通用 CRUD** - 自动实现增删改查功能
2. **生命周期钩子** - 支持操作前后的业务逻辑注入
3. **软删除支持** - 内置软删除机制
4. **树形结构** - 自动处理树形数据的父子关系
5. **关联查询** - 自动 JOIN 关联表
6. **操作日志** - 自动记录数据变更

### 1.2 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                     Service 层架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Controller 层                                              │
│       ↓                                                     │
│  Service 层 (BaseAdminCrudService)                          │
│       ↓                                                     │
│  生命周期钩子 (_before_add, _after_add, ...)               │
│       ↓                                                     │
│  数据库层 (SQLModel/SQLAlchemy)                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Service 类名 | `{资源}AdminService` | `UserAdminService` |
| 文件名 | `{资源}_service.py` 或 `admin_service.py` | `user_service.py` |
| 方法名 | 动词_名词 或 动词 | `get_user`, `assign_roles` |

---

## 二、Service 基类规范

### 2.1 BaseAdminCrudService 核心

```python
class BaseAdminCrudService:
    """管理资源通用服务基类"""
    
    def __init__(self, session: Session, model: Type[Any] | None = None, **kwargs):
        self.session = session
        self.model = model
        self.soft_delete = kwargs.get("soft_delete", False)
        self.relations = kwargs.get("relations", ())
        self.is_tree = kwargs.get("is_tree", False)
        self.parent_field = kwargs.get("parent_field", "parent_id")
```

### 2.2 基础 CRUD 方法

| 方法 | 功能 | 参数 | 返回值 |
|------|------|------|--------|
| `info(id)` | 获取详情 | `id`, `current_user`, `relations` | `dict` |
| `list(query)` | 获取列表 | `query`, `current_user`, `relations`, `is_tree`, `parent_field` | `list[dict]` |
| `page(query)` | 获取分页 | `query`, `current_user`, `relations` | `PageResult[dict]` |
| `add(payload)` | 新增 | `payload` (Request 模型) | 实体对象 |
| `update(payload)` | 更新 | `payload` (Request 模型) | 实体对象 |
| `delete(ids)` | 删除 | `ids: list[int]`, `payload`, `soft_delete` | `dict` |

### 2.3 实例化配置

```python
class UserAdminService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(
            session,
            User,              # 模型类
            soft_delete=True,   # 启用软删除
            relations=(...),    # 关联配置
        )
```

---

## 三、生命周期钩子规范

### 3.1 钩子方法列表

| 钩子方法 | 调用时机 | 用途 | 返回值 |
|----------|----------|------|--------|
| `_before_add(data)` | 新增前 | 数据验证、默认值设置 | `dict` |
| `_after_add(entity, payload)` | 新增后 | 关联操作、缓存清理、日志记录 | `None` |
| `_before_update(data, entity)` | 更新前 | 数据验证、权限检查 | `dict` |
| `_after_update(entity, payload)` | 更新后 | 关联操作、缓存清理、日志记录 | `None` |
| `_before_delete(ids, payload)` | 删除前 | 权限检查、依赖检查 | `list[int]` |
| `_after_delete(ids, payload)` | 删除后 | 关联清理、缓存清理 | `None` |

### 3.2 _before_add 使用规范

```python
def _before_add(self, data: dict) -> dict:
    """新增前置处理
    
    用于：
    - 数据验证
    - 设置默认值
    - 字段规范化
    - 业务规则检查
    """
    # 示例 1: 数据验证
    username = data.get("username")
    existing = self.session.exec(
        select(User).where(User.username == username)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    
    # 示例 2: 设置默认值
    data.setdefault("nick_name", data.get("full_name", ""))
    
    # 示例 3: 字段规范化
    data["type"] = self._normalize_menu_type(data.get("type"))
    
    # ⚠️ 禁止：不要手动转换字段名
    # data["parent_id"] = data.pop("parentId", None)  # ❌
    
    return data
```

### 3.3 _after_add 使用规范

```python
def _after_add(self, entity: Any, payload: Any = None) -> None:
    """新增后置处理
    
    用于：
    - 关联数据创建
    - 缓存更新
    - 日志记录
    - 事件触发
    """
    # 示例 1: 创建关联
    if hasattr(payload, "role_ids"):
        self._replace_user_roles(entity.id, payload.role_ids)
    
    # 示例 2: 清理缓存
    clear_login_caches(entity.id)
    
    # 示例 3: 记录审计日志
    self._log_entity_change(entity.id, "create", {"data": entity.model_dump()}, payload)
```

### 3.4 _before_update 使用规范

```python
def _before_update(self, data: dict, entity: Any) -> dict:
    """更新前置处理"""
    # 示例 1: 密码特殊处理
    if data.get("password"):
        if not data.get("old_password"):
            raise HTTPException(status_code=400, detail="原密码不能为空")
        if not verify_password(data["old_password"], entity.password_hash):
            raise HTTPException(status_code=400, detail="原密码错误")
        data["password_hash"] = hash_password(data.pop("password"))
        entity.password_version += 1
    
    # 示例 2: 设置默认值
    data["nick_name"] = data.get("nick_name") or data.get("full_name", entity.full_name)
    
    return data
```

### 3.5 _after_update 使用规范

```python
def _after_update(self, entity: Any, payload: Any = None) -> None:
    """更新后置处理"""
    # 示例 1: 更新关联
    if hasattr(payload, "role_ids"):
        self._replace_user_roles(entity.id, payload.role_ids)
    
    # 示例 2: 被禁用用户登出
    if hasattr(payload, "is_active") and not payload.is_active:
        add_user_all_tokens_to_blacklist(entity.id)
    else:
        clear_login_caches(entity.id)
```

### 3.6 _before_delete 使用规范

```python
def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
    """删除前置处理"""
    # 示例 1: 保护超级管理员
    users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())
    protected_users = [user.username for user in users if user.is_super_admin]
    if protected_users:
        raise HTTPException(status_code=400, detail=f"不能删除超级管理员: {', '.join(protected_users)}")
    
    # 示例 2: 收集受影响的用户（用于缓存清理）
    affected_user_ids = [
        link.user_id for link in self.session.exec(
            select(UserRoleLink).where(UserRoleLink.role_id.in_(ids))
        ).all()
    ]
    self._affected_user_ids_storage = affected_user_ids
    
    return ids
```

### 3.7 _after_delete 使用规范

```python
def _after_delete(self, ids: list[int], payload: Any = None) -> None:
    """删除后置处理"""
    # 示例 1: 清理缓存
    if hasattr(self, "_affected_user_ids_storage"):
        clear_login_caches_for_users(self._affected_user_ids_storage)
        del self._affected_user_ids_storage
    
    # 示例 2: 加入黑名单
    for user_id in ids:
        add_user_all_tokens_to_blacklist(user_id)
```

---

## 四、数据转换规范

### 4.1 _row_to_dict 规范

`_row_to_dict` 负责将数据库查询结果转换为字典，**只做业务数据补充，不做字段名转换**：

```python
def _row_to_dict(self, row: Any) -> dict:
    """
    将查询结果转换为字典。
    保持内部使用 snake_case 以支持子类逻辑。
    """
    data = super()._row_to_dict(row)
    
    # ✅ 正确：补充业务数据
    user_id = data.get("id")
    if user_id:
        roles = get_user_roles(self.session, user_id)
        data["role_ids"] = [role.id for role in roles if role.id is not None]
        data["role_name"] = ",".join(role.name for role in roles if role.name)
    
    # ✅ 正确：设置默认值
    if data.get("nick_name") is None:
        data["nick_name"] = data.get("full_name") or data.get("username") or ""
    
    # ❌ 禁止：字段名转换
    # data["roleIdList"] = data.pop("role_ids", [])  # ❌
    # data["createTime"] = data["created_at"]         # ❌
    
    return data
```

### 4.2 _finalize_data 规范

`_finalize_data` 由基类提供，统一处理 camelCase 转换，**子类不应覆盖**：

```python
# 基类实现
def _finalize_data(self, data: Any) -> Any:
    """
    统一出口转换：将数据转换为前端期望的 camelCase 格式。
    支持 dict 和 list[dict]。
    """
    from app.framework.api.naming import resolve_alias
    if data is None:
        return None
    if isinstance(data, list):
        return [self._finalize_data(item) for item in data]
    if isinstance(data, dict):
        return {resolve_alias(k): v for k, v in data.items()}
    return data
```

### 4.3 数据转换流程

```
数据库 (snake_case)
    ↓
_row_to_dict() (snake_case + 业务数据)
    ↓
_finalize_data() (camelCase)
    ↓
前端 (camelCase)
```

### 4.4 查询与数据权限

通用 `list/page/info` 会通过 `_apply_query()` 进入 `QueryBuilder`。当服务方法签名接收 `current_user` 时，控制器会自动注入当前用户，基类会解析 `DataScopeContext` 并应用到查询：

```python
def page(self, query: CrudQuery, current_user: User | None = None):
    statement = select(self.model)
    statement = self._apply_query(statement, self.model, query, current_user=current_user)
    ...
```

数据权限只识别模型上的 `user_id`、`department_id` 字段；没有这些字段的模型不会被误过滤。

---

## 五、自定义业务方法规范

### 5.1 方法命名规范

```python
# ✅ 推荐：动词开头，语义清晰
def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
    """分配用户角色"""
    pass

def reset_password(self, user_id: int, new_password: str) -> dict:
    """重置用户密码"""
    pass

def get_statistics(self, days: int) -> dict:
    """获取统计信息"""
    pass

# ❌ 不推荐：命名不清晰
def roles(self, user_id: int) -> dict:  # 应该叫 assign_roles 或 get_roles
    pass

def do_reset(self, ...):  # 应该叫 reset_password
    pass
```

### 5.2 方法签名规范

```python
# ✅ 推荐：明确参数类型和返回类型
def assign_roles(
    self, 
    payload: UserRoleAssignRequest,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserListItem:
    """分配用户角色"""
    pass

# ❌ 不推荐：缺少类型标注
def assign_roles(self, payload, user=None):
    pass
```

### 5.3 事务处理规范

```python
# ✅ 推荐：显式提交事务
def move(self, payload: UserMoveRequest) -> dict:
    """移动用户到其他部门"""
    department = self.session.get(Department, payload.department_id)
    if not department:
        raise HTTPException(status_code=404, detail="部门不存在")
    
    users = list(self.session.exec(
        select(User).where(User.id.in_(payload.user_ids))
    ).all())
    
    for user in users:
        user.department_id = payload.department_id
        self.session.add(user)
    
    self.session.commit()  # 显式提交
    
    for user in users:
        clear_login_caches(user.id)
    
    return {"success": True}
```

### 5.4 错误处理规范

```python
# ✅ 推荐：使用 HTTPException
def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
    user = self.session.get(User, payload.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    roles = list(self.session.exec(
        select(Role).where(Role.id.in_(payload.role_ids))
    ).all())
    
    if len(roles) != len(payload.role_ids):
        missing = set(payload.role_ids) - {role.id for role in roles}
        raise HTTPException(status_code=404, detail=f"角色不存在: {missing}")
    
    # 业务逻辑...
    return user
```

---

## 六、软删除规范

### 6.1 启用软删除

```python
class UserAdminService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(
            session,
            User,
            soft_delete=True,  # 启用软删除
        )
```

### 6.2 软删除行为

- **删除操作**：设置 `delete_time = 当前时间`
- **查询操作**：自动过滤 `delete_time IS NULL` 的记录
- **更新操作**：不允许更新已软删除的记录
- **物理删除**：通过 `soft_delete=False` 参数强制物理删除

### 6.3 软删除查询

```python
# 自动过滤软删除记录
def list_active_users(self) -> list[User]:
    """只返回未删除的用户"""
    return self.session.exec(
        select(User).where(User.delete_time == None)
    ).all()

# 查询包含软删除的记录
def list_all_users(self) -> list[User]:
    """返回所有用户（包括已删除）"""
    return self.session.exec(select(User)).all()
```

---

## 七、树形结构规范

### 7.1 启用树形结构

```python
class MenuAdminService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(
            session,
            Menu,
            is_tree=True,           # 启用树形结构
            parent_field="parent_id", # 父字段名
        )
```

### 7.2 树形方法

```python
# 基类提供的树形方法
def tree(self) -> list[dict]:
    """获取完整的树形结构"""
    return self.list(is_tree=True)

def current_tree(self, current_user: User) -> list[MenuTreeItem]:
    """获取当前用户授权的菜单树"""
    # 自定义实现...
```

### 7.3 树形数据结构

```json
[
  {
    "id": 1,
    "name": "系统管理",
    "parentId": null,
    "children": [
      {
        "id": 2,
        "name": "用户管理",
        "parentId": 1,
        "children": []
      }
    ]
  }
]
```

---

## 八、关联查询规范

### 8.1 RelationConfig 配置

```python
from app.framework.controller_meta import RelationConfig

# 在 Controller 中配置
@CoolController(
    CoolControllerMeta(
        relations=(
            RelationConfig(
                model=Department,        # 目标模型
                column="department_id",   # 当前模型关联字段
                target_column="name",    # 目标模型字段
                alias="departmentName"   # 输出别名
            ),
        ),
    )
)
class BaseUserController(BaseController):
    pass
```

### 8.2 Service 层处理

```python
class UserAdminService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(
            session,
            User,
            relations=(  # 也可以在 Service 中配置
                RelationConfig(
                    model=Department,
                    column="department_id",
                    target_column="name",
                    alias="departmentName"
                ),
            ),
        )
```

### 8.3 返回数据格式

```json
{
  "id": 1,
  "username": "admin",
  "departmentId": 1,
  "departmentName": "技术部"  // 自动关联查询
}
```

---

## 九、完整示例

### 9.1 用户管理 Service

```python
"""
用户管理服务
"""
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    add_user_all_tokens_to_blacklist,
)
from app.framework.controller_meta import BaseAdminCrudService, RelationConfig
from app.modules.base.model.auth import (
    Department,
    Role,
    RoleMenuLink,
    User,
    UserRoleLink,
    UserCreateRequest,
    UserListItem,
    UserMoveRequest,
    UserRoleAssignRequest,
    UserUpdateRequest,
)
from app.modules.base.service.authority_service import (
    clear_login_caches,
    clear_login_caches_for_users,
    get_user_roles,
)
from app.modules.base.service.data_scope_service import can_access_user


class UserAdminService(BaseAdminCrudService):
    """用户资源管理服务"""
    
    def __init__(self, session: Session):
        super().__init__(session, User)
    
    # ========== 生命周期钩子 ==========
    
    def _after_add(self, entity: User, payload: Any) -> None:
        """用户创建后记录安全审计日志"""
        try:
            from app.modules.base.service.sys_manage_service import SysSecurityLogService
            
            operator_id = getattr(payload, "_operator_id", None)
            operator_name = getattr(payload, "_operator_name", None) or "system"
            operator_ip = getattr(payload, "_operator_ip", None)
            
            SysSecurityLogService(self.session).create_entry(
                operator_id=operator_id or 0,
                operator_name=operator_name,
                operator_ip=operator_ip,
                target_type="user",
                target_id=entity.id,
                target_name=entity.username,
                operation="create",
                module="user",
                resource_path=f"/admin/base/sys/user/{entity.id}",
                new_value='{"username": "%s", "full_name": "%s"}' % (entity.username, entity.full_name),
                business_type="user_management",
                status=1,
                remark="创建新用户"
            )
        except Exception as exc:
            logger.warning(f"记录用户创建审计日志失败 - user_id: {entity.id}", exc_info=exc)
        
        if hasattr(payload, "role_ids"):
            self._replace_user_roles(entity.id, payload.role_ids)
    
    def _before_update(self, data: dict, entity: User) -> dict:
        """更新前置处理"""
        if data.get("password"):
            validate_password_strength(data["password"])
            data["password_hash"] = hash_password(data.pop("password"))
            entity.password_version += 1
        else:
            data.pop("password", None)
        
        data["nick_name"] = data.get("nick_name") or data.get("full_name", entity.full_name)
        return data
    
    def _after_update(self, entity: User, payload: Any) -> None:
        """更新后置处理"""
        if hasattr(payload, "role_ids"):
            self._replace_user_roles(entity.id, payload.role_ids)
        
        if hasattr(payload, "is_active") and not payload.is_active:
            add_user_all_tokens_to_blacklist(entity.id)
        else:
            clear_login_caches(entity.id)
    
    def _before_delete(self, ids: list[int], payload: Any = None) -> list[int]:
        """删除前置处理"""
        users = list(self.session.exec(select(User).where(User.id.in_(ids))).all())
        protected_users = [user.username for user in users if user.is_super_admin]
        if protected_users:
            raise HTTPException(status_code=400, detail=f"不能删除超级管理员: {', '.join(protected_users)}")
        
        affected_user_ids = [
            link.user_id for link in self.session.exec(
                select(UserRoleLink).where(UserRoleLink.user_id.in_(ids))
            ).all()
        ]
        self._affected_user_ids_storage = affected_user_ids
        return ids
    
    def _after_delete(self, ids: list[int], payload: Any = None) -> None:
        """删除后置处理"""
        if hasattr(self, "_affected_user_ids_storage"):
            clear_login_caches_for_users(self._affected_user_ids_storage)
            del self._affected_user_ids_storage
        
        for user_id in ids:
            add_user_all_tokens_to_blacklist(user_id)
    
    # ========== 数据转换 ==========
    
    def _row_to_dict(self, row: Any) -> dict:
        """补充业务数据"""
        data = super()._row_to_dict(row)
        if not data:
            return {}
        
        user_id = data.get("id")
        if user_id:
            roles = get_user_roles(self.session, user_id)
            data["role_ids"] = [role.id for role in roles if role.id is not None]
            data["role_name"] = ",".join(role.name for role in roles if role.name)
        else:
            data["role_ids"] = []
            data["role_name"] = ""
        
        return data
    
    # ========== 自定义业务方法 ==========
    
    def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
        """分配用户角色"""
        user = self.session.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        self._replace_user_roles(payload.user_id, payload.role_ids)
        clear_login_caches(payload.user_id)
        self.session.refresh(user)
        return UserListItem.model_validate(self._row_to_dict(user))
    
    def move(self, payload: UserMoveRequest) -> dict:
        """移动用户到其他部门"""
        department = self.session.get(Department, payload.department_id)
        if not department:
            raise HTTPException(status_code=404, detail="部门不存在")
        
        users = list(self.session.exec(
            select(User).where(User.id.in_(payload.user_ids))
        ).all())
        
        for user in users:
            user.department_id = payload.department_id
            self.session.add(user)
        
        self.session.commit()
        
        for user in users:
            clear_login_caches(user.id)
        
        return {"success": True}
    
    # ========== 私有辅助方法 ==========
    
    def _replace_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        """替换用户角色"""
        existing_links = list(self.session.exec(
            select(UserRoleLink).where(UserRoleLink.user_id == user_id)
        ).all())
        
        for link in existing_links:
            self.session.delete(link)
        
        if role_ids:
            roles = list(self.session.exec(
                select(Role).where(Role.id.in_(role_ids))
            ).all())
            
            found_role_ids = {role.id for role in roles if role.id is not None}
            missing_ids = sorted(set(role_ids) - found_role_ids)
            if missing_ids:
                self.session.rollback()
                raise HTTPException(status_code=404, detail=f"角色不存在: {missing_ids}")
            
            for role_id in role_ids:
                self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))
        
        self.session.commit()
```

### 9.2 菜单管理 Service（树形）

```python
"""
菜单管理服务
"""
from collections import defaultdict

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.framework.controller_meta import BaseAdminCrudService, QueryConfig
from app.modules.base.model.auth import (
    Menu,
    MenuCreateRequest,
    MenuExportRequest,
    MenuImportRequest,
    MenuParseRequest,
    MenuRead,
    MenuTreeItem,
    MenuUpdateRequest,
)
from app.modules.base.compat import get_menu_parent_code
from app.modules.base.service.authority_service import (
    clear_login_caches_for_menus,
    get_user_roles,
)


class MenuAdminService(BaseAdminCrudService):
    """菜单资源管理服务"""
    
    def __init__(self, session: Session):
        super().__init__(session, Menu)
    
    # ========== 数据转换 ==========
    
    def _row_to_dict(self, row: Any) -> dict:
        """类型转换 + 补充父级名称"""
        data = super()._row_to_dict(row)
        data["type"] = self._normalize_menu_type_int(data.get("type", "button"))
        
        if data.get("parent_id"):
            parent = self.session.get(Menu, data["parent_id"])
            if parent:
                data["parent_name"] = parent.name
        
        return data
    
    # ========== 自定义业务方法 ==========
    
    def tree(self) -> list[dict]:
        """获取完整的树形结构"""
        return self.list(is_tree=True)
    
    def current_tree(self, current_user: User) -> list[MenuTreeItem]:
        """获取当前用户授权的菜单树"""
        statement = select(Menu).where(Menu.is_active == True)
        
        if not current_user.is_super_admin:
            role_ids = [role.id for role in get_user_roles(self.session, current_user.id) if role.id is not None]
            if not role_ids:
                return []
            statement = (
                select(Menu)
                .join(RoleMenuLink, RoleMenuLink.menu_id == Menu.id)
                .where(RoleMenuLink.role_id.in_(role_ids), Menu.is_active == True)
            )
        
        menus = list(self.session.exec(
            statement.order_by(Menu.sort_order.asc(), Menu.created_at.asc())
        ).all())
        
        navigation_menus = [menu for menu in menus if menu.type in {"menu", "group"} or menu.path]
        expanded = {menu.id: menu for menu in navigation_menus}
        
        for menu in navigation_menus:
            parent_id = menu.parent_id
            while parent_id is not None:
                parent = self.session.get(Menu, parent_id)
                if not parent or not parent.is_active:
                    break
                expanded[parent.id] = parent
                parent_id = parent.parent_id
        
        name_map = {m.id: m.name for m in expanded.values()}
        menu_list = sorted(expanded.values(), key=lambda item: (item.sort_order, item.created_at))
        
        return self._build_tree_with_names(menu_list, name_map)
    
    def _build_tree_with_names(self, menus: list[Menu], name_map: dict[int, str]) -> list[MenuTreeItem]:
        """构建带父级名称的树"""
        nodes = {
            menu.id: MenuTreeItem(**self._build_menu_read(menu, parent_name=name_map.get(menu.parent_id)).model_dump(by_alias=True))
            for menu in menus
        }
        children_map: dict[int | None, list[MenuTreeItem]] = defaultdict(list)
        
        for menu in menus:
            children_map[menu.parent_id].append(nodes[menu.id])
        
        for parent_id, children in children_map.items():
            children.sort(key=lambda item: (item.sort_order, item.created_at))
            if parent_id in nodes:
                nodes[parent_id].children = children
        
        return children_map.get(None, [])
    
    def _build_menu_read(self, menu: Menu, parent_name: str | None = None) -> MenuRead:
        """构建菜单响应对象"""
        return MenuRead.model_validate(menu).model_copy(update={"parent_name": parent_name})
    
    # ========== 类型转换 ==========
    
    @staticmethod
    def _normalize_menu_type_int(value: str | int) -> int:
        """规范化菜单类型为整数"""
        if value in (0, "0", "group", "dir"):
            return 0
        if value in (1, "1", "menu"):
            return 1
        return 2
```

---

## 十、Service 开发检查清单

### 10.1 Service 定义检查

在定义 Service 时，请按以下清单检查：

- [ ] **继承基类**：继承了 `BaseAdminCrudService`
- [ ] **初始化正确**：正确调用了 `super().__init__()`，传入了 `session` 和 `model`
- [ ] **类注释**：添加了清晰的类注释
- [ ] **方法注释**：所有公共方法都有清晰的注释
- [ ] **类型标注**：所有方法参数和返回值都标注了类型

### 10.2 生命周期钩子检查

- [ ] **_before_add**：正确处理了数据验证和默认值
- [ ] **_after_add**：正确处理了关联操作和缓存清理
- [ ] **_before_update**：正确处理了数据验证和特殊字段
- [ ] **_after_update**：正确处理了关联操作和缓存清理
- [ ] **_before_delete**：正确处理了权限检查和依赖检查
- [ ] **_after_delete**：正确处理了关联清理和缓存清理

### 10.3 数据转换检查

- [ ] **_row_to_dict**：只补充业务数据，不做字段名转换
- [ ] **字段命名**：使用 snake_case，与数据库字段一致
- [ ] **禁止转换**：不存在 `data["camelCase"] = data.pop("snake_case")` 的代码
- [ ] **关联数据**：正确补充了关联数据（如 roles, departments）

### 10.4 自定义方法检查

- [ ] **方法命名**：使用动词开头，语义清晰
- [ ] **参数类型**：所有参数都标注了类型
- [ ] **返回类型**：正确标注了返回类型
- [ ] **错误处理**：使用 HTTPException 处理错误情况
- [ ] **事务处理**：正确处理了事务提交和回滚

### 10.5 软删除检查

- [ ] **配置正确**：需要软删除的 Service 配置了 `soft_delete=True`
- [ ] **模型要求**：模型包含 `delete_time` 字段
- [ ] **查询过滤**：查询自动过滤软删除记录
- [ ] **物理删除**：提供了物理删除的方法（如需要）

### 10.6 树形结构检查

- [ ] **配置正确**：配置了 `is_tree=True` 和 `parent_field`
- [ ] **树形方法**：提供了 `tree()` 或 `current_tree()` 方法
- [ ] **数据格式**：返回的树形数据格式正确
- [ ] **父子关系**：正确处理了父子关系

### 10.7 关联查询检查

- [ ] **RelationConfig**：正确配置了关联关系
- [ ] **关联字段**：正确补充了关联数据
- [ ] **性能优化**：使用了预加载或 JOIN 优化查询
- [ ] **空值处理**：正确处理了关联为空的情况

### 10.8 代码质量检查

- [ ] **导入规范**：按标准库、第三方库、本地模块顺序导入
- [ ] **命名规范**：类名大驼峰，方法名小写下划线，变量名小写下划线
- [ ] **注释完整**：类、方法、重要逻辑都有注释
- [ ] **长度控制**：单行代码不超过 100 字符
- [ ] **空行规范**：类之间有两个空行，方法之间有一个空行
- [ ] **异常处理**：正确处理了各种异常情况
- [ ] **日志记录**：重要操作记录了日志

---

## 十一、常见问题

### 11.1 CRUD 方法不生效？

**可能原因**：
1. Service 没有正确继承 `BaseAdminCrudService`
2. `__init__` 没有正确调用 `super().__init__()`
3. 模型参数传递错误

**解决方法**：
```python
# ✅ 正确
class YourService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, YourModel)

# ❌ 错误
class YourService:
    def __init__(self, session: Session):
        self.session = session  # 没有继承基类
```

### 11.2 生命周期钩子没有执行？

**可能原因**：
1. 方法签名与基类不匹配
2. 方法名拼写错误
3. 返回值类型不正确

**解决方法**：
```python
# ✅ 正确
def _before_add(self, data: dict) -> dict:
    return data

# ❌ 错误
def before_add(self, data: dict):  # 缺少下划线
    return data
```

### 11.3 软删除不生效？

**可能原因**：
1. 没有配置 `soft_delete=True`
2. 模型没有 `delete_time` 字段
3. 查询时手动指定了 `soft_delete=False`

**解决方法**：
```python
# 检查配置
super().__init__(session, YourModel, soft_delete=True)

# 检查模型
class YourModel(BaseEntity, table=True):  # BaseEntity 包含 delete_time
    pass
```

### 11.4 关联查询没有数据？

**可能原因**：
1. `RelationConfig` 配置错误
2. 关联字段没有值
3. 没有配置 `relations`

**解决方法**：
```python
# 在 Controller 中配置
@CoolController(
    CoolControllerMeta(
        relations=(
            RelationConfig(
                model=Department,
                column="department_id",
                target_column="name",
                alias="departmentName"
            ),
        ),
    )
)
```

### 11.5 树形结构构建失败？

**可能原因**：
1. 没有配置 `is_tree=True`
2. `parent_field` 配置错误
3. 数据中存在循环引用

**解决方法**：
```python
# 检查配置
super().__init__(session, Menu, is_tree=True, parent_field="parent_id")

# 检查数据
# 确保没有循环引用：A -> B -> C -> A
```

---

## 十二、最佳实践

### 12.1 方法组织

```python
# ✅ 推荐：按功能分组
class UserAdminService(BaseAdminCrudService):
    # ========== 生命周期钩子 ==========
    def _before_add(self, data: dict) -> dict: pass
    def _after_add(self, entity: User, payload: Any) -> None: pass
    
    # ========== 数据转换 ==========
    def _row_to_dict(self, row: Any) -> dict: pass
    
    # ========== CRUD 操作 ==========
    def list(self, query: CrudQuery | None = None) -> list[dict]: pass
    def page(self, query: CrudQuery) -> PageResult[dict]: pass
    
    # ========== 业务操作 ==========
    def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem: pass
    def reset_password(self, user_id: int, new_password: str) -> dict: pass
    
    # ========== 私有辅助方法 ==========
    def _replace_user_roles(self, user_id: int, role_ids: list[int]) -> None: pass
```

### 12.2 错误处理

```python
# ✅ 推荐：明确的错误信息
def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
    user = self.session.get(User, payload.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"用户不存在: {payload.user_id}"
        )
    
    roles = list(self.session.exec(
        select(Role).where(Role.id.in_(payload.role_ids))
    ).all())
    
    if len(roles) != len(payload.role_ids):
        missing = set(payload.role_ids) - {role.id for role in roles}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"角色不存在: {sorted(missing)}"
        )
    
    # 业务逻辑...
```

### 12.3 事务处理

```python
# ✅ 推荐：显式事务控制
def transfer_user(self, user_id: int, from_dept: int, to_dept: int) -> dict:
    """转移用户到新部门"""
    try:
        user = self.session.get(User, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        # 业务逻辑...
        user.department_id = to_dept
        self.session.add(user)
        
        self.session.commit()  # 显式提交
        
        # 清理缓存
        clear_login_caches(user_id)
        
        return {"success": True}
    
    except Exception as e:
        self.session.rollback()  # 显式回滚
        raise HTTPException(status_code=500, detail=str(e))
```

### 12.4 性能优化

```python
# ✅ 推荐：使用预加载
def list_with_departments(self) -> list[dict]:
    """获取用户列表，预加载部门信息"""
    from sqlalchemy.orm import selectinload
    
    users = list(self.session.exec(
        select(User)
        .options(selectinload(User.department))  # 预加载
        .where(User.delete_time == None)
    ).all())
    
    return [self._row_to_dict(user) for user in users]
```

---

## 十三、更新记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-04-21 | 系统 | 初始版本，建立框架 Service 使用规范 |

---

**文档维护**：本规范应随框架演进持续更新。如有疑问或建议，请联系技术负责人。
