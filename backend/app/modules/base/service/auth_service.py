"""
Base 模块认证与权限服务
"""
from __future__ import annotations

from datetime import datetime
import base64
import html
import re

from fastapi import HTTPException, Request, status
from sqlmodel import Session, select
from uuid import uuid4

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    validate_password_strength,
    decode_token,
    add_token_to_blacklist,
)

from app.modules.base.compat import SYSTEM_MANAGED_CODE_PREFIXES, get_menu_parent_code
from app.modules.base.model.auth import (
    CaptchaResponse,
    CoolLoginResponse,
    CoolMenuItem,
    CoolPersonResponse,
    CoolUserInfo,
    Department,
    LoginRequest,
    Menu,
    RefreshTokenRequest,
    Role,
    RoleDepartmentLink,
    RoleMenuLink,
    UserPersonUpdateRequest,
    User,
    UserPersonRead,
    UserRoleLink,
)
from app.modules.base.service.admin_service import MenuAdminService
from app.modules.base.service.cache_service import cache_delete, cache_get, cache_set
from app.modules.base.service.security_service import (
    create_access_token,
    create_refresh_token,
    get_refresh_token_payload,
    get_user_permissions,
    get_user_roles,
)
from app.modules.base.service.authority_service import (
    build_refresh_token_cache_key,
    clear_login_caches,
    clear_login_caches_for_users,
    get_refresh_token_ttl,
    prime_login_caches,
)
from app.modules.loader import load_menu_manifest_items
from app.modules.base.service.sys_manage_service import SysLoginLogService


class AuthService:
    """认证服务"""

    def __init__(self, session: Session):
        self.session = session

    def login(self, payload: LoginRequest, request: Request | None = None) -> CoolLoginResponse:
        login_ip = _get_request_ip(request) or "unknown"
        locked_reason = self._check_login_risk(payload.username, login_ip)
        if locked_reason:
            self._record_login_log(
                request=request,
                account=payload.username,
                status=0,
                reason=locked_reason,
                risk_hit=1,
            )
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=locked_reason)

        if settings.ADMIN_CAPTCHA_ENABLED:
            try:
                self.captcha_check(payload.captcha_id, payload.verify_code)
            except HTTPException as exc:
                self._mark_login_failure(payload.username, login_ip)
                self._record_login_log(
                    request=request,
                    account=payload.username,
                    status=0,
                    reason=exc.detail if isinstance(exc.detail, str) else "验证码不正确",
                    risk_hit=1,
                )
                raise

        statement = select(User).where(User.username == payload.username)
        user = self.session.exec(statement).first()

        if not user or not verify_password(payload.password, user.password_hash):
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name if user else None,
                user_id=user.id if user else None,
                status=0,
                reason="用户名或密码错误",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        if not user.is_active:
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name,
                user_id=user.id,
                status=0,
                reason="用户已禁用",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已禁用")

        roles = get_user_roles(self.session, user.id)
        if not roles:
            risk_hit = self._mark_login_failure(payload.username, login_ip)
            self._record_login_log(
                request=request,
                account=payload.username,
                name=user.full_name,
                user_id=user.id,
                status=0,
                reason="当前用户未分配角色",
                risk_hit=risk_hit,
            )
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户未分配角色")
        setattr(user, "_token_role_ids", [role.id for role in roles if role.id is not None])

        user.last_login_at = datetime.utcnow()
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)

        # 检查是否需要强制修改密码（从未修改过密码或密码是默认值）
        force_password_change = False
        if user.password_changed_at is None:
            # 首次登录或从未修改过密码
            force_password_change = True

        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        permissions = prime_login_caches(self.session, user, access_token)
        cache_set(build_refresh_token_cache_key(user.id), refresh_token, get_refresh_token_ttl())
        self._clear_login_failure(payload.username, login_ip)
        self._record_login_log(
            request=request,
            user_id=user.id,
            name=user.full_name,
            account=user.username,
            status=1,
        )
        return self._finalize_login_response(
            user=user,
            roles=roles,
            permissions=permissions,
            access_token=access_token,
            refresh_token=refresh_token,
            force_password_change=force_password_change,
        )
        
    def _finalize_login_response(
        self,
        *,
        user: User,
        roles: list[Role],
        permissions: list[str],
        access_token: str,
        refresh_token: str,
        force_password_change: bool = False,
    ) -> CoolLoginResponse:
        response = CoolLoginResponse(
            token=access_token,
            refresh_token=refresh_token,
            expire=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            refresh_expire=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            user_info=self.build_user_info(user, roles=roles, permissions=permissions, force_password_change=force_password_change),
            permission=permissions,
        )
        return response

    def refresh_token(self, payload: RefreshTokenRequest) -> CoolLoginResponse:
        refresh_token_value = payload.token_value
        if not refresh_token_value:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌不能为空")
        token_payload = get_refresh_token_payload(refresh_token_value)
        user_id = token_payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌缺少用户标识")

        user = self.session.get(User, int(user_id))
        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

        token_password_version = token_payload.get("password_version")
        if user.password_version != token_password_version:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌已失效")

        roles = get_user_roles(self.session, user.id)
        setattr(user, "_token_role_ids", [role.id for role in roles if role.id is not None])
        access_token = create_access_token(user)
        refresh_token = create_refresh_token(user)
        permissions = prime_login_caches(self.session, user, access_token)
        cache_set(build_refresh_token_cache_key(user.id), refresh_token, get_refresh_token_ttl())
        return self._finalize_login_response(
            user=user,
            roles=roles,
            permissions=permissions,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def logout(self, user: User, request: Request | None = None) -> None:
        # 将当前Token加入黑名单
        if request:
            try:
                from app.modules.base.service.authority_service import extract_token
                token = extract_token(request)
                payload = decode_token(token)
                jti = payload.get("jti")
                exp = payload.get("exp")
                if jti and exp:
                    add_token_to_blacklist(jti, exp)
            except Exception:
                # Token解析失败不影响登出流程
                pass

        self._record_login_log(
            request=request,
            user_id=user.id,
            name=user.full_name,
            account=user.username,
            login_type="logout",
            status=1,
        )
        clear_login_caches(user.id)

    def captcha(self, width: int = 150, height: int = 50, color: str = "#333") -> CaptchaResponse:
        chars = uuid4().hex[:4].upper()
        safe_text = html.escape(chars)
        safe_color = html.escape(color or "#333", quote=True)
        svg_data = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
            f"<rect width='{width}' height='{height}' fill='#f5f5f5' rx='4' ry='4'/>"
            f"<text x='{width * 0.18}' y='{height * 0.68}' fill='{safe_color}' "
            f"font-size='{height * 0.56}' font-family='monospace'>{safe_text}</text>"
            "</svg>"
        )
        base64_data = base64.b64encode(svg_data.encode("utf-8")).decode("ascii")
        captcha_id = uuid4().hex
        cache_set(self._build_captcha_cache_key(captcha_id), chars.lower(), settings.CAPTCHA_EXPIRE_SECONDS)
        return CaptchaResponse(
            captcha_id=captcha_id,
            data=f"data:image/svg+xml;base64,{base64_data}",
        )

    def captcha_check(self, captcha_id: str | None, verify_code: str | None) -> None:
        if not captcha_id or not verify_code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不能为空")
        cache_key = self._build_captcha_cache_key(captcha_id)
        cached = cache_get(cache_key)
        # 防重放：立即删除验证码，确保只能使用一次
        cache_delete(cache_key)
        if not cached or cached != verify_code.lower():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码不正确或已失效")

    def get_current_profile(self, user: User) -> CoolUserInfo:
        roles = get_user_roles(self.session, user.id)
        permissions = get_user_permissions(self.session, user.id)
        # 检查是否需要强制修改密码
        force_password_change = user.password_changed_at is None
        return self.build_user_info(user, roles=roles, permissions=permissions, force_password_change=force_password_change)

    def build_user_info(self, user: User, roles: list[Role], permissions: list[str], force_password_change: bool = False) -> CoolUserInfo:
        return CoolUserInfo(
            user_id=user.id,
            username=user.username,
            nick_name=user.full_name,
            department_id=user.department_id,
            role_codes=[role.code for role in roles],
            permission=permissions,
            is_super_admin=user.is_super_admin,
            force_password_change=force_password_change,
        )

    def person(self, user: User) -> UserPersonRead:
        return UserPersonRead(
            id=user.id,
            created_at=user.created_at,
            updated_at=user.updated_at or user.created_at,
            department_id=user.department_id,
            full_name=user.full_name,
            username=user.username,
            password_version=user.password_version,
            nick_name=user.nick_name,
            head_img=user.head_img,
            phone=user.phone,
            email=user.email,
            remark=user.remark,
            is_active=user.is_active,
            is_super_admin=1 if user.is_super_admin else 0,
            is_manager=1 if user.is_manager else 0,
            is_department_leader=1 if user.is_department_leader else 0,
        )

    def person_update(self, user: User, payload: UserPersonUpdateRequest) -> dict:
        target = self.session.get(User, user.id)
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

        if payload.password:
            if not payload.old_password:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码不能为空")
            if not verify_password(payload.old_password, target.password_hash):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")
            # 验证新密码强度
            validate_password_strength(payload.password)
            target.password_hash = hash_password(payload.password)
            target.password_version += 1
            target.password_changed_at = datetime.utcnow()  # 记录密码修改时间

        if payload.nick_name is not None:
            target.nick_name = payload.nick_name
        if payload.head_img is not None:
            target.head_img = payload.head_img
        if payload.phone is not None:
            target.phone = payload.phone
        if payload.email is not None:
            target.email = payload.email
        if payload.remark is not None:
            target.remark = payload.remark

        target.updated_at = datetime.utcnow()
        self.session.add(target)
        self.session.commit()
        self.session.refresh(target)
        clear_login_caches(target.id)
        return {"success": True}

    def permmenu(self, user: User) -> dict:
        """
        获取权限与菜单（Cool 兼容格式）

        返回格式: {"perms": list[str], "menus": list[dict]}

        重要: 菜单必须返回扁平数组结构，而非树形嵌套结构！
        - Cool 前端期望所有菜单项在同一层级，通过 parentId 字段建立父子关系
        - 每个菜单项的 children 数组必须为空 []
        - 测试用例 test_permmenu_contains_flat_system_management_routes 依赖此结构
        - 不要修改为树形结构，否则会导致前端无法正确渲染菜单

        Args:
            user: 当前用户

        Returns:
            dict: 包含 perms (权限列表) 和 menus (扁平菜单数组) 的字典
        """
        permissions = get_user_permissions(self.session, user.id)
        from app.modules.base.service.admin_service import MenuAdminService

        # 获取树形结构的菜单
        menu_tree = MenuAdminService(self.session).current_tree(user)

        # 转换为 CoolMenuItem 并扁平化，符合 cool 前端期望的扁平数组格式
        cool_menus = [self._build_cool_menu_item(menu) for menu in menu_tree]
        flat_menus = self._flatten_cool_menus(cool_menus)

        return {
            "perms": permissions,
            "menus": [item.model_dump(mode="json", by_alias=True) for item in flat_menus],
        }

    def _build_cool_menu_item(self, menu, name_map: dict[int, str] | None = None, children_override: list = None) -> CoolMenuItem:
        type_mapping = {"group": 0, "menu": 1, "button": 2}
        
        # 处理可能的模型对象或字典
        m_id = getattr(menu, "id", None)
        parent_id = getattr(menu, "parent_id", None)
        name = getattr(menu, "name", "")
        path = getattr(menu, "path", None)
        permission = getattr(menu, "permission", None)
        menu_type = getattr(menu, "type", 1)
        sort_order = getattr(menu, "sort_order", 0)
        component = getattr(menu, "component", None)
        keep_alive = getattr(menu, "keep_alive", True)
        is_show = getattr(menu, "is_show", True)
        is_active = getattr(menu, "is_active", True)
        # 如果传入了 children_override（来自树处理），则优先使用
        if children_override is not None:
            children = children_override
        else:
            children = getattr(menu, "children", getattr(menu, "child_menus", []))

        parent_name = None
        if name_map and parent_id in name_map:
            parent_name = name_map[parent_id]
        elif parent_id:
            parent_name = getattr(menu, "parent_name", None)

        final_type = type_mapping.get(menu_type, menu_type if isinstance(menu_type, int) else 1)
        
        # 处理组件路径逻辑，防止前端 Vue Router 报 Invalid route component
        if final_type == 0:  # 目录类型
            component = None
        elif final_type == 1:  # 菜单类型
            if not component or (isinstance(component, str) and not component.strip()):
                # 如果是带子菜单的父级菜单但没有定义组件，通常需要 layout 承载
                component = "layout" if children else None
        
        return CoolMenuItem(
            id=m_id,
            parent_id=parent_id,
            parent_name=parent_name,
            name=name,
            path=path,
            permission=permission,
            type=final_type,
            sort_order=sort_order,
            component=component,
            icon=getattr(menu, "icon", None),
            keep_alive=keep_alive,
            is_show=is_show,
            is_active=is_active,
            child_menus=[
                (self._build_cool_menu_item(child, name_map=name_map) if children_override is None else child)
                for child in children
            ],
        )

    def _flatten_cool_menus(self, menus: list[CoolMenuItem]) -> list[CoolMenuItem]:
        """
        将树形菜单结构扁平化

        将嵌套的树形菜单结构转换为扁平数组，每个菜单项的 child_menus 被清空。
        这是 Cool 前端框架的硬性要求，前端需要通过 parentId 字段自行构建树形结构。

        注意: 不要修改此方法的返回格式，否则会导致前端菜单无法正确渲染。

        Args:
            menus: 树形嵌套的菜单列表

        Returns:
            扁平化的菜单列表，每个菜单项的 child_menus 为空数组
        """
        result: list[CoolMenuItem] = []

        def walk(items: list[CoolMenuItem]) -> None:
            for item in items:
                children = item.child_menus
                result.append(item.model_copy(update={"child_menus": []}))
                if children:
                    walk(children)

        walk(menus)
        return result

    @staticmethod
    def _build_captcha_cache_key(captcha_id: str) -> str:
        return f"verify:img:{captcha_id}"

    def _record_login_log(
        self,
        *,
        request: Request | None,
        account: str | None,
        status: int,
        reason: str | None = None,
        user_id: int | None = None,
        name: str | None = None,
        login_type: str = "password",
    ) -> None:
        try:
            SysLoginLogService(self.session).create_entry(
                user_id=user_id,
                name=name,
                account=account,
                login_type=login_type,
                status=status,
                ip=_get_request_ip(request),
                reason=reason,
                user_agent=_get_user_agent(request),
                client_type=_get_client_type(request),
                device_id=_get_device_id(request),
                source_system="管理后台",
            )
        except Exception as exc:
            # 日志写入失败应记录错误日志，便于排查问题
            import logging
            logger = logging.getLogger(__name__)
            logger.error(
                f"登录日志写入失败 - account: {account}, user_id: {user_id}, status: {status}",
                exc_info=exc
            )

    def bootstrap_defaults(self) -> None:
        root_department = self.session.exec(select(Department).where(Department.name == "平台")).first()
        if not root_department:
            root_department = Department(name="平台", sort_order=0)
            self.session.add(root_department)
            self.session.commit()
            self.session.refresh(root_department)

        admin_role = self.session.exec(select(Role).where(Role.code == "admin")).first()
        if not admin_role:
            admin_role = Role(name="系统管理员", code="admin", label="admin", data_scope="all")
            self.session.add(admin_role)
            self.session.commit()
            self.session.refresh(admin_role)

        operator_role = self.session.exec(select(Role).where(Role.code == "task_operator")).first()
        if not operator_role:
            operator_role = Role(
                name="任务操作员",
                code="task_operator",
                label="task_operator",
                data_scope="self",
            )
            self.session.add(operator_role)
            self.session.commit()
            self.session.refresh(operator_role)

        role_map = {
            admin_role.code: admin_role,
            operator_role.code: operator_role,
        }

        navigation_definitions = load_menu_manifest_items()
        resource_menu_codes = {
            (item.module, item.resource): item.code
            for item in navigation_definitions
            if item.module and item.resource
        }

        all_valid_codes: set[str] = {item.code for item in navigation_definitions}
        managed_permissions: set[str] = {item.permission for item in navigation_definitions if item.permission}
        managed_paths: set[str] = {item.path for item in navigation_definitions if item.path}

        menus_by_code: dict[str, Menu] = {}
        for item in navigation_definitions:
            menu = self.session.exec(select(Menu).where(Menu.code == item.code)).first()
            if not menu:
                menu = Menu(
                    name=item.name,
                    code=item.code,
                    type=item.type,
                    path=item.path,
                    component=item.component,
                    icon=item.icon,
                    keep_alive=item.keep_alive,
                    is_show=item.is_show,
                    sort_order=item.sort_order,
                    is_active=item.is_active,
                    permission=item.permission,
                )
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)
            else:
                menu.name = item.name
                menu.type = item.type
                menu.path = item.path
                menu.component = item.component
                menu.icon = item.icon
                menu.keep_alive = item.keep_alive
                menu.is_show = item.is_show
                menu.sort_order = item.sort_order
                menu.is_active = item.is_active
                menu.permission = item.permission
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)
            menus_by_code[item.code] = menu

        for item in navigation_definitions:
            parent_code = item.parent_code
            if not parent_code:
                continue
            menu = menus_by_code[item.code]
            parent_menu = menus_by_code[parent_code]
            if menu.parent_id != parent_menu.id:
                menu.parent_id = parent_menu.id
                self.session.add(menu)
                self.session.commit()
                self.session.refresh(menu)

        for item in navigation_definitions:
            menu = menus_by_code[item.code]
            for role_code in item.role_codes:
                role = role_map.get(role_code)
                if role and role.id is not None and menu.id is not None:
                    self._ensure_role_menu_link(role.id, menu.id)

        # 清理数据库中不再存在（既不在 JSON Manifest 中，也不在控制器扫描结果中）的权限记录
        all_db_menus = self.session.exec(select(Menu)).all()
        for db_menu in all_db_menus:
            if db_menu.code not in all_valid_codes and self._is_system_managed_menu(db_menu, managed_permissions, managed_paths):
                # 删除与之关联的角色绑定，防止外键约束错误
                links = self.session.exec(select(RoleMenuLink).where(RoleMenuLink.menu_id == db_menu.id)).all()
                for link in links:
                    self.session.delete(link)
                self.session.delete(db_menu)
        self.session.commit()

        if admin_role.id is not None and root_department.id is not None:
            self._ensure_role_department_link(admin_role.id, root_department.id)
        if operator_role.id is not None and root_department.id is not None:
            self._ensure_role_department_link(operator_role.id, root_department.id)

        admin_user = self.session.exec(select(User).where(User.username == settings.DEFAULT_ADMIN_USERNAME)).first()
        if not admin_user:
            admin_user = User(
                username=settings.DEFAULT_ADMIN_USERNAME.strip(),
                full_name=settings.DEFAULT_ADMIN_NAME,
                password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD.strip()),
                department_id=root_department.id,
                is_super_admin=True,
                is_manager=True,
                is_department_leader=True,
            )
            self.session.add(admin_user)
            self.session.commit()
            self.session.refresh(admin_user)

        if admin_user.id is not None and admin_role.id is not None:
            self._ensure_user_role_link(admin_user.id, admin_role.id)

        # 同步完成后清理全站权限缓存，确保新菜单生效
        all_user_ids = self.session.exec(select(User.id)).all()
        clear_login_caches_for_users(all_user_ids)

    def _ensure_user_role_link(self, user_id: int, role_id: int) -> None:
        link = self.session.exec(select(UserRoleLink).where(UserRoleLink.user_id == user_id, UserRoleLink.role_id == role_id)).first()
        if not link:
            self.session.add(UserRoleLink(user_id=user_id, role_id=role_id))
            self.session.commit()

    def _ensure_role_menu_link(self, role_id: int, menu_id: int) -> None:
        link = self.session.exec(select(RoleMenuLink).where(RoleMenuLink.role_id == role_id, RoleMenuLink.menu_id == menu_id)).first()
        if not link:
            self.session.add(RoleMenuLink(role_id=role_id, menu_id=menu_id))
            self.session.commit()

    def _ensure_role_department_link(self, role_id: int, department_id: int) -> None:
        link = self.session.exec(
            select(RoleDepartmentLink).where(RoleDepartmentLink.role_id == role_id, RoleDepartmentLink.department_id == department_id)
        ).first()
        if not link:
            self.session.add(RoleDepartmentLink(role_id=role_id, department_id=department_id))
            self.session.commit()

    def _check_login_risk(self, account: str, ip: str) -> str | None:
        if cache_get(self._build_account_lock_key(account)):
            return "账号已被临时锁定，请稍后再试"
        if cache_get(self._build_ip_lock_key(ip)):
            return "当前IP请求过于频繁，请稍后再试"
        return None

    def _mark_login_failure(self, account: str, ip: str) -> int:
        account_failures = self._increase_counter(self._build_account_fail_key(account), settings.BASE_LOGIN_FAIL_WINDOW)
        ip_failures = self._increase_counter(self._build_ip_fail_key(ip), settings.BASE_LOGIN_FAIL_WINDOW)
        risk_hit = 0
        if account_failures >= settings.BASE_LOGIN_ACCOUNT_FAIL_MAX:
            cache_set(self._build_account_lock_key(account), "1", settings.BASE_LOGIN_LOCK_TIME)
            risk_hit = 1
        if ip_failures >= settings.BASE_LOGIN_IP_FAIL_MAX:
            cache_set(self._build_ip_lock_key(ip), "1", settings.BASE_LOGIN_LOCK_TIME)
            risk_hit = 1
        return risk_hit

    def _clear_login_failure(self, account: str, ip: str) -> None:
        cache_delete(
            self._build_account_fail_key(account),
            self._build_ip_fail_key(ip),
            self._build_account_lock_key(account),
            self._build_ip_lock_key(ip),
        )

    @staticmethod
    def _increase_counter(key: str, ttl_seconds: int) -> int:
        current = cache_get(key)
        next_value = int(current or 0) + 1
        cache_set(key, str(next_value), ttl_seconds)
        return next_value

    @staticmethod
    def _build_account_fail_key(account: str) -> str:
        return f"login:fail:account:{account}"

    @staticmethod
    def _build_ip_fail_key(ip: str) -> str:
        return f"login:fail:ip:{ip}"

    @staticmethod
    def _build_account_lock_key(account: str) -> str:
        return f"login:lock:account:{account}"

    @staticmethod
    def _build_ip_lock_key(ip: str) -> str:
        return f"login:lock:ip:{ip}"

    @staticmethod
    def _is_system_managed_menu(menu: Menu, managed_permissions: set[str], managed_paths: set[str]) -> bool:
        if menu.permission and menu.permission in managed_permissions:
            return True
        if menu.path and menu.path in managed_paths:
            return True
        code = menu.code or ""
        return any(code.startswith(prefix) for prefix in SYSTEM_MANAGED_CODE_PREFIXES)


def _get_request_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _get_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")


def _get_client_type(request: Request | None) -> str | None:
    user_agent = (_get_user_agent(request) or "").lower()
    if not user_agent:
        return None
    if "mobile" in user_agent or "android" in user_agent or "iphone" in user_agent or "ipad" in user_agent:
        return "移动端"
    return "PC"


def _get_device_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("x-device-id") or request.headers.get("device-id")
