# 框架 Controller 使用规范

> 版本：v1.0
> 生效日期：2026-04-21
> 适用范围：所有后端接口开发

---

## 一、概述

本项目采用类似 Cool-Admin-Midway 的装饰器式控制器框架，通过 `@CoolController` 装饰器自动生成标准 CRUD 接口，并支持自定义业务接口。

### 1.1 核心特性

1. **自动化 CRUD** - 自动生成标准增删改查接口
2. **声明式配置** - 通过元数据配置查询、排序、关联等规则
3. **权限自动注册** - 自动注册权限点，无需手动配置
4. **路由自动生成** - 统一路由格式，自动生成 API 文档
5. **树形结构支持** - 内置树形数据结构处理

### 1.2 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                    Controller 层架构                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  @CoolController 装饰器                                       │
│       ↓                                                     │
│  自动生成 CRUD 路由 + 自定义路由                              │
│       ↓                                                     │
│  FastAPI Router                                            │
│       ↓                                                     │
│  权限注册 + EPS 导出                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Controller 类名 | `{模块}Controller` | `BaseUserController` |
| Service 类名 | `{资源}AdminService` | `UserAdminService` |
| 文件名 | `{模块}.py` 或 `{资源}.py` | `user.py` |
| 路由路径 | `/{scope}/{module}/{resource}` | `/admin/base/sys/user` |

---

## 二、@CoolController 装饰器规范

### 2.1 基础结构

```python
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
)

@CoolController(
    CoolControllerMeta(
        module="base",           # 模块名
        resource="sys/user",     # 资源名 (支持嵌套)
        scope="admin",           # 作用域 (admin/app/api等)
        service=UserAdminService, # Service 类
    )
)
class BaseUserController(BaseController):
    """用户控制器"""
    pass

router = BaseUserController.router  # 导出路由
```

### 2.2 元数据配置详解

#### 2.2.1 核心配置

| 参数 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| `module` | `str` | ✅ | 模块名，用于权限标识 | `"base"` |
| `resource` | `str` | ✅ | 资源名，支持嵌套 | `"sys/user"` |
| `scope` | `str` | ✅ | 作用域，影响路由前缀 | `"admin"` |
| `service` | `type` | ✅ | Service 类 | `UserAdminService` |
| `controller_name` | `str` | ❌ | 控制器名称，自动生成 | 默认: `SysUserController` |
| `description` | `str` | ❌ | 描述信息 | `"用户管理"` |

#### 2.2.2 标签与权限

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tags` | `tuple[str, ...]` | `()` | API 文档标签 |
| `name_prefix` | `str` | `""` | 权限名称前缀 |
| `code_prefix` | `str` | `""` | 权限编码前缀 |
| `role_codes` | `tuple[str, ...]` | `("admin",)` | 允许的角色 |

#### 2.2.3 CRUD 动作配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `actions` | `tuple` | `DEFAULT_CRUD_ACTIONS` | 启用的 CRUD 动作 |
| `api` | `tuple` | `None` | actions 的别名 |

**默认 CRUD 动作**：
```python
DEFAULT_CRUD_ACTIONS = (
    "list",   # 获取列表 (POST /list)
    "page",   # 获取分页 (POST /page)
    "info",   # 获取详情 (GET /info)
    "add",    # 新增 (POST /add)
    "update", # 更新 (POST /update)
    "delete", # 删除 (POST /delete)
)
```

#### 2.2.4 模型配置

| 参数 | 类型 | 说明 |
|------|------|------|
| `list_response_model` | `Pydantic Model` | list 接口返回模型 |
| `page_item_model` | `Pydantic Model` | page 接口数据项模型 |
| `info_response_model` | `Pydantic Model` | info 接口返回模型 |
| `info_param_type` | `type` | info 接口参数类型 (int/str) |
| `add_request_model` | `Pydantic Model` | add 接口请求模型 |
| `add_response_model` | `Pydantic Model` | add 接口返回模型 |
| `update_request_model` | `Pydantic Model` | update 接口请求模型 |
| `update_response_model` | `Pydantic Model` | update 接口返回模型 |
| `delete_request_model` | `Pydantic Model` | delete 接口请求模型 |

#### 2.2.5 查询配置

| 参数 | 类型 | 说明 |
|------|------|------|
| `list_query` | `QueryConfig` | list 接口查询配置 |
| `page_query` | `QueryConfig` | page 接口查询配置 |

#### 2.2.6 高级配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `soft_delete` | `bool` | `False` | 是否启用软删除 |
| `is_tree` | `bool` | `False` | 是否是树形结构 |
| `parent_field` | `str` | `"parentId"` | 树形结构的父字段 |
| `relations` | `tuple[RelationConfig, ...]` | `()` | 关联查询配置 |
| `entity` | `Any` | `None` | 实体模型 |
| `before_hooks` | `tuple` | `()` | 前置钩子 |
| `insert_params` | `tuple` | `()` | 参数注入 |
| `service_apis` | `tuple` | `()` | Service 方法暴露 |

### 2.3 完整配置示例

```python
@CoolController(
    CoolControllerMeta(
        # 核心配置
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        description="用户管理",
        
        # 标签与权限
        tags=("base", "user"),
        name_prefix="用户",
        code_prefix="base_sys_user",
        role_codes=("admin", "task_operator"),
        
        # 模型配置
        list_response_model=UserListItem,
        page_item_model=UserListItem,
        info_response_model=UserInfoItem,
        info_param_type=int,
        add_request_model=UserCreateRequest,
        add_response_model=UserListItem,
        update_request_model=UserUpdateRequest,
        update_response_model=UserListItem,
        delete_request_model=DeleteRequest,
        info_ignore_property=("password_version",),
        
        # 查询配置
        list_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email"),
            field_eq=("department_id", "is_active"),
            field_like=("username", "email"),
            select=("id", "username", "full_name", "email"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email"),
            field_eq=("department_id", "is_active"),
            field_like=("username", "email"),
            select=("id", "username", "full_name", "email"),
            order_fields=("created_at", "updated_at"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        
        # 高级配置
        soft_delete=True,
        is_tree=False,
        relations=(
            RelationConfig(
                model=Department,
                column="department_id",
                target_column="name",
                alias="departmentName"
            ),
        ),
        
        # 启用的 CRUD 动作
        actions=("list", "page", "info", "add", "update", "delete"),
    )
)
class BaseUserController(BaseController):
    """用户控制器"""
    pass

router = BaseUserController.router
```

---

## 三、QueryConfig 查询配置规范

### 3.1 QueryConfig 参数

```python
@dataclass
class QueryConfig:
    # 关键字搜索
    keyword_like_fields: tuple[str, ...]  # 关键字模糊搜索字段
    keyword_fields: tuple[str, ...]       # keyword_fields 的别名
    
    # 等值过滤
    field_eq: tuple[str | QueryFieldConfig, ...]  # 等值字段
    eq_filters: tuple[str, ...]                    # eq_filters 的别名
    
    # 模糊过滤
    field_like: tuple[str | QueryFieldConfig, ...]  # 模糊字段
    like_filters: tuple[str, ...]                    # like_filters 的别名
    
    # 排序
    add_order_by: tuple[OrderByConfig, ...]  # 额外排序规则
    order_fields: tuple[str, ...]            # 允许排序的字段
    default_order: str | None                # 默认排序字段
    default_sort: str = "desc"               # 默认排序方向
    
    # 其他
    where: Any | None          # 自定义 where 条件
    select: tuple[str, ...]    # 选择的字段
```

### 3.2 QueryFieldConfig 字段配置

用于映射前端参数名到数据库字段名：

```python
@dataclass
class QueryFieldConfig:
    column: str              # 数据库字段名
    request_param: str | None = None  # 前端参数名 (默认=column)
```

**示例**：
```python
QueryConfig(
    # 简写形式：前端参数名 = 数据库字段名
    field_eq=("department_id", "is_active"),
    
    # 完整形式：映射前端参数名到数据库字段名
    field_eq=(
        QueryFieldConfig("department_id", "departmentIds"),  # departmentIds → department_id
        QueryFieldConfig("is_active", "status"),             # status → is_active
    ),
)
```

### 3.3 OrderByConfig 排序配置

```python
@dataclass
class OrderByConfig:
    column: str           # 排序字段
    direction: str = "desc"  # 排序方向: asc/desc
```

**示例**：
```python
QueryConfig(
    add_order_by=(
        OrderByConfig("created_at", "desc"),  # 按创建时间倒序
        OrderByConfig("sort_order", "asc"),   # 按排序字段正序
    ),
)
```

### 3.4 查询配置示例

```python
QueryConfig(
    # 关键字搜索：在以下字段中模糊匹配关键字
    keyword_like_fields=("username", "full_name", "email", "phone"),
    
    # 等值过滤：精确匹配
    field_eq=(
        QueryFieldConfig("department_id", "departmentId"),  # 前端传 departmentId
        QueryFieldConfig("is_active", "status"),           # 前端传 status
    ),
    
    # 模糊过滤：单独的模糊匹配
    field_like=("username", "email"),
    
    # 字段选择：只返回指定字段
    select=(
        "id", "username", "full_name", "email", "phone",
        "department_id", "is_active", "created_at"
    ),
    
    # 排序：默认按创建时间倒序，允许前端指定排序字段
    order_fields=("created_at", "updated_at", "username"),
    default_order="created_at",
    default_sort="desc",
    add_order_by=(OrderByConfig("created_at", "desc"),),
)
```

### 3.5 前端调用示例

```javascript
// 关键字搜索
POST /admin/base/sys/user/page
{
  "page": 1,
  "size": 10,
  "keyword": "admin"  // 在 username, full_name, email, phone 中模糊搜索
}

// 等值过滤
POST /admin/base/sys/user/page
{
  "page": 1,
  "size": 10,
  "status": 1,          // → is_active = 1
  "departmentId": 1     // → department_id = 1
}

// 排序
POST /admin/base/sys/user/page
{
  "page": 1,
  "size": 10,
  "order": "username",  // 按 username 排序
  "sort": "asc"         // 升序
}
```

---

## 四、RelationConfig 关联查询规范

### 4.1 RelationConfig 参数

```python
@dataclass
class RelationConfig:
    model: Any          # 目标模型类
    column: str         # 当前模型的关联字段
    target_column: str  # 目标模型要选取的字段
    alias: str          # 输出到 JSON 的别名
```

### 4.2 使用示例

```python
# 用户关联部门
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        relations=(
            RelationConfig(
                model=Department,        # 目标模型
                column="department_id",   # User 的 department_id 字段
                target_column="name",    # 选取 Department 的 name 字段
                alias="departmentName"   # 输出为 departmentName
            ),
        ),
    )
)
class BaseUserController(BaseController):
    pass
```

### 4.3 返回数据示例

```json
{
  "id": 1,
  "username": "admin",
  "departmentId": 1,
  "departmentName": "技术部",  // 自动关联查询
  "email": "admin@example.com"
}
```

### 4.4 多个关联示例

```python
relations=(
    RelationConfig(
        model=Department,
        column="department_id",
        target_column="name",
        alias="departmentName"
    ),
    RelationConfig(
        model=Role,
        column="role_id",
        target_column="name",
        alias="roleName"
    ),
)
```

---

## 五、自定义路由规范

### 5.1 使用 @Get 和 @Post 装饰器

```python
from app.framework.router.route_meta import Get, Post

@CoolController(...)
class BaseUserController(BaseController):
    
    @Get(
        "/me",
        summary="获取当前用户信息",
        permission="base:sys:user:me",
        role_codes=("admin", "task_operator"),
    )
    async def get_me(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> CoolUserInfo:
        service = AuthService(session)
        return service.get_current_profile(current_user)
    
    @Post(
        "/assignRoles",
        summary="分配用户角色",
        permission="base:sys:user:assign_roles",
    )
    async def assign_roles(
        self,
        payload: UserRoleAssignRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> UserListItem:
        service = UserAdminService(session)
        return service.assign_roles(payload)
```

### 5.2 路由元数据

```python
@dataclass
class CoolRouteMeta:
    method: str                      # HTTP 方法: GET/POST/PUT/DELETE
    path: str                        # 路由路径
    summary: str | None = None       # 接口摘要
    permission: str | None = None    # 权限标识
    role_codes: tuple[str, ...]      # 允许的角色
    tags: tuple[str, ...] = ()       # API 文档标签
    anonymous: bool = False          # 是否匿名访问
```

### 5.3 匿名接口

```python
from app.framework.router.route_meta import allow_anonymous

@Get(
    "/public",
    summary="公开接口",
    anonymous=True,  # 允许匿名访问
)
async def public_endpoint() -> dict:
    return {"message": "Public access"}
```

### 5.4 路由生成规则

自定义路由的完整路径为：`/{scope}/{module}/{resource}{path}`

```python
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",
        scope="admin",
    )
)
class BaseUserController(BaseController):
    
    @Get("/me", ...)  # 完整路径: /admin/base/sys/user/me
    async def get_me(self) -> dict:
        pass
```

---

## 六、树形结构规范

### 6.1 启用树形结构

```python
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/menu",
        scope="admin",
        service=MenuAdminService,
        is_tree=True,           # 启用树形结构
        parent_field="parent_id", # 父字段名
    )
)
class BaseMenuController(BaseController):
    pass
```

### 6.2 Service 层处理

Service 层需要实现 `_to_tree` 方法或使用内置处理：

```python
class MenuAdminService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, Menu, is_tree=True, parent_field="parent_id")
    
    # 基类已提供 _to_tree 方法，自动构建树形结构
```

### 6.3 返回数据格式

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

## 七、软删除规范

### 7.1 启用软删除

```python
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        soft_delete=True,  # 启用软删除
    )
)
class BaseUserController(BaseController):
    pass
```

### 7.2 数据模型要求

模型需要包含 `delete_time` 字段：

```python
from app.framework.models.entity import BaseEntity

class User(BaseEntity, table=True):
    # BaseEntity 已包含 delete_time 字段
    username: str
    # ...
```

### 7.3 删除行为

- **软删除**：设置 `delete_time = 当前时间`，数据仍保留在数据库
- **查询过滤**：自动过滤 `delete_time IS NULL` 的记录
- **恢复支持**：可以通过清除 `delete_time` 恢复数据

---

## 八、Service 方法暴露规范

### 8.1 配置 service_apis

将 Service 的方法直接暴露为 HTTP 接口：

```python
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        service_apis=(
            "customMethod",  # 简写形式
            ServiceApiConfig(
                method="anotherMethod",
                summary="另一个方法",
                permission="base:sys:user:another",
                role_codes=("admin",),
            ),
        ),
    )
)
class BaseUserController(BaseController):
    pass
```

### 8.2 Service 方法定义

```python
class UserAdminService(BaseAdminCrudService):
    def customMethod(self, payload: dict) -> dict:
        """自定义方法，会自动暴露为 HTTP 接口"""
        return {"result": "success"}
    
    def anotherMethod(self, params: dict) -> dict:
        """另一个方法"""
        return {"data": params}
```

### 8.3 生成的接口

- `/admin/base/sys/user/customMethod` (POST)
- `/admin/base/sys/user/anotherMethod` (POST)

---

## 九、完整示例

### 9.1 用户管理控制器

```python
"""
Base 模块用户控制器
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.modules.base.model.auth import (
    CoolUserInfo,
    Department,
    DeleteRequest,
    PageResult,
    User,
    UserListItem,
    UserInfoItem,
    UserCreateRequest,
    UserUpdateRequest,
    UserRoleAssignRequest,
    UserMoveRequest,
)
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
    QueryFieldConfig,
    RelationConfig,
)
from app.modules.base.service.admin_service import UserAdminService
from app.modules.base.service.auth_service import AuthService
from app.modules.base.service.security_service import get_current_user
from app.framework.router.route_meta import Get, Post


@CoolController(
    CoolControllerMeta(
        # 核心配置
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        
        # 标签与权限
        tags=("base", "user"),
        name_prefix="用户",
        code_prefix="base_sys_user",
        role_codes=("admin", "task_operator"),
        
        # 模型配置
        list_response_model=UserListItem,
        page_item_model=UserListItem,
        info_response_model=UserInfoItem,
        info_param_type=int,
        add_request_model=UserCreateRequest,
        add_response_model=UserListItem,
        update_request_model=UserUpdateRequest,
        update_response_model=UserListItem,
        delete_request_model=DeleteRequest,
        info_ignore_property=("password_version",),
        
        # 查询配置
        list_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email", "phone", "nick_name"),
            field_eq=(
                QueryFieldConfig("department_id", "departmentId"),
                QueryFieldConfig("is_active", "status")
            ),
            field_like=("username", "full_name", "nick_name", "email", "phone"),
            select=(
                "id", "username", "full_name", "nick_name", "head_img",
                "email", "phone", "remark", "department_id", "is_active",
                "created_at", "updated_at"
            ),
            order_fields=("created_at", "updated_at", "username"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        page_query=QueryConfig(
            keyword_like_fields=("username", "full_name", "email", "phone", "nick_name"),
            field_eq=(
                QueryFieldConfig("department_id", "departmentId"),
                QueryFieldConfig("is_active", "status")
            ),
            field_like=("username", "full_name", "nick_name", "email", "phone"),
            select=(
                "id", "username", "full_name", "nick_name", "head_img",
                "email", "phone", "remark", "department_id", "is_active",
                "created_at", "updated_at"
            ),
            order_fields=("created_at", "updated_at", "username"),
            add_order_by=(OrderByConfig("created_at", "desc"),),
        ),
        
        # 高级配置
        soft_delete=True,
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
class BaseUserController(BaseController):
    """用户控制器"""
    
    @Get(
        "/me",
        summary="获取当前登录用户信息",
        permission="base:sys:user:me",
        role_codes=("admin", "task_operator"),
    )
    async def get_me(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> CoolUserInfo:
        """获取当前登录用户信息"""
        service = AuthService(session)
        return service.get_current_profile(current_user)
    
    @Post(
        "/assignRoles",
        summary="分配用户角色",
        permission="base:sys:user:assign_roles",
    )
    async def assign_roles(
        self,
        payload: UserRoleAssignRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> UserListItem:
        """分配用户角色"""
        service = UserAdminService(session)
        return service.assign_roles(payload)
    
    @Post(
        "/move",
        summary="移动部门",
        permission="base:sys:user:move",
    )
    async def move(
        self,
        payload: UserMoveRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """移动用户到其他部门"""
        service = UserAdminService(session)
        return service.move(payload)


router = BaseUserController.router
```

### 9.2 菜单管理控制器（树形结构）

```python
"""
Base 模块菜单控制器
"""
from fastapi import Depends
from sqlmodel import Session

from app.core.database import get_session
from app.modules.base.model.auth import (
    DeleteRequest,
    Menu,
    MenuCreateRequest,
    MenuExportRequest,
    MenuImportRequest,
    MenuParseRequest,
    MenuParseResponse,
    MenuRead,
    MenuTreeItem,
    MenuUpdateRequest,
    PageResult,
    User,
)
from app.framework.controller_meta import (
    BaseController,
    CoolController,
    CoolControllerMeta,
    OrderByConfig,
    QueryConfig,
)
from app.modules.base.service.admin_service import MenuAdminService
from app.modules.base.service.security_service import get_current_user
from app.framework.router.route_meta import Get, Post


@CoolController(
    CoolControllerMeta(
        # 核心配置
        module="base",
        resource="sys/menu",
        scope="admin",
        service=MenuAdminService,
        
        # 标签与权限
        tags=("base", "menu"),
        name_prefix="菜单",
        code_prefix="base_sys_menu",
        
        # 模型配置
        list_response_model=MenuRead,
        page_item_model=MenuRead,
        info_response_model=MenuRead,
        add_request_model=MenuCreateRequest,
        add_response_model=MenuRead,
        update_request_model=MenuUpdateRequest,
        update_response_model=MenuRead,
        delete_request_model=DeleteRequest,
        
        # 查询配置
        list_query=QueryConfig(
            keyword_like_fields=("name", "code"),
            field_eq=("type", "is_active"),
            select=(
                "id", "parent_id", "parent_name", "name", "code",
                "type", "path", "component", "icon", "sort_order",
                "is_show", "permission", "is_active"
            ),
            order_fields=("sort_order", "created_at"),
            add_order_by=(OrderByConfig("sort_order", "asc"), OrderByConfig("created_at", "asc")),
        ),
        
        # 树形结构配置
        is_tree=True,
        parent_field="parent_id",
    )
)
class BaseMenuController(BaseController):
    """菜单控制器"""
    
    @Get("/tree", summary="菜单树")
    async def tree(
        self,
        session: Session = Depends(get_session),
        current_user: User = Depends(get_current_user),
    ) -> list[MenuTreeItem]:
        """获取菜单树"""
        service = MenuAdminService(session)
        return service.tree()
    
    @Get(
        "/currentTree",
        summary="当前用户菜单树",
        permission="base:sys:menu:current_tree",
    )
    async def current_tree(
        self,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[MenuTreeItem]:
        """获取当前用户授权的菜单树"""
        service = MenuAdminService(session)
        return service.current_tree(current_user)
    
    @Post(
        "/export",
        summary="导出菜单",
        permission="base:sys:menu:export",
    )
    async def export(
        self,
        payload: MenuExportRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> list[dict]:
        """导出菜单数据"""
        service = MenuAdminService(session)
        return service.export(payload)
    
    @Post(
        "/import",
        summary="导入菜单",
        permission="base:sys:menu:import",
    )
    async def import_menu(
        self,
        payload: MenuImportRequest,
        current_user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
    ) -> dict:
        """导入菜单数据"""
        service = MenuAdminService(session)
        return service.import_menu(payload)
    
    @Post(
        "/parse",
        summary="解析菜单",
        permission="base:sys:menu:parse",
    )
    async def parse(
        self,
        payload: MenuParseRequest,
        current_user: User = Depends(get_current_user),
    ) -> MenuParseResponse:
        """解析控制器生成菜单配置"""
        from app.modules.loader import load_eps_catalog
        service = MenuAdminService(session)
        eps_catalog = load_eps_catalog()
        return MenuParseResponse(
            list=service.parse_menu_candidates(payload, eps_catalog)
        )


router = BaseMenuController.router
```

---

## 十、路由注册规范

### 10.1 在模块中注册路由

```python
# app/modules/base/router.py
from fastapi import APIRouter
from app.modules.base.controller.admin import (
    comm,
    department,
    log,
    login_log,
    menu,
    open,
    param,
    security_log,
    sys,
    user,
)

router = APIRouter()

# 注册各控制器路由
router.include_router(comm.router, prefix="/comm", tags=["base", "comm"])
router.include_router(user.router, prefix="/user", tags=["base", "user"])
router.include_router(role.router, prefix="/role", tags=["base", "role"])
router.include_router(menu.router, prefix="/menu", tags=["base", "menu"])
router.include_router(department.router, prefix="/department", tags=["base", "department"])
# ...
```

### 10.2 在主应用中注册

```python
# main.py
from fastapi import FastAPI
from app.modules.base.router import router as base_router

app = FastAPI()

# 注册模块路由
app.include_router(base_router, prefix="/admin/base")
```

---

## 十一、检查规范

### 11.1 Controller 定义检查清单

在定义 Controller 时，请按以下清单检查：

- [ ] **装饰器使用**：使用了 `@CoolController` 装饰器
- [ ] **核心配置**：正确配置 `module`, `resource`, `scope`, `service`
- [ ] **标签配置**：配置了 `tags` 用于 API 文档分组
- [ ] **权限前缀**：配置了 `name_prefix` 和 `code_prefix`
- [ ] **模型配置**：配置了所有必要的 Request/Response 模型
- [ ] **查询配置**：配置了 `QueryConfig`，使用 `QueryFieldConfig` 映射前端参数
- [ ] **关联配置**：使用了 `RelationConfig` 配置关联查询
- [ ] **软删除**：需要软删除的资源配置了 `soft_delete=True`
- [ ] **树形结构**：树形资源配置了 `is_tree=True` 和 `parent_field`
- [ ] **路由导出**：导出了 `router = XXXController.router`
- [ ] **类注释**：添加了清晰的类注释
- [ ] **方法注释**：自定义方法添加了清晰的注释

### 11.2 自定义路由检查清单

- [ ] **装饰器使用**：使用了 `@Get` 或 `@Post` 装饰器
- [ ] **路径规范**：路径以 `/` 开头，不以 `/` 结尾
- [ ] **权限配置**：配置了 `permission`，遵循 `{module}:{resource}:{action}` 格式
- [ ] **摘要信息**：配置了 `summary`，用于 API 文档
- [ ] **角色限制**：需要限制角色的配置了 `role_codes`
- [ ] **匿名接口**：匿名访问接口配置了 `anonymous=True`
- [ ] **方法签名**：正确使用了 `Depends(get_session)` 和 `Depends(get_current_user)`
- [ ] **返回类型**：正确标注了返回类型
- [ ] **Service 调用**：正确实例化了 Service 类
- [ ] **方法注释**：添加了清晰的方法注释

### 11.3 查询配置检查清单

- [ ] **关键字搜索**：`keyword_like_fields` 配置正确
- [ ] **等值过滤**：使用 `QueryFieldConfig` 映射前端参数到数据库字段
- [ ] **模糊过滤**：`field_like` 配置正确
- [ ] **字段选择**：`select` 配置了需要返回的字段
- [ ] **排序配置**：配置了 `order_fields` 和 `add_order_by`
- [ ] **默认排序**：配置了 `default_order` 和 `default_sort`
- [ ] **字段命名**：使用数据库字段名 (snake_case)
- [ ] **前端参数**：前端参数名使用 camelCase

### 11.4 权限配置检查清单

- [ ] **权限格式**：遵循 `{module}:{resource}:{action}` 格式
- [ ] **权限唯一性**：权限标识全局唯一
- [ ] **角色配置**：正确配置了允许的角色
- [ ] **命名规范**：`name_prefix` 使用中文，`code_prefix` 使用英文下划线

### 11.5 代码质量检查清单

- [ ] **导入规范**：按标准库、第三方库、本地模块顺序导入
- [ ] **命名规范**：类名使用大驼峰，变量名使用小写下划线
- [ ] **注释完整**：类、方法、重要逻辑都有注释
- [ ] **错误处理**：Service 层正确处理了异常
- [ ] **类型标注**：所有方法参数和返回值都标注了类型
- [ ] **长度控制**：单行代码不超过 100 字符
- [ ] **空行规范**：类、方法之间有两个空行

### 11.6 测试检查清单

- [ ] **CRUD 接口**：测试了所有 CRUD 接口
- [ ] **自定义接口**：测试了所有自定义接口
- [ ] **查询功能**：测试了关键字搜索、过滤、排序
- [ ] **关联查询**：测试了关联数据是否正确返回
- [ ] **权限验证**：测试了权限控制是否生效
- [ ] **边界情况**：测试了空数据、错误输入等边界情况

---

## 十二、常见问题

### 12.1 CRUD 接口没有生成？

**可能原因**：
1. Service 类缺少对应的方法（`list`, `page`, `info`, `add`, `update`, `delete`）
2. 方法签名与基类不匹配

**解决方法**：
```python
# 确保 Service 继承自 BaseAdminCrudService
class YourService(BaseAdminCrudService):
    def __init__(self, session: Session):
        super().__init__(session, YourModel)
    # 基类已提供 CRUD 方法
```

### 12.2 查询参数不生效？

**可能原因**：
1. `QueryConfig` 配置错误
2. 前端参数名与 `QueryFieldConfig` 不匹配

**解决方法**：
```python
# 检查配置
QueryConfig(
    field_eq=(
        QueryFieldConfig("department_id", "departmentId"),  # 确保前端传 departmentId
    ),
)
```

### 12.3 关联查询没有返回数据？

**可能原因**：
1. `RelationConfig` 配置错误
2. 关联字段没有值

**解决方法**：
```python
# 检查配置
RelationConfig(
    model=Department,        # 确保模型正确
    column="department_id",   # 确保字段名正确
    target_column="name",    # 确保目标字段存在
    alias="departmentName"   # 确保别名正确
)
```

### 12.4 权限没有生效？

**可能原因**：
1. 权限标识格式错误
2. 用户没有分配对应角色

**解决方法**：
```python
# 检查权限格式
permission = "base:sys:user:list"  # 格式: module:resource:action
```

### 12.5 树形结构返回错误？

**可能原因**：
1. `is_tree` 配置错误
2. `parent_field` 配置错误
3. 数据中存在循环引用

**解决方法**：
```python
# 检查配置
is_tree=True,
parent_field="parent_id",  # 确保与数据库字段名一致
```

---

## 十三、最佳实践

### 13.1 命名规范

```python
# ✅ 推荐
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sys/user",      # 使用 / 分隔层级
        scope="admin",
        service=UserAdminService,
    )
)
class BaseUserController(BaseController):
    pass

# ❌ 不推荐
@CoolController(
    CoolControllerMeta(
        module="base",
        resource="sysUser",       # 不要用驼峰
        scope="admin",
        service=UserAdminService,
    )
)
class userController(BaseController):  # 类名不要小写开头
    pass
```

### 13.2 配置组织

```python
# ✅ 推荐：配置分组清晰
@CoolController(
    CoolControllerMeta(
        # 核心配置
        module="base",
        resource="sys/user",
        scope="admin",
        service=UserAdminService,
        
        # 标签与权限
        tags=("base", "user"),
        name_prefix="用户",
        code_prefix="base_sys_user",
        
        # 模型配置
        list_response_model=UserListItem,
        # ...
    )
)
```

### 13.3 自定义路由组织

```python
# ✅ 推荐：按功能分组
class BaseUserController(BaseController):
    # ========== CRUD 自定义 ==========
    
    # ========== 关联操作 ==========
    @Post("/assignRoles", ...)
    async def assign_roles(self, ...): pass
    
    # ========== 业务操作 ==========
    @Post("/move", ...)
    async def move(self, ...): pass
    
    # ========== 查询操作 ==========
    @Get("/me", ...)
    async def get_me(self, ...): pass
```

### 13.4 错误处理

```python
# ✅ 推荐：Service 层统一错误处理
class UserAdminService(BaseAdminCrudService):
    def assign_roles(self, payload: UserRoleAssignRequest) -> UserListItem:
        user = self.session.get(User, payload.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        
        # 业务逻辑...
        return user
```

---

## 十四、更新记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-04-21 | 系统 | 初始版本，建立框架 Controller 使用规范 |

---

**文档维护**：本规范应随框架演进持续更新。如有疑问或建议，请联系技术负责人。
