"""多设备会话域（AuthService 的 session 分域 mixin）：登出/被动登出/设备会话管理。"""

from __future__ import annotations

import time

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security import add_token_to_blacklist, decode_token
from app.modules.base.model.auth import User
from app.modules.base.service.authority_service import delete_session, list_user_sessions
from app.modules.base.service.security_service import get_refresh_token_payload


class SessionMixin:
    """多设备会话生命周期。依赖宿主提供 `self.session` 与 LoginMixin 的 `_record_login_log`。"""

    def logout(self, user: User, request: Request | None = None) -> None:
        """退出当前设备：仅拉黑当前 access token + 删除当前会话，不影响其他设备。

        多设备会话模型下，logout 不再递增 token_version（那会踢全部设备），
        也不再 clear_login_caches（那会清权限缓存、影响其他设备）。
        """
        sid = None
        # 拉黑当前 access token 并取出 sid（用于精确删除当前会话）
        if request:
            try:
                from app.modules.base.service.authority_service import extract_token

                token = extract_token(request)
                payload = decode_token(token)
                jti = payload.get("jti")
                exp = payload.get("exp")
                if jti and exp:
                    add_token_to_blacklist(jti, exp)
                sid = payload.get("sid")
            except Exception:
                # Token 解析失败不影响后续清理
                pass

        # 仅删除当前会话记录：其他设备的会话与 refresh 不受影响
        if sid:
            try:
                delete_session(user.id, sid)
            except Exception:
                pass

        # 登录日志写入失败不应阻塞登出流程
        try:
            self._record_login_log(
                request=request,
                user_id=user.id,
                name=user.full_name,
                account=user.username,
                login_type="logout",
                status=1,
            )
        except Exception:
            pass

    def revoke_by_cookie(self, request: Request) -> None:
        """best-effort 登出清理（被动登出）：仅凭 access token / refresh cookie
        删除当前会话记录。用于 access token 可能已失效场景，配合 _clear_refresh_token_cookie
        确保共享设备残留 cookie 不能被续期冒充。
        """
        user_id = None
        sid = None
        # access token 进黑名单并尝试取 user_id / sid（token 可能已失效，全部 try 忽略）
        try:
            from app.modules.base.service.authority_service import extract_token

            token = extract_token(request)
            payload = decode_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp")
            if jti and exp:
                add_token_to_blacklist(jti, exp)
            user_id = payload.get("sub") or payload.get("userId")
            sid = payload.get("sid")
        except Exception:
            pass

        # access token 失效时，从 refresh cookie 提取 user_id / sid
        if not user_id or not sid:
            try:
                refresh_token = request.cookies.get("refresh_token")
                if refresh_token:
                    refresh_payload = get_refresh_token_payload(refresh_token)
                    user_id = user_id or refresh_payload.get("sub")
                    sid = sid or refresh_payload.get("sid")
            except Exception:
                pass

        if user_id and sid:
            try:
                delete_session(int(user_id), sid)
            except Exception:
                pass

    def list_sessions(self, user: User, request: Request | None = None) -> list[dict]:
        """列出当前用户的活跃设备（按 device_id 聚合同设备的多次登录），标记当前设备。"""
        from app.modules.base.service.authority_service import _extract_device_id

        current_device_id = _extract_device_id(request) if request else None
        sessions = list_user_sessions(user.id)
        devices: dict[str, dict] = {}
        for item in sessions:
            device_id = item.get("device_id") or item.get("sid")
            entry = devices.get(device_id)
            if entry is None:
                entry = {
                    "deviceId": device_id,
                    "ip": item.get("ip"),
                    "userAgent": item.get("ua"),
                    "createdAt": item.get("created_at") or 0,
                    "lastActiveAt": item.get("last_active_at") or 0,
                    "_count": 0,
                }
                devices[device_id] = entry
            entry["_count"] += 1
            # 聚合同设备的多次登录：取最早创建 + 最后活跃
            if item.get("created_at") and item["created_at"] < entry["createdAt"]:
                entry["createdAt"] = item["created_at"]
            if item.get("last_active_at") and item["last_active_at"] > entry["lastActiveAt"]:
                entry["lastActiveAt"] = item["last_active_at"]
        result = [
            {
                "deviceId": entry["deviceId"],
                "ip": entry["ip"],
                "userAgent": entry["userAgent"],
                "createdAt": entry["createdAt"],
                "lastActiveAt": entry["lastActiveAt"],
                "sessionCount": entry["_count"],
                "current": entry["deviceId"] == current_device_id,
            }
            for entry in devices.values()
        ]
        result.sort(key=lambda x: x.get("lastActiveAt", 0), reverse=True)
        return result

    def revoke_device(self, user: User, device_id: str) -> None:
        """踢出当前用户的指定设备（device_id 必须属于本人），会踢该设备全部会话。"""
        sessions = list_user_sessions(user.id)
        target = [item for item in sessions if (item.get("device_id") or item.get("sid")) == device_id]
        if not target:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="设备不存在或已失效")
        for item in target:
            access_jti = item.get("access_jti")
            if access_jti:
                try:
                    add_token_to_blacklist(access_jti, int(time.time()) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
                except Exception:
                    pass
            delete_session(user.id, item.get("sid", ""))
