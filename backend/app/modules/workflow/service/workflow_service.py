"""
工作流核心管理与运行时服务。
"""
import asyncio
import copy
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.ai.model.ai import AiChatRequest, AiRuntimeMessage
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowExecutionLog,
    WorkflowInstance,
)
from app.modules.workflow.service.compiler import WorkflowCompiler, WorkflowState, node_registry, render_template, safe_eval, strip_braces

logger = logging.getLogger(__name__)


# 全局工作流事件订阅器，用于实时流式推送（规避循环导入）
workflow_event_listeners = []

# Checkpoint 持久化存储由工厂函数按配置动态选择后端
from app.modules.workflow.service.checkpointer import get_checkpointer
# 跨进程事件总线（Redis pub/sub + 进程内 fallback）
from app.modules.workflow.service.event_bus import publish_event


# --- 统一的 AI 运行时操作封装 (避免局部 SessionLocal 导入重复与异常静默吞没) ---

def run_ai_chat(
    profile_code: str,
    user_prompt: str,
    system_prompt: str | None = None,
    response_format: dict[str, Any] | None = None,
) -> str:
    """
    统一驱动对话模型，做空响应拦截防御。
    response_format 支持 json_schema / json_object / None(纯文本)。
    """
    from app.core.database import SessionLocal
    with SessionLocal() as session:
        runtime_service = AiModelRuntimeService(session)
        
        messages = []
        if system_prompt and system_prompt.strip():
            messages.append(AiRuntimeMessage(role="system", content=system_prompt))
        messages.append(AiRuntimeMessage(role="user", content=user_prompt))

        chat_request = AiChatRequest(
            profile_code=profile_code,
            messages=messages,
            response_format=response_format,
            skip_masking=True,
        )
        result = runtime_service.chat(chat_request)

        if not result.get("success"):
            raise ValueError(f"大模型调用失败: {result.get('errorMessage') or result.get('message') or '未返回详情'}")

        content = result.get("content")
        if not content:
            raise ValueError("大模型返回内容为空")
        return content


def run_ai_image(
    profile_code: str,
    prompt: str,
    size: str | None = None,
    image: str | list[str] | None = None,
    custom_options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    统一驱动图像模型，做空响应拦截防御，并支持自适应尺寸与参考图。
    返回 {"url": ..., "result": ..., "request_payload": ...} 以便调用方进一步持久化。
    """
    from app.core.database import SessionLocal
    with SessionLocal() as session:
        runtime_service = AiModelRuntimeService(session)
        from app.modules.ai.model.ai import AiImageRequest

        # 组装参数
        options = dict(custom_options or {})
        if size:
            options["size"] = size

        image_request = AiImageRequest(
            profile_code=profile_code,
            prompt=prompt,
            image=image or None,
            options=options
        )
        result = runtime_service.image(image_request)

        data = result.get("data", [])
        if not data:
            raise ValueError(f"绘图大模型响应的图片列表为空。错误详情: {result.get('errorMessage') or '未返回详情'}")

        image_url = data[0].get("url", "")
        request_payload = {"prompt": prompt, "options": options, "size": size}
        return {"url": image_url, "result": result, "request_payload": request_payload}


# --- 1. 注册核心节点执行逻辑 ---

def _field_to_schema(f: dict) -> dict[str, Any]:
    field_type = f.get("type", "string").strip()
    desc = f.get("description", "").strip()
    
    schema = {}
    if desc:
        schema["description"] = desc
        
    if field_type == "object":
        schema["type"] = "object"
        properties = {}
        required = []
        for child in (f.get("children") or []):
            child_name = child.get("name", "").strip()
            if not child_name or child_name == "[Item]":
                continue
            properties[child_name] = _field_to_schema(child)
            required.append(child_name)
        schema["properties"] = properties
        schema["required"] = required
        schema["additionalProperties"] = False
        
    elif field_type == "array_object":
        schema["type"] = "array"
        properties = {}
        required = []
        for child in (f.get("children") or []):
            child_name = child.get("name", "").strip()
            if not child_name:
                continue
            properties[child_name] = _field_to_schema(child)
            required.append(child_name)
        schema["items"] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False
        }
        
    elif field_type == "array_string":
        schema["type"] = "array"
        schema["items"] = {"type": "string"}
        
    elif field_type == "array_number":
        schema["type"] = "array"
        schema["items"] = {"type": "number"}
        
    elif field_type == "array_boolean":
        schema["type"] = "array"
        schema["items"] = {"type": "boolean"}
        
    elif field_type == "array":
        schema["type"] = "array"
        children = f.get("children") or []
        if children:
            schema["items"] = _field_to_schema(children[0])
        else:
            schema["items"] = {"type": "string"}
            
    else:
        # 兼容 OpenAI Schema 规范，确保 boolean, number/integer, string 类型正确
        schema["type"] = field_type
        
    return schema


def _build_json_schema_from_fields(
    json_fields: list[dict],
    schema_name: str = "workflow_output",
) -> dict[str, Any] | None:
    """
    将工作流 jsonFields [{name, type, description, children}] 转为 OpenAI 兼容的 JSON Schema。
    无有效字段时返回 None（调用方应回退到 json_object）。
    """
    if not json_fields:
        return None

    properties: dict[str, Any] = {}
    required: list[str] = []
    for f in json_fields:
        name = f.get("name", "").strip()
        if not name or name == "[Item]":
            continue
        properties[name] = _field_to_schema(f)
        required.append(name)

    if not properties:
        return None

    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def _build_json_desc_recursive(fields: list[dict], indent: int = 1) -> str:
    parts = []
    indent_space = "  " * indent
    for f in fields:
        name = f.get("name")
        if not name:
            continue
        desc = f.get("description", "")
        field_type = f.get("type", "string").strip()
        
        desc_str = f" ({desc})" if desc else ""
        
        if field_type == "object":
            children_str = _build_json_desc_recursive(f.get("children") or [], indent + 1)
            parts.append(f'{indent_space}"{name}": {{\n{children_str}\n{indent_space}}}')
        elif field_type == "array_object":
            children_str = _build_json_desc_recursive(f.get("children") or [], indent + 2)
            indent_next = "  " * (indent + 1)
            parts.append(f'{indent_space}"{name}": [\n{indent_next}{{\n{children_str}\n{indent_next}}}\n{indent_space}]')
        elif field_type == "array_string":
            parts.append(f'{indent_space}"{name}": [string{desc_str}]')
        elif field_type == "array_number":
            parts.append(f'{indent_space}"{name}": [number{desc_str}]')
        elif field_type == "array_boolean":
            parts.append(f'{indent_space}"{name}": [boolean{desc_str}]')
        elif field_type == "array":
            children = f.get("children") or []
            if children:
                item_field = children[0]
                item_type = item_field.get("type", "string").strip()
                if item_type == "object":
                    item_str = _build_json_desc_recursive(item_field.get("children") or [], indent + 2)
                    indent_next = "  " * (indent + 1)
                    parts.append(f'{indent_space}"{name}": [\n{indent_next}{{\n{item_str}\n{indent_next}}}\n{indent_space}]')
                else:
                    item_desc = item_field.get("description", "")
                    item_desc_str = f" ({item_desc})" if item_desc else ""
                    parts.append(f'{indent_space}"{name}": [{item_type}{item_desc_str}]')
            else:
                parts.append(f'{indent_space}"{name}": []')
        else:
            parts.append(f'{indent_space}"{name}": {field_type}{desc_str}')
            
    return ",\n".join(parts)


async def execute_llm_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 节点执行逻辑，支持分层 JSON 输出：
    Tier 1: json_schema（有 jsonFields 时自动生成 Schema）
    Tier 2: json_object（宽松 JSON 模式）
    Tier 3: 纯文本（无 response_format）
    """
    profile_code = config.get("model_profile_code")
    system_prompt_template = config.get("system_prompt_template", "")
    user_prompt_template = config.get("prompt_template", "")
    output_variable = config.get("output_variable", "output")

    output_format = config.get("output_format", "text")
    json_fields = config.get("json_fields", [])
    response_format = None
    
    # 确定格式化指令应该追加到哪里（优先追加到 System Prompt）
    format_instructions = ""

    if output_format == "json":
        # Tier 1: json_schema — 有字段定义时生成 Schema
        schema = _build_json_schema_from_fields(json_fields)
        if schema:
            response_format = schema
        else:
            # Tier 2: json_object — 无字段定义，宽松模式
            response_format = {"type": "json_object"}

        # 文本指令始终追加作为兜底
        if json_fields:
            field_desc = _build_json_desc_recursive(json_fields, 1)
            format_instructions = (
                f'\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。\n'
                f'JSON 结构如下：\n{{\n{field_desc}\n}}'
            )
        else:
            format_instructions = (
                '\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。'
            )

    elif output_format == "json_object":
        # Tier 2: json_object — 用户显式选择宽松模式
        response_format = {"type": "json_object"}
        format_instructions = (
            '\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。'
        )

    if format_instructions:
        if system_prompt_template.strip():
            system_prompt_template += format_instructions
        else:
            user_prompt_template += format_instructions

    # 移除强制的系统级安全指令，交给统一的 AiSecurityService 处理

    # 渲染 Prompt 变量
    system_prompt = render_template(system_prompt_template, variables) if system_prompt_template else None
    user_prompt = render_template(user_prompt_template, variables)

    # 调用统一的 AI 对话驱动
    content = await asyncio.to_thread(run_ai_chat, profile_code, user_prompt, system_prompt, response_format)

    # JSON 模式自动解析结构化输出
    if output_format in ("json", "json_object"):
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r'^```\w*\n?', '', stripped)
            stripped = re.sub(r'\n?```\s*$', '', stripped)
        try:
            return {output_variable: json.loads(stripped)}
        except json.JSONDecodeError:
            logger.warning("LLM JSON 输出解析失败，保留原始文本")

    return {output_variable: content}


async def execute_tool_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    [Mock] 工具节点执行逻辑 (Mock 工具动作)
    """
    tool_name = config.get("tool_name", "unknown")
    output_variable = config.get("output_variable", "tool_result")

    # 优先使用 mock_data 配置，否则返回通用模拟结果
    mock_data = config.get("mock_data")
    if mock_data:
        await asyncio.sleep(0.3)
        return {output_variable: mock_data}

    # 模拟工具执行延迟
    await asyncio.sleep(0.5)

    return {output_variable: f"Mock Tool '{tool_name}' executed successfully with context."}


async def execute_human_input_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    人工输入/审批节点。
    利用 LangGraph 的内置 interrupt 特性挂起运行。
    """
    from langgraph.errors import GraphInterrupt
    message = config.get("message", "需要人工审批")
    output_variable = config.get("output_variable", "approval_result")

    # 抛出 GraphInterrupt，使工作流在当前步骤被挂起
    # 当恢复运行时，可通过 Command 传递人类回执值，这会在 resume 状态下接收到
    from langgraph.types import interrupt
    
    # 在 LangGraph 中，当运行到此处且无 resume 信号时，会在此触发暂停
    user_response = interrupt({
        "message": message,
        "output_variable": output_variable
    })
    
    return {output_variable: user_response}


# 注册至全局注册表
node_registry.register("llm", execute_llm_node)
node_registry.register("tool", execute_tool_node)
node_registry.register("human_input", execute_human_input_node)


# --- 2. 高级节点执行函数定义与注册 ---

async def execute_intent_classifier_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    意图识别与语义分流节点执行逻辑
    """
    node_id = config.get("id", "intent_classifier")
    input_var = config.get("input_variable", "")
    if input_var:
        var_name = strip_braces(input_var.strip())
        query = str(variables.get(var_name, ""))
    else:
        query = variables.get("query") or variables.get("user_query") or ""
    intents = config.get("intents", [])
    default_route = config.get("default_route")
    profile_code = config.get("model_profile_code")

    if not intents:
        return {f"{node_id}_selected_route": default_route}

    # 1. 组装意图引导 Prompt
    intents_desc = "\n".join([f"- {i.get('name')}: {i.get('description', '')}" for i in intents])
    
    prompt = f"""请分析以下用户的输入，并将其准确归类到以下意图类别之一。

可选意图类别列表：
{intents_desc}
- 其他: 不符合上述任何意图的杂项输入

用户的输入文本：
\"\"\"
{query}
\"\"\"

请注意：你必须仅输出匹配到的“意图名称”。不要包含任何其他修饰文本、标点符号或解释说明。如果无法匹配任何意图，请输出“其他”。"""

    # 2. 调用 AI 运行时大模型 (通过 asyncio.to_thread 避免同步阻塞)
    try:
        # 这里仅使用 user_prompt 即可
        matched_intent_name = (await asyncio.to_thread(run_ai_chat, profile_code, prompt)).strip()
    except Exception as e:
        logger.error(f"意图分类大模型调用失败: {e}")
        matched_intent_name = "其他"

    # 3. 匹配目标跳转路由
    selected_route = default_route
    for intent in intents:
        if intent.get("name") == matched_intent_name:
            selected_route = intent.get("target_route")
            break
            
    if matched_intent_name == "其他" or not selected_route:
        selected_route = default_route

    return {f"{node_id}_selected_route": selected_route}


async def execute_loop_controller_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    循环控制器节点执行逻辑（状态链式循环：上一次迭代的输出作为下一次的输入）。
    只在循环开始前做一次 deepcopy，后续迭代链式传递状态，支持跨迭代状态累积。
    """
    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError(
            "循环控制器节点缺少已编译的体子图。"
            "请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。"
        )
    list_var = strip_braces(config.get("list_variable") or config.get("array_variable", "list_variable"))
    item_var = config.get("item_variable", "loop_item")
    output_var = config.get("output_variable", "loop_results")
    stop_on_error = config.get("stop_on_error", True)

    items = variables.get(list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}

    # 只做一次初始拷贝，后续迭代链式传递状态
    iter_vars = copy.deepcopy(variables)
    results = []
    index_key = f"{item_var}_index"

    for idx, item in enumerate(items):
        iter_vars[item_var] = item
        iter_vars[index_key] = idx
        body_state = {"messages": [], "variables": iter_vars, "current_node": "start"}
        try:
            body_result = await compiled_body.ainvoke(body_state)
            iter_vars = body_result.get("variables", {})
            # 收集本次迭代的关键输出（排除临时注入的循环变量）
            iter_output = {k: v for k, v in iter_vars.items()
                          if k != item_var and k != index_key}
            results.append(iter_output)
            logger.info("[Loop] Iteration %d/%d complete: item=%s", idx + 1, len(items), str(item)[:80])
        except Exception as e:
            logger.error("[Loop] Iteration %d/%d failed: %s", idx + 1, len(items), e)
            results.append({"error": str(e)})
            if stop_on_error:
                break

    return {output_var: results}


async def execute_batch_processor_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    批处理并发节点执行逻辑（子图模式：并发遍历列表，每项独立调用体子图）。
    使用 asyncio.gather + Semaphore 控制并发，return_exceptions=True 容错。
    """
    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError(
            "批处理节点缺少已编译的体子图。"
            "请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。"
        )
    list_var = strip_braces(config.get("list_variable") or config.get("array_variable", "batch_list_variable"))
    item_var = config.get("item_variable", "batch_item")
    output_var = config.get("output_variable", "batch_results")
    concurrency_limit = min(max(int(config.get("concurrency_limit", 5) or 5), 1), 20)

    items = variables.get(list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_body(item: Any) -> Dict[str, Any]:
        async with semaphore:
            iter_vars = copy.deepcopy(variables)
            iter_vars[item_var] = item
            body_state = {"messages": [], "variables": iter_vars, "current_node": "start"}
            body_result = await compiled_body.ainvoke(body_state)
            return body_result.get("variables", {})

    raw_results = await asyncio.gather(
        *[run_body(item) for item in items],
        return_exceptions=True
    )

    results = []
    for r in raw_results:
        if isinstance(r, Exception):
            logger.error("[Batch] Single iteration failed: %s", r)
            results.append({"error": str(r)})
        else:
            results.append(r)

    logger.info("[Batch] All %d iterations complete (concurrency=%d)", len(items), concurrency_limit)
    return {output_var: results}


async def execute_image_generator_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    生图节点执行逻辑，已增强支持自适应尺寸、参考图、以及自定义 options。
    生成的图片自动转存到媒体资源库，返回永久存储 URL。
    """
    from app.core.database import SessionLocal
    from app.modules.media.service.media_service import MediaAssetService

    profile_code = config.get("model_profile_code")
    prompt_template = config.get("prompt_template", "")
    size = config.get("size") or None
    output_variable = config.get("output_variable", "image_url")

    # 1. 渲染提示词模版
    prompt = render_template(prompt_template, variables)

    # 2. 提取参考图片参数
    image_val = None
    image_var = config.get("image_variable")
    if image_var:
        image_val = variables.get(image_var)
    if not image_val and config.get("image_template"):
        try:
            image_val = render_template(config.get("image_template"), variables)
        except Exception:
            pass

    # 3. 合并自定义参数（支持前端 optionsJson 字段）
    custom_options = config.get("options") or {}
    options_json = config.get("options_json") or ""
    if options_json.strip():
        try:
            parsed = json.loads(options_json)
            if isinstance(parsed, dict):
                custom_options = {**custom_options, **parsed}
        except json.JSONDecodeError:
            logger.warning(f"生图节点 optionsJson 解析失败: {options_json}")

    # 4. 调用 AI 生图
    try:
        ai_result = await asyncio.to_thread(
            run_ai_image, profile_code, prompt, size, image_val, custom_options
        )
    except Exception as e:
        logger.error(f"工作流生图 API 呼叫失败: {e}")
        return {output_variable: ""}

    temp_url = ai_result["url"]
    if not temp_url:
        return {output_variable: ""}

    # 5. 转存到媒体资源库
    permanent_url = temp_url
    try:
        permanent_url = await asyncio.to_thread(
            _persist_image_to_media,
            ai_result["result"],
            ai_result["request_payload"],
            profile_code,
        )
        logger.info(f"工作流生图转存成功: temp={temp_url[:80]}... → permanent={permanent_url}")
    except Exception as e:
        logger.warning(f"工作流生图转存失败，使用临时 URL: {e}")

    return {output_variable: permanent_url}


def _persist_image_to_media(
    result: dict[str, Any],
    request_payload: dict[str, Any],
    profile_code: str | None = None,
) -> str:
    """将 AI 生图结果转存到媒体资源库，返回永久存储 URL。转存失败时抛异常由调用方兜底。"""
    from app.core.database import SessionLocal
    from app.modules.media.service.media_service import MediaAssetService

    with SessionLocal() as session:
        media_service = MediaAssetService(session)
        assets = media_service.create_from_ai_result(
            task_type="image",
            result=result,
            request_payload=request_payload,
            source_type="workflow",
            profile_code=profile_code,
        )
        # 正常转存成功
        if assets:
            try:
                url = assets[0].storage_url
                if url:
                    return url
            except Exception:
                pass  # 去重场景：asset 已被 session.delete，属性访问可能异常

        # 去重兜底：按 original_url 查找已有的同源资产
        data = result.get("data", [])
        original_url = data[0].get("url", "") if data else ""
        if original_url:
            from app.modules.media.model.media import MediaAsset as MA
            existing = session.exec(
                select(MA).where(
                    MA.original_url == original_url,
                    MA.status == "success",
                    MA.delete_time == None,  # noqa: E711
                ).order_by(MA.created_at.desc())
            ).first()
            if existing and existing.storage_url:
                return existing.storage_url

        raise ValueError("媒体转存未返回有效存储地址")


async def tool_web_search(query: str, max_results: int = 3) -> str:
    """
    [Mock] 网页搜索占位工具实现
    """
    await asyncio.sleep(0.3)
    return f"[搜索引擎结果] '{query}'：\n1. AI内容生成大屏看板与工作流完美整合。\n2. LangGraph 极力推荐用在复杂循环多步场景。"


async def tool_file_system(filename: str, content: str = None) -> str:
    """
    [Mock] 本地文件系统读写占位工具实现
    """
    await asyncio.sleep(0.1)
    if content:
        return f"[本地文件系统] 成功存储文件 '{filename}'，大小：{len(content)} 字节"
    return f"[本地文件系统] 成功拉取文件 '{filename}'，内容预览：'工作流演示。'"


async def tool_mock_weather_api(location: str) -> str:
    """
    [Mock] 天气查询占位工具实现
    """
    await asyncio.sleep(0.3)
    return json.dumps({
        "location": location,
        "temperature": "26°C",
        "condition": "晴",
        "humidity": "45%",
        "wind": "微风",
    }, ensure_ascii=False)


async def execute_tool_executor_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    通用工具执行器节点逻辑
    """
    tool_code = config.get("tool_code", "unknown")
    arguments = variables.get("arguments") or config.get("arguments") or {}
    if not arguments:
        arguments_json_str = config.get("arguments_json", "")
        if arguments_json_str:
            try:
                arguments = json.loads(arguments_json_str)
            except json.JSONDecodeError:
                arguments = {}
    output_variable = config.get("output_variable", "tool_result")

    # 参数级联转换
    resolved_args = {}
    for arg_name, arg_val in arguments.items():
        if isinstance(arg_val, str) and arg_val.startswith("variables."):
            var_key = arg_val.removeprefix("variables.")
            resolved_args[arg_name] = variables.get(var_key)
        else:
            resolved_args[arg_name] = arg_val

    try:
        if tool_code == "web_search":
            query = resolved_args.get("query", "")
            res = await tool_web_search(query, int(resolved_args.get("max_results", 3)))
        elif tool_code == "file_system":
            filename = resolved_args.get("filename", "output.txt")
            content = resolved_args.get("content")
            res = await tool_file_system(filename, content)
        elif tool_code == "mock_weather_api":
            location = resolved_args.get("location", "未知")
            res = await tool_mock_weather_api(location)
        else:
            res = f"[工具中心] 找不到系统工具 Code: '{tool_code}'"
    except Exception as e:
        res = f"[工具中心报错] 执行异常: {e}"

    return {output_variable: res}


def _render_output_field_recursive(field: dict, variables: Dict[str, Any]) -> Any:
    field_type = field.get("type", "string").strip()
    
    if field_type == "object":
        result = {}
        for child in (field.get("children") or []):
            child_name = child.get("name", "")
            if not child_name:
                continue
            result[child_name] = _render_output_field_recursive(child, variables)
        return result
        
    elif field_type == "array":
        result = []
        for child in (field.get("children") or []):
            result.append(_render_output_field_recursive(child, variables))
        return result
        
    else:
        value_tpl = field.get("value", "")
        if isinstance(value_tpl, str):
            rendered = render_template(value_tpl, variables)
            try:
                return json.loads(rendered)
            except (json.JSONDecodeError, ValueError):
                return rendered
        return value_tpl


async def execute_variable_assignment_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    变量赋值节点执行逻辑。支持按字面量或表达式计算赋值。
    """
    assignments = config.get("assignments", [])
    updates = {}
    for assign in assignments:
        var_name = assign.get("variable_name")
        val_type = assign.get("value_type", "string")
        val = assign.get("value", "")
        
        if not var_name:
            continue
            
        if val_type == "string":
            updates[var_name] = str(val)
        elif val_type == "number":
            try:
                updates[var_name] = float(val) if "." in str(val) else int(val)
            except ValueError:
                updates[var_name] = 0
        elif val_type == "boolean":
            updates[var_name] = str(val).lower() in ("true", "1", "yes")
        elif val_type == "expression":
            try:
                # 包含 updates 允许前后变量依赖
                ctx = {**variables, **updates}
                updates[var_name] = safe_eval(str(val), ctx)
            except Exception as e:
                logger.warning(f"变量赋值表达式 '{val}' 执行失败: {e}")
                updates[var_name] = None
        else:
            updates[var_name] = val
            
    return updates


async def execute_variable_transform_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    变量转换/聚合节点执行逻辑。
    """
    input_var = strip_braces(config.get("input_variable", ""))
    transform_type = config.get("transform_type", "join_array")
    transform_args = config.get("transform_args", {})
    output_var = config.get("output_variable", "transformed_value")

    input_val = variables.get(input_var)
    result = None

    try:
        if transform_type == "join_array":
            separator = transform_args.get("separator", ",")
            if isinstance(input_val, list):
                result = separator.join(str(x) for x in input_val)
            elif input_val is not None:
                result = str(input_val)

        elif transform_type == "extract_json_path":
            if input_val is None:
                result = None
            else:
                path = transform_args.get("path", "")
                if isinstance(input_val, str):
                    try:
                        data = json.loads(input_val)
                    except json.JSONDecodeError:
                        data = {}
                else:
                    data = input_val

                if not path or not isinstance(data, (dict, list)):
                    result = data
                else:
                    parts = path.split(".")
                    curr = data
                    for part in parts:
                        if isinstance(curr, dict) and part in curr:
                            curr = curr[part]
                        elif isinstance(curr, list):
                            try:
                                idx = int(part)
                            except ValueError:
                                curr = None
                                break
                            if -len(curr) <= idx < len(curr):
                                curr = curr[idx]
                            else:
                                curr = None
                                break
                        else:
                            curr = None
                            break
                    result = curr

        elif transform_type == "eval_expression":
            expression = transform_args.get("expression", "")
            ctx = {**variables, "input_value": input_val}
            result = safe_eval(expression, ctx)

        else:
            result = input_val
            
    except Exception as e:
        logger.warning(f"变量转换节点执行异常: {e}")
        result = None
        
    if not output_var:
        return {}
    return {output_var: result}


async def execute_end_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    结束节点：支持结构化字段输出和文本/JSON 两种模式（支持多层嵌套结构）
    """
    output_format = config.get("output_format", "")

    if output_format == "json" and config.get("output_fields"):
        # 结构化字段模式：递归渲染嵌套字段
        result = {}
        for field in config["output_fields"]:
            name = field.get("name", "")
            if not name:
                continue
            result[name] = _render_output_field_recursive(field, variables)
        return {"workflow_output": result}
    else:
        # 文本模式或旧数据兼容（使用 output_template）
        output_template = config.get("output_template", "")
        if not output_template or not output_template.strip():
            return {}
        rendered = render_template(output_template, variables)
        try:
            workflow_output = json.loads(rendered)
        except json.JSONDecodeError:
            workflow_output = rendered
        return {"workflow_output": workflow_output}


async def execute_condition_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    二元条件分支节点执行逻辑。路由通过条件边处理，此执行体仅作为节点执行标记。
    """
    return {}


async def execute_switch_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    分支选择器节点执行逻辑。由于路由通过条件边处理，此执行体无需状态修改，仅作为节点执行标记。
    """
    return {}


# 注册新高级节点执行器至全局注册表
node_registry.register("intent_classifier", execute_intent_classifier_node)
node_registry.register("loop_controller", execute_loop_controller_node)
node_registry.register("batch_processor", execute_batch_processor_node)
node_registry.register("image_generator", execute_image_generator_node)
node_registry.register("tool_executor", execute_tool_executor_node)
node_registry.register("end", execute_end_node)
node_registry.register("condition", execute_condition_node)
node_registry.register("switch", execute_switch_node)
node_registry.register("variable_assignment", execute_variable_assignment_node)
node_registry.register("variable_transform", execute_variable_transform_node)


# --- 2. 工作流服务逻辑 ---

class WorkflowService(BaseAdminCrudService):
    """
    工作流定义管理与执行服务
    """
    def __init__(self, session: Session):
        super().__init__(session, WorkflowDefinition)

    def _before_add(self, data: dict) -> dict:
        """
        新增前的校验与逻辑
        """
        # 1. 唯一性校验
        code = data.get("code")
        if code:
            existing = self.session.exec(
                select(WorkflowDefinition).where(WorkflowDefinition.code == code)
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 2. 拓扑 JSON 基础校验
        graph_json_str = data.get("graph_json")
        if graph_json_str and graph_json_str != "{}":
            try:
                graph_json = json.loads(graph_json_str)
                if not isinstance(graph_json, dict) or "nodes" not in graph_json or "edges" not in graph_json:
                    raise ValueError("工作流拓扑结构不合法")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"保存失败：画布拓扑 JSON 校验失败: {e}")

        return data

    def _before_update(self, data: dict, entity: Any) -> dict:
        """
        为了支持局部更新（如 cl-switch 仅传 id 和 is_active），
        这里过滤掉未传值（即为 None）的字段，并执行唯一性及拓扑 JSON 校验。
        """
        # 1. 唯一性校验
        code = data.get("code")
        if code and code != entity.code:
            existing = self.session.exec(
                select(WorkflowDefinition).where(WorkflowDefinition.code == code)
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 2. 拓扑 JSON 基础校验
        graph_json_str = data.get("graph_json")
        if graph_json_str and graph_json_str != "{}":
            try:
                graph_json = json.loads(graph_json_str)
                if not isinstance(graph_json, dict) or "nodes" not in graph_json or "edges" not in graph_json:
                    raise ValueError("工作流拓扑结构不合法")
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"保存失败：画布拓扑 JSON 校验失败: {e}")

        # 注意：此处过滤 None 值（即未显式传递的 Optional 字段）是为了在 cl-switch 局部更新
        # （只传递了 id 和 status/is_active 等）场景下，避免将其余未传字段覆盖更新为 Null。
        # 其副作用是无法通过传递 None/Null 的更新请求将某个字段显式清空。
        # 在本模块（WorkflowDefinitionUpdateRequest 中 description/graph_json 等均为 Optional[str] = None）
        # 场景下目前安全，在此保留此注释以提请后续维护注意该局部更新语义。
        return {k: v for k, v in data.items() if v is not None}


class WorkflowInstanceService(BaseAdminCrudService):
    """
    工作流实例管理服务
    """
    def __init__(self, session: Session):
        super().__init__(session, WorkflowInstance)

    async def start_instance(self, definition_id: int, inputs: Dict[str, Any]) -> WorkflowInstance:
        """
        创建一个工作流实例并启动异步执行
        """
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition or not definition.is_active:
            raise HTTPException(status_code=404, detail="工作流定义不存在或未启用")

        # 2秒防重放：检查是否有相同参数且相同定义的实例在最近运行中
        from datetime import datetime, timedelta
        two_seconds_ago = datetime.utcnow() - timedelta(seconds=2)
        
        stmt = select(WorkflowInstance).where(
            WorkflowInstance.definition_id == definition_id,
            WorkflowInstance.status == "running",
            WorkflowInstance.created_at >= two_seconds_ago
        )
        recent_instances = self.session.exec(stmt).all()
        for inst in recent_instances:
            if inst.state_data == json.dumps(inputs):
                raise HTTPException(status_code=400, detail="检测到重复的启动请求，请稍后再试。")

        # 初始化实例记录
        thread_id = str(uuid4())
        instance = WorkflowInstance(
            definition_id=definition.id,
            thread_id=thread_id,
            status="running",
            state_data=json.dumps(inputs),
            current_node=None
        )
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)

        # 通过 Celery 异步任务执行工作流（从 Web 进程剥离至独立 Worker）
        from app.modules.workflow.tasks.workflow_tasks import execute_workflow

        task = execute_workflow.delay(instance.id, definition.id, json.dumps(inputs))
        instance.celery_task_id = task.id
        self.session.add(instance)
        self.session.commit()

        return instance

    async def resume_instance(self, instance_id: int, user_input: Any) -> WorkflowInstance:
        """
        恢复暂停中的工作流实例并传入人类交互值
        """
        instance = self.session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="工作流实例不存在")
        if instance.status != "paused":
            raise HTTPException(status_code=400, detail="只有处于挂起暂停状态的工作流实例才可以恢复")

        definition = self.session.get(WorkflowDefinition, instance.definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="关联的工作流定义丢失")

        # 更新状态为运行中
        instance.status = "running"
        self.session.add(instance)
        self.session.commit()

        # 通过 Celery 异步任务恢复执行，Command(resume=user_input) 继续
        from app.modules.workflow.tasks.workflow_tasks import execute_workflow

        task = execute_workflow.delay(instance.id, definition.id, instance.state_data, json.dumps(user_input))
        instance.celery_task_id = task.id
        self.session.add(instance)
        self.session.commit()

        return instance

    # ==========================================
    # 节点级运行（开发期调试 / 强一致性）
    # ==========================================

    async def test_node(self, definition_id: int, node_id: str, mock_variables: Dict[str, Any]) -> "NodeTestResponse":
        """
        单节点测试：直接调用注册的节点执行器，不走完整的 LangGraph，不创建实例和日志。
        """
        from app.modules.workflow.model.workflow import NodeTestResponse
        from app.modules.workflow.service.compiler import UNTESTABLE_NODE_TYPES, convert_keys_to_snake, apply_input_mappings, apply_output_mappings, node_registry, resolve_node_inputs
        from app.core.redis import redis_client

        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="工作流定义不存在")

        try:
            graph_json = json.loads(definition.graph_json)
        except Exception:
            raise HTTPException(status_code=400, detail="工作流拓扑解析失败")

        nodes = graph_json.get("nodes", [])
        node = next((n for n in nodes if n.get("id") == node_id), None)
        if not node:
            raise HTTPException(status_code=404, detail=f"节点 '{node_id}' 不存在")

        node_type = node.get("type")
        # 拦截不可单独测试的节点类型
        if node_type in UNTESTABLE_NODE_TYPES:
            raise HTTPException(status_code=400, detail=f"节点类型 '{node_type}' 不支持单节点测试")

        config = convert_keys_to_snake(node.get("config", {}))
        executor = node_registry.get(node_type)
        if not executor:
            raise HTTPException(status_code=400, detail=f"工作流中使用了未注册的节点类型: '{node_type}'")

        # 防重放：同一节点 2 秒内不重复执行 (使用 Redis)
        dedup_key = f"loom:workflow:test_node:{definition_id}:{node_id}"
        if not redis_client.set(dedup_key, "1", nx=True, ex=2):
            raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

        # 1. 提炼入参
        node_inputs = resolve_node_inputs(mock_variables, config)

        start_time = time.perf_counter()
        error_msg = None
        is_timeout = False
        updates = {}
        try:
            executor_config = {**config, "id": node_id}
            # 执行节点（可配置超时，默认 180 秒；LLM 节点常需 60-180 秒响应）
            from app.core.config import settings
            timeout_seconds = settings.WORKFLOW_NODE_TEST_TIMEOUT
            updates = await asyncio.wait_for(
                executor(node_inputs, executor_config),
                timeout=timeout_seconds
            )
            if updates is None:
                updates = {}
        except asyncio.TimeoutError:
            logger.warning("单节点测试超时 [%s] (%ds)", node_id, timeout_seconds)
            error_msg = f"节点执行超时（{timeout_seconds}秒），可能是模型响应过慢或配置有误"
            is_timeout = True
        except Exception as e:
            logger.error("单节点测试执行失败 [%s]: %s", node_id, e, exc_info=True)
            error_msg = str(e)
            is_timeout = False

        latency_ms = int((time.perf_counter() - start_time) * 1000)

        # 单节点测试主要关心节点本身的输出 updates，不关心写回全局后的完整 variables 状态
        return NodeTestResponse(
            output=updates,
            latency_ms=latency_ms,
            error=error_msg,
            is_timeout=is_timeout
        )


def recover_orphaned_instances(session: Session):
    """
    启动时将长时间卡在 running/pending 状态的实例标记为 failed。
    5 分钟宽限期避免误杀刚启动的正常实例。paused 状态不处理。
    """
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    stmt = select(WorkflowInstance).where(
        WorkflowInstance.status.in_(["running", "pending"]),
        WorkflowInstance.updated_at < cutoff,
    )
    orphaned = list(session.exec(stmt).all())
    if not orphaned:
        return
    for instance in orphaned:
        instance.status = "failed"
        instance.error_message = "Server restarted during workflow execution"
        session.add(instance)
    session.commit()
    logger.warning("已将 %d 个孤儿工作流实例标记为 failed", len(orphaned))
