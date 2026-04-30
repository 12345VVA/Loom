# 框架 Model 使用规范

> 版本：v1.0
> 生效日期：2026-04-21
> 适用范围：所有后端 Model 层开发

---

## 一、概述

Model 层是数据模型的定义层，负责定义数据库表结构、请求/响应模型、数据验证规则等。本项目基于 **SQLModel** 和 **Pydantic** 构建，统一使用 `snake_case` 命名，通过 `alias_generator` 自动转换为前端期望的 `camelCase`。

### 1.1 核心特性

1. **统一命名** - 所有字段使用 `snake_case`，自动转换为 `camelCase`
2. **类型安全** - 完整的类型标注和运行时验证
3. **自动转换** - 通过 `alias_generator` 实现字段名自动转换
4. **类型转换** - 使用 `@field_validator` 和 `@field_serializer` 处理类型转换
5. **双向兼容** - 使用 `populate_by_name=True` 同时接受两种命名格式

### 1.2 Model 分类

| 类型 | 基类 | 用途 | 文件位置 |
|------|------|------|----------|
| **Entity Model** | `BaseEntity` | 数据库表定义 | `model/*.py` |
| **Request Model** | `BaseModel` | 请求参数验证 | `model/*.py` |
| **Response Model** | `BaseModel` | 响应数据定义 | `model/*.py` |
| **Link Model** | `BaseEntity` | 多对多关联表 | `model/*.py` |

### 1.3 架构层次

```
┌─────────────────────────────────────────────────────────────┐
│                      Model 层架构                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Request Model (Pydantic) → 验证 & 解析                     │
│       ↓                                                     │
│  Service Layer → 业务逻辑                                    │
│       ↓                                                     │
│  Entity Model (SQLModel) → 数据库操作                        │
│       ↓                                                     │
│  Response Model (Pydantic) → 序列化 & 转换                   │
│       ↓                                                     │
│  前端 (camelCase)                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| Entity 类名 | `{名称}` | `User`, `Department`, `Menu` |
| Request 类名 | `{资源}{操作}Request` | `UserCreateRequest`, `MenuUpdateRequest` |
| Response 类名 | `{资源}{类型}` | `UserListItem`, `MenuRead` |
| Link 类名 | `{资源1}{资源2}Link` | `UserRoleLink`, `RoleMenuLink` |
| 文件名 | `{模块}.py` 或 `{资源}.py` | `auth.py`, `user.py` |

---

## 二、Entity Model 规范

### 2.1 BaseEntity 基类

```python
class BaseEntity(SQLModel):
    """通用基类模型，包含 ID 和自动时间戳"""
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    delete_time: Optional[datetime] = Field(default=None, index=True)
```

### 2.2 Entity Model 定义

```python
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity

class User(BaseEntity, table=True):
    """用户表"""
    
    __tablename__ = "sys_user"
    
    # 基础字段
    username: str = Field(index=True, unique=True)
    full_name: str
    nick_name: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True, unique=True)
    
    # 类型字段
    is_active: bool = Field(default=True)
    is_super_admin: bool = Field(default=False)
    
    # 关联字段
    department_id: Optional[int] = Field(default=None, foreign_key="department_id")
    
    # 敏感字段
    password_hash: str
    password_version: int = Field(default=1)
    password_changed_at: Optional[datetime] = None
```

### 2.3 字段定义规范

| 参数 | 用途 | 示例 |
|------|------|------|
| `index` | 创建索引 | `Field(index=True)` |
| `unique` | 唯一约束 | `Field(unique=True)` |
| `default` | 默认值 | `Field(default=0)` |
| `default_factory` | 动态默认值 | `Field(default_factory=datetime.utcnow)` |
| `foreign_key` | 外键 | `Field(foreign_key="department_id")` |
| `nullable` | 可为空 | `Field(default=None)` |

### 2.4 完整示例

```python
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship
from app.framework.models.entity import BaseEntity

class User(BaseEntity, table=True):
    """用户表"""
    
    __tablename__ = "sys_user"
    
    # ========== 基本信息 ==========
    username: str = Field(index=True, unique=True, max_length=50)
    full_name: str = Field(max_length=100)
    nick_name: Optional[str] = Field(default=None, max_length=50)
    
    # ========== 联系方式 ==========
    email: Optional[str] = Field(default=None, index=True, unique=True, max_length=100)
    phone: Optional[str] = Field(default=None, max_length=20)
    head_img: Optional[str] = Field(default=None, max_length=500)
    
    # ========== 状态字段 ==========
    is_active: bool = Field(default=True)
    is_super_admin: bool = Field(default=False)
    is_manager: bool = Field(default=False)
    is_department_leader: bool = Field(default=False)
    
    # ========== 部门关联 ==========
    department_id: Optional[int] = Field(default=None, foreign_key="sys_department.id")
    department: Optional["Department"] = Relationship(back_populates="users")
    
    # ========== 认证信息 ==========
    password_hash: str
    password_version: int = Field(default=1)
    password_changed_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    
    # ========== 备注 ==========
    remark: Optional[str] = Field(default=None, max_length=500)
```

### 2.5 Link Model 定义

```python
class UserRoleLink(BaseEntity, table=True):
    """用户角色关联表"""
    
    __tablename__ = "sys_user_role"
    
    user_id: int = Field(index=True, foreign_key="sys_user.id")
    role_id: int = Field(index=True, foreign_key="sys_role.id")
    
    # 关系定义（可选）
    user: Optional["User"] = Relationship(back_populates="role_links")
    role: Optional["Role"] = Relationship(back_populates="user_links")
```

---

## 三、Request Model 规范

### 3.1 基础配置

所有 Request 模型必须包含以下配置：

```python
from pydantic import BaseModel, ConfigDict
from app.framework.api.naming import resolve_alias

class YourCreateRequest(BaseModel):
    """创建资源请求"""
    
    model_config = ConfigDict(
        populate_by_name=True,        # 允许同时接受 snake_case 和 camelCase
        alias_generator=resolve_alias, # 自动生成别名
    )
    
    # 字段定义...
```

### 3.2 字段定义规范

**字段名必须使用 snake_case**，与 Entity Model 保持一致：

```python
# ✅ 正确
class UserCreateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    username: str
    full_name: str
    nick_name: str = ""
    department_id: Optional[int] = None
    role_ids: list[int] = []
    is_active: bool = True

# ❌ 错误
class UserCreateRequest(BaseModel):
    username: str
    fullName: str        # ❌ 不要用 camelCase
    deptId: int          # ❌ 不要用语义别名
    isActive: bool       # ❌ 不要用 camelCase
```

这个规则同样适用于系统参数、日志等兼容 Loom 的模型。即使前端字段是 `keyName`、`dataType`、`createTime`，模型内部也应定义为 `key_name`、`data_type`、`created_at`，由 `alias_generator=resolve_alias` 负责输入输出转换。

### 3.3 字段验证

使用 `@field_validator` 进行数据验证：

```python
from pydantic import field_validator

class UserCreateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    username: str
    password: str
    email: Optional[str] = None
    
    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """去除前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v
    
    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """验证邮箱格式"""
        if v and "@" not in v:
            raise ValueError("邮箱格式不正确")
        return v
```

### 3.4 类型转换

处理前端传来的不同类型数据：

```python
class UserCreateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    is_active: bool = True
    
    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        """接受 status (0/1) 或 is_active (true/false)"""
        if isinstance(v, int):
            return v == 1
        return bool(v)
```

### 3.5 嵌套模型

```python
class AddressModel(BaseModel):
    """地址模型"""
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    province: str
    city: str
    address: str

class UserCreateRequest(BaseModel):
    """创建用户请求"""
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    username: str
    address: Optional[AddressModel] = None
```

### 3.6 完整示例

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field as PydanticField, field_validator
from app.framework.api.naming import resolve_alias

class UserCreateRequest(BaseModel):
    """创建用户请求"""
    
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    # ========== 基本信息 ==========
    username: str
    full_name: str
    nick_name: str = ""
    
    # ========== 认证信息 ==========
    password: str
    password_changed_at: Optional[datetime] = None
    
    # ========== 联系方式 ==========
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    head_img: Optional[str] = None
    
    # ========== 组织信息 ==========
    department_id: Optional[int] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    
    # ========== 状态 ==========
    is_active: bool = True
    is_super_admin: bool = False
    is_manager: bool = False
    is_department_leader: bool = False
    
    # ========== 备注 ==========
    remark: Optional[str] = None
    
    # ========== 验证器 ==========
    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """去除用户名和密码的前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v
    
    @field_validator("is_active", "is_super_admin", "is_manager", "is_department_leader", mode="before")
    @classmethod
    def parse_boolean(cls, v):
        """解析布尔值"""
        if isinstance(v, int):
            return v == 1
        return bool(v)
```

---

## 四、Response Model 规范

### 4.1 基础配置

所有 Response 模型必须包含以下配置：

```python
from pydantic import BaseModel, ConfigDict
from app.framework.api.naming import resolve_alias

class YourRead(BaseModel):
    """资源响应"""
    
    model_config = ConfigDict(
        from_attributes=True,       # 支持从 ORM 模型创建
        populate_by_name=True,       # 允许内部使用 snake_case
        alias_generator=resolve_alias, # 自动生成序列化别名
    )
    
    # 字段定义...
```

### 4.2 字段定义规范

**字段名必须使用 snake_case**，序列化时自动转换为 camelCase：

```python
# ✅ 正确
class UserListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    id: int
    username: str
    full_name: str
    department_id: Optional[int] = None
    is_active: bool = True
    created_at: datetime

# ❌ 错误
class UserListItem(BaseModel):
    id: int
    username: str
    fullName: str        # ❌ 不要用 camelCase
    deptId: int          # ❌ 不要用语义别名
    isActive: bool       # ❌ 不要用 camelCase
```

### 4.3 类型序列化

使用 `@field_serializer` 处理类型转换：

```python
from pydantic import field_serializer

class UserListItem(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    is_active: bool = True
    created_at: datetime
    
    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        """将 bool 转换为前端期望的 0/1"""
        return 1 if v else 0
    
    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        """格式化时间为 ISO 字符串"""
        return v.isoformat() if v else None
```

### 4.4 计算字段

使用 `@computed_field` 定义动态计算的字段：

```python
from pydantic import computed_field

class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    first_name: str
    last_name: str
    
    @computed_field
    @property
    def full_name(self) -> str:
        """动态计算的全名字段"""
        return f"{self.first_name} {self.last_name}"
```

### 4.5 继承规范

子类自动继承父类的 `alias_generator` 配置：

```python
class UserListItem(BaseModel):
    """用户列表项"""
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    id: int
    username: str
    # ... 其他字段

class UserInfoItem(UserListItem):
    """用户详细信息（继承列表项）"""
    password_version: Optional[int] = None  # 自动继承配置
```

### 4.6 完整示例

```python
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field as PydanticField, field_serializer
from app.framework.api.naming import resolve_alias

class UserListItem(BaseModel):
    """用户列表项"""
    
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    # ========== 基本信息 ==========
    id: int
    username: str
    full_name: str
    nick_name: Optional[str] = None
    head_img: Optional[str] = None
    
    # ========== 联系方式 ==========
    email: Optional[str] = None
    phone: Optional[str] = None
    
    # ========== 组织信息 ==========
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    role_name: Optional[str] = None
    
    # ========== 状态 ==========
    is_active: bool = True
    
    # ========== 时间戳 ==========
    created_at: datetime
    updated_at: datetime
    
    # ========== 序列化器 ==========
    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        """bool → int (0/1)"""
        return 1 if v else 0
    
    @field_serializer("created_at")
    def serialize_created_at(self, v: datetime) -> str:
        """格式化时间"""
        return v.isoformat() if v else None
    
    @field_serializer("updated_at")
    def serialize_updated_at(self, v: datetime) -> str:
        """格式化时间"""
        return v.isoformat() if v else None


class UserInfoItem(UserListItem):
    """用户详细信息（继承列表项）"""
    
    password_version: Optional[int] = PydanticField(default=None)
```

---

## 五、特殊字段类型规范

### 5.1 枚举类型

```python
from enum import Enum
from pydantic import BaseModel, ConfigDict
from app.framework.api.naming import resolve_alias

class UserStatus(str, Enum):
    """用户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    BANNED = "banned"

class UserCreateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    status: UserStatus = UserStatus.ACTIVE


class UserRead(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    status: UserStatus
```

### 5.2 日期时间类型

```python
from datetime import datetime

class YourModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    # 使用 datetime 类型
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None
    
    # 序列化时自动转换为 ISO 格式字符串
```

### 5.3 密码字段

```python
class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    old_password: str
    new_password: str
    confirm_password: str
    
    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """验证密码强度"""
        if len(v) < 8:
            raise ValueError("密码长度至少为 8 位")
        if not any(c.isupper() for c in v):
            raise ValueError("密码必须包含至少一个大写字母")
        return v
    
    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        """确认密码匹配"""
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("两次输入的密码不一致")
        return v
```

### 5.4 文件上传字段

```python
class FileUploadRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    file_name: str
    file_size: int
    file_type: str
    
    @field_validator("file_size")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        """验证文件大小（最大 10MB）"""
        max_size = 10 * 1024 * 1024
        if v > max_size:
            raise ValueError("文件大小不能超过 10MB")
        return v
    
    @field_validator("file_type")
    @classmethod
    def validate_file_type(cls, v: str) -> str:
        """验证文件类型"""
        allowed_types = ["image/jpeg", "image/png", "application/pdf"]
        if v not in allowed_types:
            raise ValueError(f"不支持的文件类型: {v}")
        return v
```

---

## 六、Model 组织规范

### 6.1 文件组织

```
app/modules/{module}/model/
├── __init__.py
├── auth.py              # 认证相关模型
├── user.py              # 用户相关模型
├── role.py              # 角色相关模型
└── ...
```

### 6.2 导出顺序

```python
"""
模块模型定义

导出顺序：
1. 基础依赖
2. Entity Model
3. Link Model
4. Request Model
5. Response Model
"""

# ========== 基础依赖 ==========
from datetime import datetime
from typing import Optional

# ========== Entity Model ==========
class User(BaseEntity, table=True):
    pass

# ========== Link Model ==========
class UserRoleLink(BaseEntity, table=True):
    pass

# ========== Request Model ==========
class UserCreateRequest(BaseModel):
    pass

class UserUpdateRequest(BaseModel):
    pass

# ========== Response Model ==========
class UserListItem(BaseModel):
    pass

class UserInfoItem(UserListItem):
    pass
```

### 6.3 类型定义顺序

```python
from typing import Optional, List

# 推荐：按类型分组
from datetime import datetime
from enum import Enum

# 内部类型
class MyEnum(str, Enum):
    A = "a"
    B = "b"

# 基础模型
class MyModel(BaseEntity, table=True):
    pass

# Request/Response
class MyRequest(BaseModel):
    pass

class MyResponse(BaseModel):
    pass
```

---

## 七、Model 开发检查清单

### 7.1 Entity Model 检查

在定义 Entity Model 时，请按以下清单检查：

- [ ] **继承基类**：继承了 `BaseEntity`
- [ ] **表名配置**：配置了 `__tablename__`
- [ ] **字段命名**：使用 snake_case，与数据库字段一致
- [ ] **主键定义**：使用了 `BaseEntity` 的 `id` 字段
- [ ] **索引配置**：需要查询的字段配置了 `index=True`
- [ ] **唯一约束**：唯一字段配置了 `unique=True`
- [ ] **外键配置**：关联字段配置了 `foreign_key`
- [ ] **默认值**：配置了合理的 `default` 或 `default_factory`
- [ ] **类型正确**：字段类型与数据库列类型匹配
- [ ] **长度限制**：字符串字段配置了 `max_length`
- [ ] **关系定义**：配置了 SQLAlchemy `Relationship`（如需要）
- [ ] **类注释**：添加了清晰的类注释
- [ ] **字段注释**：重要字段添加了注释

### 7.2 Request Model 检查

- [ ] **继承正确**：继承了 `BaseModel`
- [ ] **配置完整**：配置了 `populate_by_name=True` 和 `alias_generator=resolve_alias`
- [ ] **字段命名**：使用 snake_case，与 Entity Model 一致
- [ ] **必填字段**：必填字段没有默认值
- [ ] **可选字段**：可选字段配置了 `Optional` 和默认值
- [ ] **类型验证**：使用了 `@field_validator` 进行数据验证
- [ ] **类型转换**：使用了 `@field_validator` 进行类型转换
- [ ] **错误提示**：验证错误提供了清晰的错误信息
- [ ] **嵌套模型**：嵌套模型也正确配置了 `alias_generator`
- [ ] **类注释**：添加了清晰的类注释

### 7.3 Response Model 检查

- [ ] **继承正确**：继承了 `BaseModel`
- [ ] **配置完整**：配置了 `from_attributes=True`、`populate_by_name=True` 和 `alias_generator=resolve_alias`
- [ ] **字段命名**：使用 snake_case，与 Entity Model 一致
- [ ] **类型序列化**：使用了 `@field_serializer` 处理类型转换
- [ ] **时间格式化**：datetime 字段正确序列化为字符串
- [ ] **计算字段**：计算字段使用了 `@computed_field`
- [ ] **继承使用**：正确使用了继承来复用字段定义
- [ ] **类注释**：添加了清晰的类注释

### 7.4 Link Model 检查

- [ ] **继承基类**：继承了 `BaseEntity`
- [ ] **表名配置**：配置了 `__tablename__`，遵循 `{table1}_{table2}` 格式
- [ ] **外键配置**：外键字段配置了 `foreign_key` 和 `index=True`
- [ ] **唯一约束**：配置了复合唯一约束（如需要）
- [ ] **关系定义**：配置了双向 `Relationship`（如需要）

### 7.5 字段验证检查

- [ ] **必填验证**：必填字段进行了验证
- [ ] **格式验证**：邮箱、手机号等格式正确验证
- [ ] **长度验证**：字符串字段验证了长度
- [ ] **范围验证**：数值字段验证了范围
- [ ] **枚举验证**：枚举字段使用了正确的枚举类型
- [ ] **业务验证**：业务规则正确验证

### 7.6 类型转换检查

- [ ] **前端输入**：`@field_validator(mode="before")` 正确处理前端输入
- [ ] **前端输出**：`@field_serializer` 正确处理前端输出
- [ ] **布尔转换**：bool ↔ int 转换正确
- [ ] **时间转换**：datetime ↔ string 转换正确
- [ ] **枚举转换**：枚举 ↔ string 转换正确

---

## 八、常见问题

### 8.1 字段验证不生效？

**可能原因**：
1. `@field_validator` 的 `mode` 参数设置错误
2. 验证器方法不是类方法
3. 验证器方法返回值类型不正确

**解决方法**：
```python
# ✅ 正确
@field_validator("username", mode="before")
@classmethod
def strip_whitespace(cls, v: str) -> str:
    return v.strip()

# ❌ 错误
def strip_whitespace(self, v: str) -> str:  # 缺少 @classmethod
    return v.strip()
```

### 8.2 序列化不生效？

**可能原因**：
1. 没有配置 `alias_generator=resolve_alias`
2. 使用了 `model_dump()` 而不是 `model_dump(by_alias=True)`
3. `@field_serializer` 配置错误

**解决方法**：
```python
# 检查配置
model_config = ConfigDict(
    from_attributes=True,
    populate_by_name=True,
    alias_generator=resolve_alias,  # 必须配置
)

# 检查序列化
data = instance.model_dump(by_alias=True)  # 必须有 by_alias=True
```

### 8.3 继承后配置丢失？

**可能原因**：子类重新定义了 `model_config`

**解决方法**：
```python
# ✅ 正确：子类自动继承
class ChildModel(ParentModel):
    new_field: str = "value"
    # 不需要重新定义 model_config

# ❌ 错误：覆盖了父类配置
class ChildModel(ParentModel):
    model_config = ConfigDict()  # 这会覆盖父类配置
```

### 8.4 前端无法识别字段？

**可能原因**：
1. 字段名使用了 camelCase
2. 没有配置 `populate_by_name=True`

**解决方法**：
```python
# ✅ 正确
model_config = ConfigDict(
    populate_by_name=True,  # 必须配置
    alias_generator=resolve_alias,
)

full_name: str  # 使用 snake_case

# ❌ 错误
model_config = ConfigDict()

fullName: str  # 不要用 camelCase
```

### 8.5 时间格式不正确？

**可能原因**：没有使用 `@field_serializer` 格式化时间

**解决方法**：
```python
@field_serializer("created_at")
def serialize_created_at(self, v: datetime) -> str:
    """格式化时间为 ISO 字符串"""
    return v.isoformat() if v else None
```

---

## 九、最佳实践

### 9.1 模型分离

```python
# ✅ 推荐：Entity、Request、Response 分离
# auth.py

# Entity Model
class User(BaseEntity, table=True):
    pass

# Request Model
class UserCreateRequest(BaseModel):
    pass

class UserUpdateRequest(BaseModel):
    pass

# Response Model
class UserListItem(BaseModel):
    pass

class UserInfoItem(UserListItem):
    pass

# ❌ 不推荐：混合定义
class User(BaseEntity, table=True, BaseModel):
    pass
```

### 9.2 字段分组

```python
class UserCreateRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=resolve_alias,
    )
    
    # ========== 基本信息 ==========
    username: str
    full_name: str
    nick_name: str = ""
    
    # ========== 认证信息 ==========
    password: str
    
    # ========== 联系方式 ==========
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    
    # ========== 组织信息 ==========
    department_id: Optional[int] = None
    role_ids: list[int] = []
```

### 9.3 验证器组织

```python
class UserCreateRequest(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None
    
    # ========== 字符串处理 ==========
    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v
    
    # ========== 业务验证 ==========
    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if len(v) < 3:
            raise ValueError("用户名至少为 3 个字符")
        return v
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少为 8 个字符")
        return v
```

### 9.4 复用字段定义

```python
# 定义可复用的字段组合
from pydantic import BaseModel, Field as PydanticField

class TimestampMixin(BaseModel):
    """时间戳混入"""
    created_at: datetime
    updated_at: datetime

class SoftDeleteMixin(BaseModel):
    """软删除混入"""
    delete_time: Optional[datetime] = None
    is_deleted: bool = False

# 使用混入
class UserRead(TimestampMixin, SoftDeleteMixin, BaseModel):
    username: str
    full_name: str
```

---

## 十、完整示例

### 10.1 完整的模型定义文件

```python
"""
用户认证与权限模型

包含：
- Entity Model: User, Role, Menu, Department
- Link Model: UserRoleLink, RoleMenuLink, RoleDepartmentLink
- Request Model: Create/Update Request
- Response Model: List/Info Item
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field as PydanticField, field_validator, field_serializer
from sqlmodel import Field, Relationship, SQLModel
from app.framework.models.entity import BaseEntity
from app.framework.api.naming import resolve_alias

# ========== Entity Model ==========

class Department(BaseEntity, table=True):
    """部门表"""
    
    __tablename__ = "sys_department"
    
    name: str = Field(index=True, unique=True)
    parent_id: Optional[int] = Field(default=None)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    
    # 关系
    users: list["User"] = Relationship(back_populates="department")


class Role(BaseEntity, table=True):
    """角色表"""
    
    __tablename__ = "sys_role"
    
    name: str = Field(index=True, unique=True)
    code: str = Field(index=True, unique=True)
    label: str = Field(index=True, unique=True)
    remark: Optional[str] = None
    data_scope: str = Field(default="self")
    is_active: bool = Field(default=True)
    
    # 关系
    user_links: list["UserRoleLink"] = Relationship(back_populates="role")
    menu_links: list["RoleMenuLink"] = Relationship(back_populates="role")
    department_links: list["RoleDepartmentLink"] = Relationship(back_populates="role")


class Menu(BaseEntity, table=True):
    """菜单与权限资源表"""
    
    __tablename__ = "sys_menu"
    
    parent_id: Optional[int] = Field(default=None)
    name: str
    code: str = Field(index=True, unique=True)
    type: str = Field(default="button")
    path: Optional[str] = None
    component: Optional[str] = None
    icon: Optional[str] = None
    keep_alive: bool = Field(default=True)
    is_show: bool = Field(default=True)
    permission: Optional[str] = Field(default=None, index=True)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)
    
    # 关系
    role_links: list["RoleMenuLink"] = Relationship(back_populates="menu")


class User(BaseEntity, table=True):
    """用户表"""
    
    __tablename__ = "sys_user"
    
    username: str = Field(index=True, unique=True, max_length=50)
    full_name: str = Field(max_length=100)
    nick_name: Optional[str] = Field(default=None, max_length=50)
    head_img: Optional[str] = Field(default=None, max_length=500)
    email: Optional[EmailStr] = Field(default=None, index=True, unique=True)
    phone: Optional[str] = Field(default=None, max_length=20)
    remark: Optional[str] = Field(default=None, max_length=500)
    password_hash: str
    password_version: int = Field(default=1)
    password_changed_at: Optional[datetime] = Field(default=None)
    department_id: Optional[int] = Field(default=None, foreign_key="sys_department.id")
    is_super_admin: bool = Field(default=False)
    is_manager: bool = Field(default=False)
    is_department_leader: bool = Field(default=False)
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = None
    
    # 关系
    department: Optional[Department] = Relationship(back_populates="users")
    role_links: list["UserRoleLink"] = Relationship(back_populates="user")


# ========== Link Model ==========

class UserRoleLink(BaseEntity, table=True):
    """用户角色关联表"""
    
    __tablename__ = "sys_user_role"
    
    user_id: int = Field(index=True, foreign_key="sys_user.id")
    role_id: int = Field(index=True, foreign_key="sys_role.id")
    
    # 关系
    user: Optional[User] = Relationship(back_populates="role_links")
    role: Optional[Role] = Relationship(back_populates="user_links")


class RoleMenuLink(BaseEntity, table=True):
    """角色菜单关联表"""
    
    __tablename__ = "sys_role_menu"
    
    role_id: int = Field(index=True, foreign_key="sys_role.id")
    menu_id: int = Field(index=True, foreign_key="sys_menu.id")
    
    # 关系
    role: Optional[Role] = Relationship(back_populates="menu_links")
    menu: Optional[Menu] = Relationship(back_populates="role_links")


class RoleDepartmentLink(BaseEntity, table=True):
    """角色部门关联表"""
    
    __tablename__ = "sys_role_department"
    
    role_id: int = Field(index=True, foreign_key="sys_role.id")
    department_id: int = Field(index=True, foreign_key="sys_department.id")


# ========== Request Model ==========

class LoginRequest(BaseModel):
    """登录请求"""
    
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    username: str
    password: str
    captcha_id: Optional[str] = None
    verify_code: Optional[str] = None
    
    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class UserCreateRequest(BaseModel):
    """创建用户请求"""
    
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    username: str
    full_name: str
    nick_name: str = ""
    password: str
    head_img: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    department_id: Optional[int] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    is_active: bool = True
    
    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v


class UserUpdateRequest(BaseModel):
    """更新用户请求"""
    
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    id: int
    full_name: str
    nick_name: str = ""
    head_img: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    department_id: Optional[int] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    is_active: bool = True
    password: Optional[str] = None


# ========== Response Model ==========

class PageResult(BaseModel, Generic[T]):
    """分页响应"""
    
    items: list[T]
    total: int
    page: int
    page_size: int


class UserListItem(BaseModel):
    """用户列表项"""
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)
    
    id: int
    username: str
    full_name: str
    nick_name: Optional[str] = None
    head_img: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    role_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    
    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class UserInfoItem(UserListItem):
    """用户详细信息"""
    
    password_version: Optional[int] = PydanticField(default=None)
```

---

## 十一、更新记录

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|----------|
| v1.0 | 2026-04-21 | 系统 | 初始版本，建立框架 Model 使用规范 |

---

**文档维护**：本规范应随框架演进持续更新。如有疑问或建议，请联系技术负责人。
