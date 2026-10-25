"""统一业务异常基类（渐进式引入）。

背景：service 层存量直接抛 fastapi.HTTPException（312 处/47 文件）——耦合 HTTP
语义且无法携带业务码段。BusinessError 与框架层解耦（不继承 HTTPException），
由异常处理器转 error envelope；存量 HTTPException 不迁移，新代码可用本基类。

用法：
    raise BusinessError("工单已关闭，无法撤回", code=ErrorCode.CONFLICT, status_code=409)
"""

from __future__ import annotations

from app.framework.api.error_codes import ErrorCode


class BusinessError(Exception):
    """业务规则异常：message 面向用户，code 为业务错误码，status_code 为 HTTP 映射。"""

    def __init__(
        self,
        message: str,
        *,
        code: int = ErrorCode.FAIL,
        status_code: int = 400,
        data: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = int(code)
        self.status_code = int(status_code)
        self.data = data
