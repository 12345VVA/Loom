import json
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlmodel import Session

from app.core.database import engine
from app.modules.base.model.sys import SysLog

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
                    params = json.loads(body_bytes.decode())
                    # 脱敏：隐藏密码字段
                    if "password" in params:
                        params["password"] = "******"
            except:
                params = {"_error": "failed_to_parse_body"}

        # 执行请求
        response = await call_next(request)
        
        # 记录日志 (异步或简单的同步写入)
        # 获取当前用户 (中间件可能拿不到 Depends(get_current_user))
        # 通常从 request.state.current_user 获取 (如果前序中间件已解析)
        current_user = getattr(request.state, "current_user", None)
        user_id = getattr(current_user, "id", None)

        with Session(engine) as session:
            log = SysLog(
                user_id=user_id,
                action=request.url.path,
                method=request.method,
                params=json.dumps(params) if params else None,
                ip=request.client.host if request.client else None,
                status=1 if response.status_code < 400 else 0,
                message=f"Status: {response.status_code}"
            )
            session.add(log)
            session.commit()

        return response
