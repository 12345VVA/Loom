"""
Base 模块认证与权限服务（门面）。

实现按职责域拆分（G7 刀1，M6 巨石清偿）：
- auth_login.py — 登录/刷新令牌/登录风控/登录日志（LoginMixin）
- auth_session.py — 多设备会话生命周期（SessionMixin）
- auth_captcha.py — 滑块验证码签发与校验（CaptchaMixin）
- auth_profile.py — 个人资料/用户信息/权限菜单（ProfileMixin）
- auth_bootstrap.py — 启动期菜单/角色/初始账号幂等对账（BootstrapMixin）
- auth_request_info.py — 请求信息解析工具（login/session 共用）

本模块保留全部历史符号：`AuthService` 组合各 mixin（API 不变），
模块级请求解析函数 re-export 供既有引用方（tests 等）使用，
外部统一从 `app.modules.base.service.auth_service` 引用。
"""

from __future__ import annotations

from sqlmodel import Session

from app.modules.base.service.auth_bootstrap import BootstrapMixin
from app.modules.base.service.auth_captcha import CaptchaMixin
from app.modules.base.service.auth_login import LoginMixin
from app.modules.base.service.auth_profile import ProfileMixin
from app.modules.base.service.auth_request_info import (
    _get_client_type as _get_client_type,
)
from app.modules.base.service.auth_request_info import (
    _get_device_id as _get_device_id,
)
from app.modules.base.service.auth_request_info import (
    _get_request_ip as _get_request_ip,
)
from app.modules.base.service.auth_request_info import (
    _get_user_agent as _get_user_agent,
)
from app.modules.base.service.auth_session import SessionMixin

__all__ = [
    "AuthService",
    "_get_client_type",
    "_get_device_id",
    "_get_request_ip",
    "_get_user_agent",
]


class AuthService(LoginMixin, SessionMixin, CaptchaMixin, ProfileMixin, BootstrapMixin):
    """认证服务（组合 login/session/captcha/profile/bootstrap 五域）"""

    def __init__(self, session: Session):
        self.session = session
