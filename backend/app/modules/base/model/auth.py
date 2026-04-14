"""
Base 模块认证与权限相关模型
"""
from __future__ import annotations

from datetime import datetime
from typing import Generic, Optional, TypeVar

from pydantic import AliasChoices, BaseModel, ConfigDict, Field as PydanticField
from sqlmodel import Field, SQLModel
from app.framework.models.entity import BaseEntity


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

    username: str
    password: str
    captchaId: Optional[str] = None
    verifyCode: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""

    refresh_token: Optional[str] = None
    refreshToken: Optional[str] = None

    @property
    def token_value(self) -> str | None:
        return self.refresh_token or self.refreshToken


class UserPersonRead(BaseModel):
    """个人信息响应模型（对齐 Cool-Admin）"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    createTime: datetime
    updateTime: datetime
    departmentId: Optional[int] = None
    name: str
    username: str
    passwordV: int = 1
    nickName: Optional[str] = None
    headImg: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    remark: Optional[str] = None
    status: int = 1
    isSuperAdmin: int = 0
    isManager: int = 0
    isDepartmentLeader: int = 0
    orderNum: int = 0
    openId: Optional[str] = None
    unionId: Optional[str] = None
    socketId: Optional[str] = None


class UserPersonUpdateRequest(BaseModel):
    """当前用户资料修改请求"""

    nickName: Optional[str] = None
    headImg: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    remark: Optional[str] = None
    password: Optional[str] = None
    oldPassword: Optional[str] = None


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
    """Cool 风格用户信息"""

    userId: int
    username: str
    nickName: str
    departmentId: Optional[int]
    roleCodes: list[str]
    perms: list[str]
    isSuperAdmin: bool


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

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    nickName: str
    headImg: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    departmentId: Optional[int] = None
    departmentName: Optional[str] = None
    roleIdList: list[int] = PydanticField(default_factory=list)
    roleName: Optional[str] = None
    status: int
    createTime: datetime
    updateTime: datetime


class UserInfoItem(UserListItem):
    passwordVersion: Optional[int] = PydanticField(default=None)


class UserCreateRequest(BaseModel):
    """创建用户请求"""

    username: str
    name: str = PydanticField(validation_alias=AliasChoices("name", "full_name"))
    nickName: str = PydanticField(default="", validation_alias=AliasChoices("nickName", "nick_name"))
    password: str
    headImg: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("headImg", "head_img"))
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    departmentId: Optional[int] = PydanticField(default=None, validation_alias=AliasChoices("departmentId", "department_id"))
    roleIdList: list[int] = PydanticField(default_factory=list, validation_alias=AliasChoices("roleIdList", "role_ids"))
    status: int = PydanticField(default=1, validation_alias=AliasChoices("status", "is_active"))


class UserUpdateRequest(BaseModel):
    """更新用户请求"""

    id: int
    name: str = PydanticField(validation_alias=AliasChoices("name", "full_name"))
    nickName: str = PydanticField(default="", validation_alias=AliasChoices("nickName", "nick_name"))
    headImg: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("headImg", "head_img"))
    email: Optional[str] = None
    phone: Optional[str] = None
    remark: Optional[str] = None
    departmentId: Optional[int] = PydanticField(default=None, validation_alias=AliasChoices("departmentId", "department_id"))
    roleIdList: list[int] = PydanticField(default_factory=list, validation_alias=AliasChoices("roleIdList", "role_ids"))
    status: int = PydanticField(default=1, validation_alias=AliasChoices("status", "is_active"))
    password: Optional[str] = None


class UserRoleAssignRequest(BaseModel):
    """用户角色分配请求"""

    user_id: int
    role_ids: list[int] = PydanticField(default_factory=list)


class UserMoveRequest(BaseModel):
    departmentId: int
    userIds: list[int] = PydanticField(default_factory=list)


class RoleRead(BaseModel):
    """角色响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    label: str
    code: str
    remark: Optional[str] = None
    status: int
    relevance: int = 1
    menuIdList: list[int] = PydanticField(default_factory=list)
    departmentIdList: list[int] = PydanticField(default_factory=list)
    createTime: datetime
    updateTime: datetime


class RoleCreateRequest(BaseModel):
    """角色创建请求"""

    name: str
    label: str
    code: Optional[str] = None
    remark: Optional[str] = None
    status: int = 1
    relevance: int = 1
    menuIdList: list[int] = PydanticField(default_factory=list)
    departmentIdList: list[int] = PydanticField(default_factory=list)


class RoleUpdateRequest(BaseModel):
    """角色更新请求"""

    id: int
    name: str
    label: str
    code: Optional[str] = None
    remark: Optional[str] = None
    status: int = 1
    relevance: int = 1
    menuIdList: list[int] = PydanticField(default_factory=list)
    departmentIdList: list[int] = PydanticField(default_factory=list)


class RoleMenuAssignRequest(BaseModel):
    """角色菜单分配请求"""

    role_id: int
    menu_ids: list[int] = PydanticField(default_factory=list)


class MenuRead(BaseModel):
    """菜单响应"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    parentId: Optional[int] = None
    parentName: Optional[str] = None
    name: str
    code: str
    type: int
    router: Optional[str] = None
    viewPath: Optional[str] = None
    icon: Optional[str] = None
    keepAlive: bool = True
    isShow: bool = True
    perms: Optional[str] = None
    orderNum: int
    status: int
    createTime: datetime
    updateTime: datetime


class MenuCreateRequest(BaseModel):
    """菜单创建请求"""

    parentId: Optional[int] = PydanticField(default=None, validation_alias=AliasChoices("parentId", "parent_id"))
    name: str
    code: Optional[str] = None
    type: int | str = 2
    router: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("router", "path"))
    viewPath: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("viewPath", "component"))
    icon: Optional[str] = None
    keepAlive: bool = PydanticField(default=True, validation_alias=AliasChoices("keepAlive", "keep_alive"))
    isShow: bool = PydanticField(default=True, validation_alias=AliasChoices("isShow", "is_show"))
    perms: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("perms", "permission"))
    orderNum: int = PydanticField(default=0, validation_alias=AliasChoices("orderNum", "sort_order"))
    status: int = PydanticField(default=1, validation_alias=AliasChoices("status", "is_active"))


class MenuUpdateRequest(BaseModel):
    """菜单更新请求"""

    id: int
    parentId: Optional[int] = PydanticField(default=None, validation_alias=AliasChoices("parentId", "parent_id"))
    name: str
    code: Optional[str] = None
    type: int | str = 2
    router: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("router", "path"))
    viewPath: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("viewPath", "component"))
    icon: Optional[str] = None
    keepAlive: bool = PydanticField(default=True, validation_alias=AliasChoices("keepAlive", "keep_alive"))
    isShow: bool = PydanticField(default=True, validation_alias=AliasChoices("isShow", "is_show"))
    perms: Optional[str] = PydanticField(default=None, validation_alias=AliasChoices("perms", "permission"))
    orderNum: int = PydanticField(default=0, validation_alias=AliasChoices("orderNum", "sort_order"))
    status: int = PydanticField(default=1, validation_alias=AliasChoices("status", "is_active"))


class MenuTreeItem(MenuRead):
    """菜单树节点"""

    children: list["MenuTreeItem"] = PydanticField(default_factory=list)


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parentId: Optional[int] = None
    name: str
    parentName: Optional[str] = None
    orderNum: int
    status: int
    createTime: datetime
    updateTime: datetime


class DepartmentCreateRequest(BaseModel):
    parentId: Optional[int] = PydanticField(default=None, validation_alias=AliasChoices("parentId", "parent_id"))
    name: str
    orderNum: int = PydanticField(default=0, validation_alias=AliasChoices("orderNum", "sort_order"))


class DepartmentUpdateRequest(DepartmentCreateRequest):
    id: int


class DepartmentOrderItem(BaseModel):
    id: int
    parentId: Optional[int] = None
    orderNum: int = 0


class DepartmentDeleteRequest(DeleteRequest):
    deleteUser: bool = False


class MenuExportRequest(DeleteRequest):
    pass


class MenuImportNode(BaseModel):
    id: Optional[int] = None
    parentId: Optional[int] = None
    name: str
    router: Optional[str] = None
    viewPath: Optional[str] = None
    perms: Optional[str] = None
    type: int = 1
    icon: Optional[str] = None
    orderNum: int = 0
    keepAlive: bool = True
    isShow: bool = True
    childMenus: list["MenuImportNode"] = PydanticField(default_factory=list)


class MenuImportRequest(BaseModel):
    menus: list[MenuImportNode] = PydanticField(default_factory=list)


class MenuParseRequest(BaseModel):
    prefixes: list[str] = PydanticField(default_factory=list)


class MenuParseItem(BaseModel):
    module: str
    resource: str
    prefix: str
    controller: str
    name: str
    router: str
    viewPath: Optional[str] = None
    icon: Optional[str] = None
    parentCode: Optional[str] = None
    api: list[dict] = PydanticField(default_factory=list)


class MenuParseResponse(BaseModel):
    items: list[MenuParseItem] = PydanticField(default_factory=list, alias="list")


class MenuCreateAutoItem(BaseModel):
    parentId: Optional[int] = None
    name: str
    router: str
    module: Optional[str] = None
    prefix: Optional[str] = None
    icon: Optional[str] = None
    orderNum: int = 0
    keepAlive: bool = True
    api: list[dict] = PydanticField(default_factory=list)
    viewPath: Optional[str] = None


class MenuCreateAutoRequest(BaseModel):
    items: list[MenuCreateAutoItem] = PydanticField(default_factory=list)


class TokenPair(BaseModel):
    """登录响应"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_expires_in: int
    user: UserProfile
    permissions: list[str]


class CoolLoginResponse(BaseModel):
    """Cool 风格登录响应"""

    token: str
    refreshToken: str
    expire: int
    refreshExpire: int
    userInfo: CoolUserInfo
    perms: list[str]


class CaptchaResponse(BaseModel):
    """验证码响应"""

    captchaId: str
    data: str


class CoolMenuItem(BaseModel):
    """Cool 风格菜单节点"""

    id: int
    parentId: Optional[int] = None
    parentName: Optional[str] = None
    name: str
    router: Optional[str] = None
    viewPath: Optional[str] = None
    perms: Optional[str] = None
    type: int = 1
    icon: Optional[str] = None
    orderNum: int = 0
    keepAlive: bool = True
    isShow: bool = True
    status: int = 1
    childMenus: list["CoolMenuItem"] = PydanticField(default_factory=list)


class CoolPersonResponse(BaseModel):
    """Cool 风格个人信息接口响应"""

    userInfo: CoolUserInfo
    perms: list[str]
    menus: list[CoolMenuItem]


MenuTreeItem.model_rebuild()
CoolMenuItem.model_rebuild()
MenuImportNode.model_rebuild()
