import json
import logging
import time
from datetime import datetime
from typing import Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel import Session

from app.core.database import engine
from app.modules.base.model.sys import SysLog

logger = logging.getLogger(__name__)

# 敏感字段列表，用于日志脱敏
SENSITIVE_FIELDS = {
    "password", "old_password", "new_password", "confirm_password",
    "passwd", "pwd", "secret", "token", "access_token", "refresh_token",
    "api_key", "apikey", "private_key", "private_key",
    "phone", "mobile", "telephone", "id_card", "idcard", "idCard",
    "bank_card", "bankCard", "credit_card", "creditCard",
    "ssn", "social_security_number"
}


def _serialize_value(value: Any) -> Any:
    """
    安全地序列化值，处理 datetime 等特殊类型
    """
    if isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, (str, int, float, bool, type(None))):
        return value
    else:
        return str(value)


def mask_sensitive_data(data: dict, sensitive_fields: set = None) -> dict:
    """
    递归脱敏字典中的敏感字段

    Args:
        data: 待脱敏的字典
        sensitive_fields: 敏感字段集合，默认使用全局配置

    Returns:
        脱敏后的字典副本
    """
    if sensitive_fields is None:
        sensitive_fields = SENSITIVE_FIELDS

    if not isinstance(data, dict):
        return data

    masked = {}
    for key, value in data.items():
        key_lower = key.lower()
        # 检查是否为敏感字段
        if key_lower in sensitive_fields or any(s in key_lower for s in [s.lower() for s in sensitive_fields]):
            if key_lower in ("phone", "mobile", "telephone"):
                # 手机号保留前3后4位：138****5678
                if isinstance(value, str) and len(value) >= 7:
                    masked[key] = f"{value[:3]}****{value[-4:]}"
                else:
                    masked[key] = "****"
            elif key_lower in ("id_card", "idcard", "idcard", "ssn"):
                # 身份证保留前6后4位
                if isinstance(value, str) and len(value) >= 10:
                    masked[key] = f"{value[:6]}****{value[-4:]}"
                else:
                    masked[key] = "****"
            elif key_lower in ("bank_card", "bankcard", "credit_card", "creditcard"):
                # 银行卡保留前4后4位
                if isinstance(value, str) and len(value) >= 8:
                    masked[key] = f"{value[:4]}****{value[-4:]}"
                else:
                    masked[key] = "****"
            else:
                # 其他敏感字段完全隐藏
                masked[key] = "******"
        elif isinstance(value, dict):
            # 递归处理嵌套字典
            masked[key] = mask_sensitive_data(value, sensitive_fields)
        elif isinstance(value, list):
            # 处理列表中的字典项
            masked[key] = [
                mask_sensitive_data(item, sensitive_fields) if isinstance(item, dict) else _serialize_value(item)
                for item in value
            ]
        else:
            # 使用安全的序列化函数处理其他类型
            masked[key] = _serialize_value(value)

    return masked


class OperationLogMiddleware(BaseHTTPMiddleware):
    """
    操作日志中间件。
    记录管理端的所有修改类请求 (POST, PUT, DELETE)。
    """
    async def dispatch(self, request: Request, call_next):
        # 仅记录管理端且为修改类的请求
        if not request.url.path.startswith("/admin") or request.method not in ("POST", "PUT", "DELETE"):
            return await call_next(request)

        # 排除特定的白名单路径 (如登录、文件上传等，避免记录二进制大对象或敏感密码)
        if any(path in request.url.path for path in ("/login", "/upload", "/eps")):
            return await call_next(request)

        start_time = time.time()

        # 尝试获取 Body (注意：这会读取并消耗 stream，FastAPI 默认不推荐在中间件直接读取)
        # 生产环境建议使用自定义 APIRoute 或者是更优雅的拦截方式
        params = {}
        if request.method in ("POST", "PUT"):
            try:
                # 注意：大型 Body 或二进制直接读取会导致性能问题或错误
                body_bytes = await request.body()
                if body_bytes:
                    # 关键修复：重置请求体流，确保后续中间件和路由能再次读取 Body
                    request._body = body_bytes
                    async def _re_receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = _re_receive

                    params = json.loads(body_bytes.decode())
                    # 使用增强的脱敏函数处理敏感字段
                    params = mask_sensitive_data(params)
            except Exception as exc:
                logger.warning(f"解析请求Body失败 - {request.url.path}", exc_info=exc)
                params = {"_error": "failed_to_parse_body"}

        # 执行请求
        response = await call_next(request)

        # 记录日志 (异步或简单的同步写入)
        # 获取当前用户 (中间件可能拿不到 Depends(get_current_user))
        # 通常从 request.state.current_user 获取 (如果前序中间件已解析)
        current_user = getattr(request.state, "current_user", None)
        user_id = getattr(current_user, "id", None)

        try:
            with Session(engine) as session:
                log = SysLog(
                    user_id=user_id,
                    action=request.url.path,
                    method=request.method,
                    params=json.dumps(params, ensure_ascii=False) if params else None,
                    ip=request.client.host if request.client else None,
                    status=1 if response.status_code < 400 else 0,
                    message=f"Status: {response.status_code}"
                )
                session.add(log)
                session.commit()
        except Exception as exc:
            # 日志写入失败记录到错误日志，不影响主流程
            logger.error(
                f"操作日志写入失败 - path: {request.url.path}, method: {request.method}, user_id: {user_id}",
                exc_info=exc
            )

        return response
