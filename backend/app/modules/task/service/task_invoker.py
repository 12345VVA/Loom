"""
系统任务调用器 - 支持类 Midway 风格的服务方法动态调用
"""
from __future__ import annotations

import json
import time
import inspect
import asyncio
import threading
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, Type

from sqlmodel import Session

from app.core.database import engine

class TaskInvoker:
    """任务执行器，负责解析 service 字符串并执行对应的类方法"""

    _service_map: Dict[str, Type] = {}

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
        service_cls = cls._service_map.get(key)
        
        if not service_cls:
            # 尝试通过模块路径动态加载 (如果不在映射中)
            # 例如 app.modules.task.service.task_service:TaskInfoService:test
            if "." in key and ":" in service_path.replace(key, ""):
                raise ValueError(f"Service '{key}' not found in registry and dynamic loading not implemented for security.")
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
                        eq_filters={k: v for k, v in payload.items() if k not in ["page", "size", "keyword", "order", "sort"]},
                        raw_params=payload
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
