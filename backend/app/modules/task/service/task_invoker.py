"""
系统任务调用器 - 支持类 Midway 风格的服务方法动态调用
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import threading
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session

from app.core.database import engine
from app.core.config import settings

logger = logging.getLogger(__name__)


class TaskInvoker:
    """任务执行器，负责解析 service 字符串并执行对应的类方法"""

    _service_map: dict[str, type] = {}

    # 显式白名单：允许通过 TaskInfo.service 调用的 service_path（格式 "key:method"）。
    # 为空时表示未启用白名单（仅拦截私有方法）；非空时仅放行已登记的服务路径。
    _allowed_services: set[str] = set()

    @classmethod
    def scan_services(cls):
        """扫描所有模块的 service 目录，建立服务映射表"""
        if cls._service_map:
            return

        modules_root = Path(__file__).resolve().parents[2]
        for module_dir in modules_root.iterdir():
            if not module_dir.is_dir() or module_dir.name.startswith("__"):
                continue

            service_dir = module_dir / "service"
            if not service_dir.exists():
                continue

            for service_file in service_dir.glob("*.py"):
                if service_file.name.startswith("__"):
                    continue

                module_path = f"app.modules.{module_dir.name}.service.{service_file.stem}"
                try:
                    mod = __import__(module_path, fromlist=["*"])
                    for name, obj in inspect.getmembers(mod, inspect.isclass):
                        if name.endswith("Service") and name != "BaseAdminCrudService":
                            # 从类名派生资源名 (例如 DictInfoService -> info)
                            # 1. 去失 Service 后缀
                            res_base = name.replace("Service", "")
                            # 2. 如果以模块名开头，去掉它
                            module_name = module_dir.name
                            import re

                            # 尝试匹配 ModuleNameResourceName 格式
                            match = re.match(f"^{module_name.capitalize()}(.*)", res_base)
                            if match:
                                resource_name = match.group(1).lower()
                            else:
                                resource_name = res_base.lower()

                            if not resource_name:
                                resource_name = "main"

                            # 注册短名：模块名.资源名
                            short_name = f"{module_name}.{resource_name}"
                            cls._service_map[short_name] = obj
                            # 同时也注册类名全称作为备选
                            cls._service_map[f"{module_name}.{name}"] = obj
                except Exception as e:
                    print(f"Failed to load service {module_path}: {e}")

        # 扫描完成后填充白名单（配置驱动优先，否则登记所有已扫描公开方法）
        cls._refresh_allowed_services()

    @classmethod
    def _refresh_allowed_services(cls) -> None:
        """根据 settings.TASK_ALLOWED_SERVICES 填充白名单。

        - 配置非空：仅允许列出的 "key:method"（fail-closed，便于收窄攻击面）。
        - 配置为空：登记所有已扫描 service 的公开（非下划线）方法，使白名单真正生效，
          而非空集形同虚设；行为等价于"已扫描 + 非下划线方法"放行，向后兼容。
        """
        configured = settings.TASK_ALLOWED_SERVICES
        if configured:
            cls._allowed_services = {item.strip() for item in configured.split(",") if item.strip()}
            return
        allowed: set[str] = set()
        for key, service_cls in cls._service_map.items():
            for name, _member in inspect.getmembers(service_cls, inspect.isfunction):
                if name.startswith("_"):
                    continue
                allowed.add(f"{key}:{name}")
        cls._allowed_services = allowed

    @classmethod
    def register_allowed_service(cls, service_path: str) -> None:
        """登记一个允许调用的 service_path（格式 "key:method"）到白名单。"""
        cls._allowed_services.add(service_path)

    @classmethod
    def register_allowed_services(cls, service_paths: list[str]) -> None:
        """批量登记允许调用的 service_path 列表到白名单。"""
        cls._allowed_services.update(service_paths)

    @classmethod
    def invoke(cls, service_path: str, data_json: str | None = None) -> Any:
        """
        执行任务逻辑
        :param service_path: 格式如 "task.info:test" 或 "dict.info:rebuild"
        :param data_json: 任务参数 (JSON 字符串)
        """
        cls.scan_services()

        if ":" not in service_path:
            raise ValueError(f"Invalid service path format: {service_path}. Expected 'service_key:method_name'")

        key, method_name = service_path.split(":", 1)

        # 安全校验 1：禁止调用以 _ 开头的私有/受保护方法
        if method_name.startswith("_"):
            logger.warning(
                "TaskInvoker rejected private method invocation: service_path=%s", service_path
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"不允许调用以下划线开头的方法: {method_name}",
            )

        # 安全校验 2：若已启用白名单（非空），则 service_path 必须在白名单中
        if cls._allowed_services and service_path not in cls._allowed_services:
            logger.warning(
                "TaskInvoker rejected non-whitelisted service invocation: service_path=%s", service_path
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"该服务方法不在允许调用的白名单中: {service_path}",
            )

        service_cls = cls._service_map.get(key)

        if not service_cls:
            # 尝试通过模块路径动态加载 (如果不在映射中)
            # 例如 app.modules.task.service.task_service:TaskInfoService:test
            if "." in key and ":" in service_path.replace(key, ""):
                raise ValueError(
                    f"Service '{key}' not found in registry and dynamic loading not implemented for security."
                )
            raise ValueError(f"Service '{key}' not found. Available services: {list(cls._service_map.keys())}")

        payload = {}
        if data_json:
            try:
                payload = json.loads(data_json)
            except Exception:
                payload = {"raw": data_json}

        # 实例化服务并执行
        with Session(engine) as session:
            # 实例化服务 (约定构造函数接受 session)
            instance = service_cls(session)
            method = getattr(instance, method_name, None)

            if not method:
                raise AttributeError(f"Method '{method_name}' not found in service '{key}' ({service_cls.__name__})")

            # 获取方法签名
            signature = inspect.signature(method)
            params = list(signature.parameters.values())

            # 准备调用参数
            invoke_args = []
            if len(params) > 0:
                first_param = params[0]
                # 情况 A: 期望 CrudQuery (通常是 list, page 方法)
                from app.framework.controller_meta import CrudQuery

                if first_param.annotation == CrudQuery or first_param.name == "query":
                    # 将 dict 转换为 CrudQuery
                    query = CrudQuery(
                        page=payload.get("page"),
                        size=payload.get("size"),
                        keyword=payload.get("keyword"),
                        order=payload.get("order"),
                        sort=payload.get("sort"),
                        eq_filters={
                            k: v for k, v in payload.items() if k not in ["page", "size", "keyword", "order", "sort"]
                        },
                        raw_params=payload,
                    )
                    invoke_args.append(query)
                # 情况 B: 期望普通 dict
                else:
                    invoke_args.append(payload)

            # 执行
            if inspect.iscoroutinefunction(method):
                return _run_coroutine_sync(method(*invoke_args))
            else:
                return method(*invoke_args)


def _run_coroutine_sync(coro):
    """在同步任务入口里安全执行协程。"""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in result:
        raise result["error"]
    return result.get("value")
