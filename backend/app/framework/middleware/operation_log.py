import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.framework.runtime import registry

logger = logging.getLogger(__name__)

# 敏感字段列表，用于日志脱敏
SENSITIVE_FIELDS = {
    "password",
    "old_password",
    "new_password",
    "confirm_password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "apiKey",
    "authorization",
    "private_key",
    "phone",
    "mobile",
    "telephone",
    "id_card",
    "idcard",
    "idCard",
    "bank_card",
    "bankCard",
    "credit_card",
    "creditCard",
    "ssn",
    "social_security_number",
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


class OperationLogMiddleware:
    """操作日志中间件：记录管理端修改类请求（POST/PUT/DELETE）的参数摘要。

    纯 ASGI 纪律（必守）：本中间件曾以 BaseHTTPMiddleware + ``await request.body()``
    实现——``request._body`` 缓存会让 ``wrapped_receive`` 在 SSE 挂起期的断连监听链
    中**永远返回合成的 http.request**（starlette base.py state3 首分支），被内侧层
    的 state2 判非 disconnect 击穿整条监听链（真机实测：所有 SSE 流必崩、前端只能
    靠 trace 兜底拉回复，表现为「每次对话都慢」）。读 body 必须走「一次读全 + 单条
    回放 + 后续透传」的纯 ASGI 模式（与 BodyBuffer 同构，不制造额外消息）。
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._should_log(scope):
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")
        status_holder = {"code": 0}

        async def send_capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message.get("status", 0)
            await send(message)

        params: dict[str, Any] = {}
        # 读 body（上游 BodyBuffer 已合并为单条；此处防御性读循环并限流）
        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message.get("type") != "http.request":
                break
            chunk = message.get("body", b"")
            chunks.append(chunk)
            total += len(chunk)
            if total > 1 * 1024 * 1024 or not message.get("more_body", False):
                break

        if chunks and method in ("POST", "PUT"):
            body_bytes = b"".join(chunks)
            if body_bytes:
                try:
                    if len(body_bytes) > 1 * 1024 * 1024:
                        params = {"_warning": "body_too_large"}
                    else:
                        params = mask_sensitive_data(json.loads(body_bytes.decode()))
                except Exception as exc:
                    logger.warning("解析请求Body失败 - %s", path, exc_info=exc)
                    params = {"_error": "failed_to_parse_body"}

        # 回放单条完整 body，后续透传原始 receive（uvicorn 队列只剩 disconnect，
        # 不向监听链制造任何额外 http.request——本缺陷的根因即在此）
        pending: list[Message] = [{"type": "http.request", "body": b"".join(chunks), "more_body": False}]

        async def replay_receive() -> Message:
            if pending:
                return pending.pop(0)
            return await receive()

        started = time.perf_counter()
        try:
            await self.app(scope, replay_receive, send_capture)
        finally:
            current_user = (scope.get("state") or {}).get("current_user")
            log_payload = {
                "user_id": getattr(current_user, "id", None),
                "action": path,
                "method": method,
                "params": json.dumps(params, ensure_ascii=False) if params else None,
                "ip": (scope.get("client") or (None,))[0],
                "status": 1 if 0 < status_holder["code"] < 400 else 0,
                "message": f"Status: {status_holder['code'] or 'no-response'} ({int((time.perf_counter() - started) * 1000)}ms)",
            }
            task = asyncio.create_task(asyncio.to_thread(_write_operation_log, log_payload))
            task.add_done_callback(_on_op_log_task_done)

    @staticmethod
    def _should_log(scope: Scope) -> bool:
        path = scope.get("path", "")
        if not path.startswith("/admin") or scope.get("method") not in ("POST", "PUT", "DELETE"):
            return False
        return not any(item in path for item in ("/login", "/upload", "/eps"))


def _write_operation_log(payload: dict[str, Any]) -> None:
    try:
        # SysLog ORM 依赖收敛于 base（DI 注册 "audit_write"），框架层只交付 payload
        registry.resolve("audit_write")(payload)
    except Exception as exc:
        logger.error(
            "操作日志写入失败 - path: %s, method: %s, user_id: %s",
            payload.get("action"),
            payload.get("method"),
            payload.get("user_id"),
            exc_info=exc,
        )


def _on_op_log_task_done(task: asyncio.Task) -> None:
    """兜底：避免 'Task exception was never retrieved' 警告。

    _write_operation_log 内部已有 try/except 记录业务失败，这里只兜未被捕获的意外。
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("操作日志异步任务未捕获异常: %s: %s", type(exc).__name__, exc, exc_info=exc)
