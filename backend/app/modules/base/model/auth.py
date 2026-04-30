"""
Base 模块认证与权限相关模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field as PydanticField, field_validator, field_serializer
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity
from app.framework.api.naming import resolve_alias


class Department(BaseEntity, table=True):
    """部门表"""

    __tablename__ = "sys_department"

    name: str = Field(index=True, unique=True)
    parent_id: Optional[int] = Field(default=None)
    sort_order: int = Field(default=0)
    is_active: bool = Field(default=True)


class Role(BaseEntity, table=True):
    """角色表"""

    __tablename__ = "sys_role"

    name: str = Field(index=True, unique=True)
    code: str = Field(index=True, unique=True)
    label: str = Field(index=True, unique=True)
    remark: Optional[str] = None
    data_scope: str = Field(default="self")
    is_active: bool = Field(default=True)


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


class User(BaseEntity, table=True):
    """用户表"""

    __tablename__ = "sys_user"

    username: str = Field(index=True, unique=True)
    full_name: str
    nick_name: Optional[str] = None
    head_img: Optional[str] = None
    email: Optional[str] = Field(default=None, index=True, unique=True)
    phone: Optional[str] = None
    remark: Optional[str] = None
    password_hash: str
    password_version: int = Field(default=1)
    password_changed_at: Optional[datetime] = Field(default=None)  # 密码最后修改时间
    department_id: Optional[int] = Field(default=None)
    is_super_admin: bool = Field(default=False)
    is_manager: bool = Field(default=False)
    is_department_leader: bool = Field(default=False)
    is_active: bool = Field(default=True)
    last_login_at: Optional[datetime] = None


class UserRoleLink(BaseEntity, table=True):
    """用户角色关联表"""

    __tablename__ = "sys_user_role"

    user_id: int = Field(index=True)
    role_id: int = Field(index=True)


class RoleMenuLink(BaseEntity, table=True):
    """角色菜单关联表"""

    __tablename__ = "sys_role_menu"

    role_id: int = Field(index=True)
    menu_id: int = Field(index=True)


class RoleDepartmentLink(BaseEntity, table=True):
    """角色部门关联表"""

    __tablename__ = "sys_role_department"

    role_id: int = Field(index=True)
    department_id: int = Field(index=True)


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
        """去除用户名和密码的前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    refresh_token: Optional[str] = None

    @property
    def token_value(self) -> str | None:
        return self.refresh_token


class UserPersonRead(BaseModel):
    """个人信息响应模型（对齐 Loom）"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    created_at: datetime
    updated_at: datetime
    department_id: Optional[int] = None
    full_name: str
    username: str
    password_version: int = 1
    nick_name: Optional[str] = None
    head_img: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    remark: Optional[str] = None
    is_active: bool = True
    is_super_admin: int = 0
    is_manager: int = 0
    is_department_leader: int = 0
    sort_order: int = 0
    open_id: Optional[str] = None
    union_id: Optional[str] = None
    socket_id: Optional[str] = None

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class UserPersonUpdateRequest(BaseModel):
    """当前用户资料修改请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    nick_name: Optional[str] = None
    head_img: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    remark: Optional[str] = None
    password: Optional[str] = None
    old_password: Optional[str] = None

    @field_validator("password", "old_password", mode="before")
    @classmethod
    def strip_passwords(cls, v: Optional[str]) -> Optional[str]:
        """去除密码的前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v


class UserProfile(BaseModel):
    """当前用户信息"""

    id: int
    username: str
    full_name: str
    department_id: Optional[int]
    is_super_admin: bool
    is_manager: bool
    is_department_leader: bool
    role_codes: list[str]
    permissions: list[str]


class CoolUserInfo(BaseModel):
    """Loom 兼容用户信息"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    user_id: int
    username: str
    nick_name: Optional[str] = None
    department_id: Optional[int]
    role_codes: list[str]
    permission: list[str]
    is_super_admin: bool
    force_password_change: bool = False  # 是否强制修改密码


T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    """分页响应"""

    items: list[T]
    total: int
    page: int
    page_size: int


class DeleteRequest(BaseModel):
    """批量删除请求"""

    ids: list[int] = PydanticField(default_factory=list)


class UserListItem(BaseModel):
    """用户管理列表项"""

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
    password_version: Optional[int] = PydanticField(default=None)


class UserCreateRequest(BaseModel):
    """创建用户请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    username: str
    full_name: str
    nick_name: str = ""
    password: str
    head_img: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    department_id: Optional[int] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    is_active: bool = True

    @field_validator("username", "password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """去除用户名和密码的前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class UserUpdateRequest(BaseModel):
    """更新用户请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    full_name: str
    nick_name: str = ""
    head_img: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    department_id: Optional[int] = None
    role_ids: list[int] = PydanticField(default_factory=list)
    is_active: bool = True
    password: Optional[str] = None

    @field_validator("password", mode="before")
    @classmethod
    def strip_password(cls, v: Optional[str]) -> Optional[str]:
        """去除密码的前后空格"""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class UserRoleAssignRequest(BaseModel):
    """用户角色分配请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    user_id: int
    role_ids: list[int] = PydanticField(default_factory=list)


class UserMoveRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    department_id: int
    user_ids: list[int] = PydanticField(default_factory=list)


class RoleRead(BaseModel):
    """角色响应"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    name: str
    label: str
    code: str
    remark: Optional[str] = None
    is_active: bool = True
    relevance: int = 1
    menu_ids: list[int] = PydanticField(default_factory=list)
    department_ids: list[int] = PydanticField(default_factory=list)
    created_at: datetime
    updated_at: datetime

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class RoleCreateRequest(BaseModel):
    """角色创建请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    name: str
    label: str
    code: Optional[str] = None
    remark: Optional[str] = None
    is_active: bool = True
    relevance: int = 1
    menu_ids: list[int] = PydanticField(default_factory=list)
    department_ids: list[int] = PydanticField(default_factory=list)

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class RoleUpdateRequest(BaseModel):
    """角色更新请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    name: str
    label: str
    code: Optional[str] = None
    remark: Optional[str] = None
    is_active: bool = True
    relevance: int = 1
    menu_ids: list[int] = PydanticField(default_factory=list)
    department_ids: list[int] = PydanticField(default_factory=list)

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class RoleMenuAssignRequest(BaseModel):
    """角色菜单分配请求"""

    role_id: int
    menu_ids: list[int] = PydanticField(default_factory=list)


class MenuRead(BaseModel):
    """菜单响应"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    name: str
    code: str
    type: int
    path: Optional[str] = None
    component: Optional[str] = None
    icon: Optional[str] = None
    keep_alive: bool = True
    is_show: bool = True
    permission: Optional[str] = None
    sort_order: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, v: Any) -> int:
        if v in (0, "0", "group", "dir"):
            return 0
        if v in (1, "1", "menu"):
            return 1
        if v in (2, "2", "button"):
            return 2
        return v # 让 pydantic 自己报 int 转换错误，如果不匹配以上

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class MenuCreateRequest(BaseModel):
    """菜单创建请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    parent_id: Optional[int] = None
    name: str
    code: Optional[str] = None
    type: int | str = 2
    path: Optional[str] = None
    component: Optional[str] = None
    icon: Optional[str] = None
    keep_alive: bool = True
    is_show: bool = True
    permission: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class MenuUpdateRequest(BaseModel):
    """菜单更新请求"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    parent_id: Optional[int] = None
    name: str
    code: Optional[str] = None
    type: int | str = 2
    path: Optional[str] = None
    component: Optional[str] = None
    icon: Optional[str] = None
    keep_alive: bool = True
    is_show: bool = True
    permission: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

    @field_validator("is_active", mode="before")
    @classmethod
    def parse_status(cls, v):
        if isinstance(v, int):
            return v == 1
        return bool(v)


class MenuTreeItem(MenuRead):
    """菜单树节点"""

    children: list["MenuTreeItem"] = PydanticField(default_factory=list)


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True, alias_generator=resolve_alias)

    id: int
    parent_id: Optional[int] = None
    name: str
    parent_name: Optional[str] = None
    sort_order: int
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class DepartmentCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)
    
    parent_id: Optional[int] = None
    name: str
    sort_order: int = 0


class DepartmentUpdateRequest(DepartmentCreateRequest):
    id: int


class DepartmentOrderItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    parent_id: Optional[int] = None
    sort_order: int = 0


class DepartmentDeleteRequest(DeleteRequest):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    delete_user: bool = False


class MenuExportRequest(DeleteRequest):
    pass


class MenuImportNode(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: Optional[int] = None
    parent_id: Optional[int] = None
    name: str
    path: Optional[str] = None
    component: Optional[str] = None
    permission: Optional[str] = None
    type: int = 1
    icon: Optional[str] = None
    sort_order: int = 0
    keep_alive: bool = True
    is_show: bool = True
    child_menus: list["MenuImportNode"] = PydanticField(default_factory=list)


class MenuImportRequest(BaseModel):
    menus: list[MenuImportNode] = PydanticField(default_factory=list)


class MenuParseRequest(BaseModel):
    prefixes: list[str] = PydanticField(default_factory=list)


class MenuParseItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    module: str
    resource: str
    prefix: str
    controller: str
    name: str
    path: str
    component: Optional[str] = None
    icon: Optional[str] = None
    parent_code: Optional[str] = None
    api: list[dict] = PydanticField(default_factory=list)


class MenuParseResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    items: list[MenuParseItem] = PydanticField(default_factory=list, validation_alias=AliasChoices("items", "list"), serialization_alias="list")


class MenuCreateAutoItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    parent_id: Optional[int] = None
    name: str
    path: str
    module: Optional[str] = None
    prefix: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int = 0
    keep_alive: bool = True
    api: list[dict] = PydanticField(default_factory=list)
    component: Optional[str] = None


class MenuCreateAutoRequest(BaseModel):
    items: list[MenuCreateAutoItem] = PydanticField(default_factory=list)


class TokenPair(BaseModel):
    """登录响应"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserProfile
    permissions: list[str]


class CoolLoginResponse(BaseModel):
    """Loom 兼容登录响应"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    token: str
    refresh_token: str
    expire: int
    refresh_expire: int
    user_info: CoolUserInfo
    permission: list[str]


class CaptchaResponse(BaseModel):
    """验证码响应"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    captcha_id: str
    data: dict[str, Any]


class CoolMenuItem(BaseModel):
    """Loom 兼容菜单节点"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    id: int
    parent_id: Optional[int] = None
    parent_name: Optional[str] = None
    name: str
    path: Optional[str] = None
    component: Optional[str] = None
    permission: Optional[str] = None
    type: int = 1
    icon: Optional[str] = None
    sort_order: int = 0
    keep_alive: bool = True
    is_show: bool = True
    is_active: bool = True
    child_menus: list["CoolMenuItem"] = PydanticField(
        default_factory=list,
        serialization_alias="children"
    )

    @field_serializer("is_active")
    def serialize_status(self, v: bool) -> int:
        return 1 if v else 0


class CoolPersonResponse(BaseModel):
    """Loom 兼容个人信息接口响应"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=resolve_alias)

    user_info: CoolUserInfo
    permission: list[str]
    menus: list[CoolMenuItem]


MenuTreeItem.model_rebuild()
CoolMenuItem.model_rebuild()
MenuImportNode.model_rebuild()
