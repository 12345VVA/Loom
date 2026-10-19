"""AI 运行时调用边界领域异常（ai↔media/notification 解耦批次3，2026-10-18）。

``AiInvocationError`` 是 ai 运行时（runtime_service / registry_service /
security_service）对消费方抛出的**唯一**异常类型：调用失败、配置缺失、
治理阻断、能力缺失、安全拦截统一收口，携带 HTTP 语义 ``status_code``
供 web 层与消费方判别。

设计取舍（对核实报告 §四批次3"纯领域异常"方案的有意偏差——继承
HTTPException 而非 RuntimeError）：
- framework 层禁 import 业务模块（架构守卫白名单为空），纯领域异常的
  全局 HTTP 转换 handler 无处安放；
- 继承使既有 HTTPException handler 与消费方既有防御（error_format 等）
  零改动兼容，HTTP 响应定义性不变；
- 核心收益完整保留：消费方得以窄类型 ``except AiInvocationError``，
  替代语义过载的 ``except HTTPException``（见 workflow_memory 未配置态）。
"""

from __future__ import annotations

from fastapi import HTTPException


class AiInvocationError(HTTPException):
    """AI 调用边界失败（配置缺失 404 / 配置不可用 400 / 安全拦截 400 /
    治理阻断 429 / 治理不可用 503 / 能力缺失 501 / 调用失败 400）。"""

    def __init__(self, detail: str, *, status_code: int = 400):
        super().__init__(status_code=status_code, detail=detail)
