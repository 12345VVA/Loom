"""
工作流核心管理与运行时服务。
"""

import asyncio
import copy
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import Session, select

from app.modules.ai.model.ai import AiChatRequest, AiRuntimeMessage
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.base.model.auth import User
from app.modules.base.service.admin_service import BaseAdminCrudService
from app.modules.base.service.authority_service import is_super_admin
from app.modules.workflow.model.workflow import (
    WorkflowDefinition,
    WorkflowInstance,
)
from app.modules.workflow.service.compiler import (
    node_registry,
    render_template,
    safe_eval,
    strip_braces,
)

if TYPE_CHECKING:
    from app.modules.workflow.model.workflow import NodeTestResponse

logger = logging.getLogger(__name__)


# Checkpoint 持久化存储由工厂函数按配置动态选择后端

# 跨进程事件总线（Redis pub/sub + 进程内 fallback）


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
            logger.error("大模型调用失败: %s", result.get("errorMessage") or result.get("message") or "未返回详情")
            raise ValueError("大模型服务调用异常，请稍后重试。")

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

        image_request = AiImageRequest(profile_code=profile_code, prompt=prompt, image=image or None, options=options)
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
        for child in f.get("children") or []:
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
        for child in f.get("children") or []:
            child_name = child.get("name", "").strip()
            if not child_name:
                continue
            properties[child_name] = _field_to_schema(child)
            required.append(child_name)
        schema["items"] = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
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
            parts.append(
                f'{indent_space}"{name}": [\n{indent_next}{{\n{children_str}\n{indent_next}}}\n{indent_space}]'
            )
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
                    parts.append(
                        f'{indent_space}"{name}": [\n{indent_next}{{\n{item_str}\n{indent_next}}}\n{indent_space}]'
                    )
                else:
                    item_desc = item_field.get("description", "")
                    item_desc_str = f" ({item_desc})" if item_desc else ""
                    parts.append(f'{indent_space}"{name}": [{item_type}{item_desc_str}]')
            else:
                parts.append(f'{indent_space}"{name}": []')
        else:
            parts.append(f'{indent_space}"{name}": {field_type}{desc_str}')

    return ",\n".join(parts)


def _build_llm_response_format(output_format: str, json_fields: list) -> tuple[dict[str, Any] | None, str]:
    """根据输出模式构建 response_format 与追加到 prompt 的格式化指令。

    Tier 1: json_schema（有 jsonFields 时自动生成 Schema）；Tier 2: json_object（宽松模式）。
    返回 (response_format, format_instructions)。
    """
    response_format: dict[str, Any] | None = None
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
                f"\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。\n"
                f"JSON 结构如下：\n{{\n{field_desc}\n}}"
            )
        else:
            format_instructions = "\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。"
    elif output_format == "json_object":
        # Tier 2: json_object — 用户显式选择宽松模式
        response_format = {"type": "json_object"}
        format_instructions = "\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。"

    return response_format, format_instructions


def _parse_llm_output(content: str, output_format: str, output_variable: str) -> dict[str, Any]:
    """解析 LLM 输出：JSON 模式去 markdown 后 json.loads，失败保留原始文本。"""
    if output_format in ("json", "json_object"):
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```\w*\n?", "", stripped)
            stripped = re.sub(r"\n?```\s*$", "", stripped)
        try:
            return {output_variable: json.loads(stripped)}
        except json.JSONDecodeError:
            logger.warning("LLM JSON 输出解析失败，保留原始文本")
    return {output_variable: content}


async def execute_llm_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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

    response_format, format_instructions = _build_llm_response_format(output_format, json_fields)
    # 格式化指令优先追加到 System Prompt，否则追加到 User Prompt
    if format_instructions:
        if system_prompt_template.strip():
            system_prompt_template += format_instructions
        else:
            user_prompt_template += format_instructions

    # 渲染 Prompt 变量（输入安全检查由 run_ai_chat → runtime_service.chat 统一处理）
    system_prompt = render_template(system_prompt_template, variables) if system_prompt_template else None
    user_prompt = render_template(user_prompt_template, variables)

    # 调用统一的 AI 对话驱动
    content = await asyncio.to_thread(run_ai_chat, profile_code, user_prompt, system_prompt, response_format)

    return _parse_llm_output(content, output_format, output_variable)


async def execute_tool_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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


async def execute_human_input_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    人工输入/审批节点。
    利用 LangGraph 的内置 interrupt 特性挂起运行。
    """

    message = config.get("message", "需要人工审批")
    output_variable = config.get("output_variable", "approval_result")

    # 抛出 GraphInterrupt，使工作流在当前步骤被挂起
    # 当恢复运行时，可通过 Command 传递人类回执值，这会在 resume 状态下接收到
    from langgraph.types import interrupt

    # 在 LangGraph 中，当运行到此处且无 resume 信号时，会在此触发暂停
    user_response = interrupt({"message": message, "output_variable": output_variable})

    return {output_variable: user_response}


# 注册至全局注册表
node_registry.register("llm", execute_llm_node)
node_registry.register("tool", execute_tool_node)
node_registry.register("human_input", execute_human_input_node)


# --- 2. 高级节点执行函数定义与注册 ---


async def execute_intent_classifier_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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


async def execute_loop_controller_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    循环控制器节点执行逻辑（状态链式循环：上一次迭代的输出作为下一次的输入）。
    只在循环开始前做一次 deepcopy，后续迭代链式传递状态，支持跨迭代状态累积。
    """
    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError(
            "循环控制器节点缺少已编译的体子图。请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。"
        )
    list_var = strip_braces(config.get("list_variable") or config.get("array_variable", "list_variable"))
    item_var = config.get("item_variable", "loop_item")
    output_var = config.get("output_variable", "loop_results")
    stop_on_error = config.get("stop_on_error", True)

    items = variables.get(list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}
    if len(items) > 200:
        raise ValueError(f"循环项数量({len(items)})超过系统硬上限(200)，请缩小批次或调整上游数据。")

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
            iter_output = {k: v for k, v in iter_vars.items() if k != item_var and k != index_key}
            results.append(iter_output)
            logger.info("[Loop] Iteration %d/%d complete: item=%s", idx + 1, len(items), str(item)[:80])
        except Exception as e:
            logger.error("[Loop] Iteration %d/%d failed: %s", idx + 1, len(items), e)
            results.append({"error": str(e)})
            if stop_on_error:
                break

    return {output_var: results}


async def execute_batch_processor_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    批处理并发节点执行逻辑（子图模式：并发遍历列表，每项独立调用体子图）。
    使用 asyncio.gather + Semaphore 控制并发，return_exceptions=True 容错。
    """
    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError("批处理节点缺少已编译的体子图。请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。")
    list_var = strip_braces(config.get("list_variable") or config.get("array_variable", "batch_list_variable"))
    item_var = config.get("item_variable", "batch_item")
    output_var = config.get("output_variable", "batch_results")
    concurrency_limit = min(max(int(config.get("concurrency_limit", 5) or 5), 1), 20)

    items = variables.get(list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}
    if len(items) > 200:
        raise ValueError(f"批处理项数量({len(items)})超过系统硬上限(200)，请缩小批次或调整上游数据。")

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_body(item: Any) -> dict[str, Any]:
        async with semaphore:
            iter_vars = copy.deepcopy(variables)
            iter_vars[item_var] = item
            body_state = {"messages": [], "variables": iter_vars, "current_node": "start"}
            body_result = await compiled_body.ainvoke(body_state)
            return body_result.get("variables", {})

    raw_results = await asyncio.gather(*[run_body(item) for item in items], return_exceptions=True)

    results = []
    for r in raw_results:
        if isinstance(r, Exception):
            logger.error("[Batch] Single iteration failed: %s", r)
            results.append({"error": str(r)})
        else:
            results.append(r)

    logger.info("[Batch] All %d iterations complete (concurrency=%d)", len(items), concurrency_limit)
    return {output_var: results}


async def execute_image_generator_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    生图节点执行逻辑，已增强支持自适应尺寸、参考图、以及自定义 options。
    生成的图片自动转存到媒体资源库，返回永久存储 URL。
    """

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
        except Exception as e:
            logger.warning("生图节点 image_template 渲染失败，跳过参考图: %s", e)

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
        ai_result = await asyncio.to_thread(run_ai_image, profile_code, prompt, size, image_val, custom_options)
    except Exception as e:
        logger.error(f"工作流生图 API 呼叫失败: {e}")
        raise ValueError("工作流生图失败，模型服务异常或内部错误。")

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
                select(MA)
                .where(
                    MA.original_url == original_url,
                    MA.status == "success",
                    MA.delete_time == None,  # noqa: E711
                )
                .order_by(MA.created_at.desc())
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
    return json.dumps(
        {
            "location": location,
            "temperature": "26°C",
            "condition": "晴",
            "humidity": "45%",
            "wind": "微风",
        },
        ensure_ascii=False,
    )


async def execute_tool_executor_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    通用工具执行器节点逻辑。

    注意：web_search / file_system / mock_weather_api 当前为 [Mock] 占位实现，
    返回演示数据；生产部署请替换为真实工具接入（见 tool_web_search 等）。
    """
    from app.core.config import settings

    tool_code = config.get("tool_code", "unknown")
    # 生产环境保护：调用 mock 占位工具时告警，避免演示数据被误当真实结果
    if tool_code in ("web_search", "file_system", "mock_weather_api") and not settings.DEBUG:
        logger.warning("[Mock] 工具 '%s' 为占位实现，返回演示数据，生产环境请替换为真实工具", tool_code)
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


def _render_output_field_recursive(field: dict, variables: dict[str, Any]) -> Any:
    field_type = field.get("type", "string").strip()

    if field_type == "object":
        result = {}
        for child in field.get("children") or []:
            child_name = child.get("name", "")
            if not child_name:
                continue
            result[child_name] = _render_output_field_recursive(child, variables)
        return result

    elif field_type == "array":
        result = []
        for child in field.get("children") or []:
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


async def execute_variable_assignment_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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


async def execute_variable_transform_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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


async def execute_end_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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


async def execute_condition_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    二元条件分支节点执行逻辑。路由通过条件边处理，此执行体仅作为节点执行标记。
    """
    return {}


async def execute_switch_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
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

# 工作流实例终态：到达后不可再 start/resume/cancel
TERMINAL_STATUSES = frozenset({"success", "failed", "cancelled"})


def assert_workflow_owner(session: Session, entity: Any, current_user: User | None) -> None:
    """工作流数据所有者校验：超管放行；无用户上下文（内部调用）放行；否则必须为本人。

    用于修复审查报告 S1（IDOR）：防止用户越权读取/操作他人的工作流定义与实例。
    owner_id 为 None 时放行，兼容迁移前的旧数据。
    """
    if current_user is None:
        return
    if is_super_admin(session, current_user):
        return
    owner_id = getattr(entity, "user_id", None)
    if owner_id is not None and owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权操作他人的工作流")


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
        # 1. 编码：未提供则自动生成（WF+日期+序列）；显式提供则校验唯一
        code = data.get("code")
        if not code:
            data["code"] = self._generate_code()
        else:
            existing = self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.code == code)).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 注：graph_json 已移至版本表，拓扑校验改由 WorkflowVersionService.save_draft 承担
        return data

    def _generate_code(self) -> str:
        """生成唯一工作流编码：WF + YYYYMMDD + 3位当日序列（如 WF20260630001）。

        取当天同前缀已有编码的最大数字序列 +1；DB code 字段 unique 约束兜底并发冲突。
        """
        prefix = "WF" + datetime.now(timezone.utc).strftime("%Y%m%d")
        rows = self.session.exec(
            select(WorkflowDefinition.code).where(WorkflowDefinition.code.like(f"{prefix}%"))
        ).all()
        max_seq = 0
        for c in rows:
            suffix = c[len(prefix):]
            if suffix.isdigit():
                max_seq = max(max_seq, int(suffix))
        return f"{prefix}{max_seq + 1:03d}"

    def _before_update(self, data: dict, entity: Any) -> dict:
        """
        为了支持局部更新（如 cl-switch 仅传 id 和 is_active），
        这里过滤掉未传值（即为 None）的字段，并执行唯一性及拓扑 JSON 校验。
        """
        # 1. 唯一性校验
        code = data.get("code")
        if code and code != entity.code:
            existing = self.session.exec(select(WorkflowDefinition).where(WorkflowDefinition.code == code)).first()
            if existing:
                raise HTTPException(status_code=400, detail=f"工作流编码 '{code}' 已存在。")

        # 注：graph_json 已移至版本表，update 不再处理 graph；拓扑校验由 save_draft 承担
        # 注意：此处过滤 None 值（即未显式传递的 Optional 字段）是为了在 cl-switch 局部更新
        # （只传递了 id 和 status/is_active 等）场景下，避免将其余未传字段覆盖更新为 Null。
        # 其副作用是无法通过传递 None/Null 的更新请求将某个字段显式清空。
        # 在本模块（WorkflowDefinitionUpdateRequest 中 description/graph_json 等均为 Optional[str] = None）
        # 场景下目前安全，在此保留此注释以提请后续维护注意该局部更新语义。
        return {k: v for k, v in data.items() if v is not None}

    def add(self, payload: Any, current_user: User | None = None) -> Any:
        """新增工作流定义，自动写入创建者 user_id 以支持数据权限隔离（修复 IDOR）。"""
        if isinstance(payload, list):
            return [self.add(item, current_user) for item in payload]
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        if current_user is not None and "user_id" not in data:
            data["user_id"] = current_user.id
        return super().add(data)

    def update(self, payload: Any, current_user: User | None = None) -> Any:
        """更新前校验调用者是否为该工作流定义的所有者（修复 IDOR 越权改）。"""
        id_val = getattr(payload, "id", None)
        entity = self.session.get(self.model, id_val) if id_val is not None else None
        if entity is not None:
            assert_workflow_owner(self.session, entity, current_user)
        return super().update(payload)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前校验调用者是否为每个待删工作流定义的所有者（修复 IDOR 越权删）。"""
        for entity_id in ids or []:
            entity = self.session.get(self.model, entity_id)
            if entity is not None:
                assert_workflow_owner(self.session, entity, current_user)
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    def info(self, id, current_user=None, relations=()):
        """详情额外回填版本字段：currentVersionNo/currentPublishedAt/draftGraphJson。"""
        result = super().info(id, current_user, relations)
        if isinstance(result, dict):
            self._enrich_with_version_info(result)
        return result

    def list(self, query=None, current_user=None, relations=None, is_tree=None, parent_field=None):
        data = super().list(query, current_user, relations, is_tree, parent_field)
        self._enrich_list_with_version(data)
        return data

    def page(self, query, current_user=None, relations=()):
        result = super().page(query, current_user, relations)
        self._enrich_list_with_version(result.items)
        return result

    def _enrich_list_with_version(self, items: list) -> None:
        """列表批量回填 currentVersionNo/currentPublishedAt（一次 IN 查询）。"""
        if not items:
            return
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        vids = {it.get("currentVersionId") for it in items if isinstance(it, dict) and it.get("currentVersionId")}
        if not vids:
            return
        versions = {
            v.id: v
            for v in self.session.exec(
                select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.id.in_(vids))
            ).all()
        }
        for it in items:
            if not isinstance(it, dict):
                continue
            v = versions.get(it.get("currentVersionId"))
            if v:
                it["currentVersionNo"] = v.version_no
                it["currentPublishedAt"] = v.published_at

    def _enrich_with_version_info(self, data: dict) -> None:
        """info 单条回填 currentVersionNo/currentPublishedAt/draftGraphJson。"""
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        cur_vid = data.get("currentVersionId")
        if cur_vid is not None:
            v = self.session.get(WorkflowDefinitionVersion, cur_vid)
            if v:
                data["currentVersionNo"] = v.version_no
                data["currentPublishedAt"] = v.published_at
        draft_vid = data.get("draftVersionId")
        if draft_vid is not None:
            v = self.session.get(WorkflowDefinitionVersion, draft_vid)
            if v:
                data["draftGraphJson"] = v.graph_json


class WorkflowInstanceService(BaseAdminCrudService):
    """
    工作流实例管理服务
    """

    def __init__(self, session: Session):
        super().__init__(session, WorkflowInstance)

    def delete(
        self,
        ids: list[int],
        payload: Any = None,
        soft_delete: bool | None = None,
        current_user: User | None = None,
    ) -> dict:
        """删除前校验调用者是否为每个待删工作流实例的所有者（修复 IDOR 越权删实例）。

        BaseAdminCrudService.delete 按 ids 直接软删除，不走 DataScope，故在此显式逐条校验 owner。
        """
        for entity_id in ids or []:
            instance = self.session.get(self.model, entity_id)
            if instance is not None:
                assert_workflow_owner(self.session, instance, current_user)
        return super().delete(ids, payload=payload, soft_delete=soft_delete)

    def info(self, id, current_user=None, relations=()):
        result = super().info(id, current_user, relations)
        if isinstance(result, dict):
            self._enrich_version_no([result])
            self._enrich_token_cost([result])
        return result

    def list(self, query=None, current_user=None, relations=None, is_tree=None, parent_field=None):
        data = super().list(query, current_user, relations, is_tree, parent_field)
        self._enrich_version_no(data)
        self._enrich_token_cost(data)
        return data

    def page(self, query, current_user=None, relations=()):
        result = super().page(query, current_user, relations)
        self._enrich_version_no(result.items)
        self._enrich_token_cost(result.items)
        return result

    def _enrich_version_no(self, items: list) -> None:
        """回填 versionNo（join 版本表，一次 IN 查询）。"""
        if not items:
            return
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion

        vids = {it.get("versionId") for it in items if isinstance(it, dict) and it.get("versionId")}
        if not vids:
            return
        version_nos = {
            v.id: v.version_no
            for v in self.session.exec(
                select(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.id.in_(vids))
            ).all()
        }
        for it in items:
            if isinstance(it, dict):
                vno = version_nos.get(it.get("versionId"))
                if vno is not None:
                    it["versionNo"] = vno

    def _enrich_token_cost(self, items: list) -> None:
        """回填 totalTokens/costUsd（按 instance 聚合 AiModelCallLog，一次 group by 避免 N+1）。"""
        if not items:
            return
        from sqlalchemy import func

        from app.modules.ai.model.ai import AiModelCallLog

        instance_ids = [it.get("id") for it in items if isinstance(it, dict) and it.get("id")]
        if not instance_ids:
            return
        rows = self.session.exec(
            select(
                AiModelCallLog.workflow_instance_id,
                func.sum(AiModelCallLog.total_tokens),
                func.sum(func.coalesce(AiModelCallLog.cost_micro_usd, 0)),
            )
            .where(AiModelCallLog.workflow_instance_id.in_(instance_ids))
            .group_by(AiModelCallLog.workflow_instance_id)
        ).all()
        cost_map = {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in rows}
        for it in items:
            if not isinstance(it, dict):
                continue
            tokens, cost_micro = cost_map.get(it.get("id")) or (0, 0)
            it["totalTokens"] = tokens
            it["costUsd"] = cost_micro / 1_000_000.0

    def start_instance(
        self, definition_id: int, inputs: dict[str, Any], current_user: User | None = None
    ) -> WorkflowInstance:
        """
        创建一个工作流实例并启动异步执行（正式运行：跑已发布版 current_version_id）。
        """
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition or not definition.is_active:
            raise HTTPException(status_code=404, detail="工作流定义不存在或未启用")
        if definition.current_version_id is None:
            raise HTTPException(status_code=400, detail="该工作流尚未发布任何版本，无法启动实例")
        # 注：start_instance 不校验 definition owner —— 设计上任何用户均可启动已启用的工作流
        # 定义、实例归属启动者；definition 的可见性已由 DataScope 在 page/list/info 限制。
        return self._create_and_dispatch_instance(
            definition, definition.current_version_id, inputs, current_user, dedup=True
        )

    def start_trial_instance(
        self, definition_id: int, inputs: dict[str, Any], current_user: User | None = None
    ) -> WorkflowInstance:
        """
        试运行实例：跑草稿版（draft_version_id），无草稿回退已发布版。

        与正式 start_instance 分流 —— 编辑器试运行应反映最新保存的草稿，而非上次发布版
        （start_instance 固定走 current_version_id，保存草稿不会改变它，导致试运行跑旧版）。
        不要求已发布（发布前即可试运行）；关闭去重（试运行允许反复触发，前端已防双击）。
        """
        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition or not definition.is_active:
            raise HTTPException(status_code=404, detail="工作流定义不存在或未启用")
        draft_vid = definition.draft_version_id or definition.current_version_id
        if draft_vid is None:
            raise HTTPException(status_code=400, detail="该工作流尚无任何版本（草稿/发布），无法试运行")
        return self._create_and_dispatch_instance(
            definition, draft_vid, inputs, current_user, dedup=False
        )

    def _create_and_dispatch_instance(
        self,
        definition: WorkflowDefinition,
        version_id: int,
        inputs: dict[str, Any],
        current_user: User | None,
        *,
        dedup: bool = True,
    ) -> WorkflowInstance:
        """建实例（绑定指定 version_id）+ 可选防重放去重 + 派发 Celery 执行。

        start_instance（正式，dedup=True）与 start_trial_instance（试运行，dedup=False）共用。
        版本来源由调用方决定：正式走 current_version_id，试运行走草稿。
        """
        definition_id = definition.id

        # 防重放：优先用 Redis SETNX 抢占式去重锁（覆盖 Celery 多 worker / 高并发盲区，
        # 原 DB 2 秒窗口查询存在竞态）。Redis 不可用时（如本地开发）退回 DB 查询兜底。
        if dedup:
            import hashlib

            dedup_key = (
                f"loom:workflow:start:{definition_id}:"
                f"{hashlib.sha1(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}"
            )
            try:
                from app.core.redis import redis_client

                if not redis_client.set(dedup_key, "1", nx=True, ex=10):
                    raise HTTPException(status_code=400, detail="检测到重复的启动请求，请稍后再试。")
            except HTTPException:
                raise
            except Exception:
                # Redis 不可用：降级为 DB 2 秒窗口查询兜底，保持与原行为一致，不阻断正常启动
                logger.warning("工作流启动去重锁 Redis 不可用，降级为 DB 查询兜底", exc_info=True)
                two_seconds_ago = datetime.now(timezone.utc) - timedelta(seconds=2)
                stmt = select(WorkflowInstance).where(
                    WorkflowInstance.definition_id == definition_id,
                    WorkflowInstance.status == "running",
                    WorkflowInstance.created_at >= two_seconds_ago,
                )
                for inst in self.session.exec(stmt).all():
                    if inst.state_data == json.dumps(inputs):
                        raise HTTPException(status_code=400, detail="检测到重复的启动请求，请稍后再试。")

        # 初始化实例记录
        thread_id = str(uuid4())
        instance = WorkflowInstance(
            definition_id=definition.id,
            version_id=version_id,
            thread_id=thread_id,
            status="running",
            state_data=json.dumps(inputs),
            current_node=None,
            user_id=current_user.id if current_user else None,
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

    def resume_instance(
        self, instance_id: int, user_input: Any, current_user: User | None = None
    ) -> WorkflowInstance:
        """
        恢复暂停中的工作流实例并传入人类交互值
        """
        instance = self.session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="工作流实例不存在")
        assert_workflow_owner(self.session, instance, current_user)

        # S6 防御：user_input=None 时 json.dumps → "null" → 走 initial_state 从头重跑
        if user_input is None:
            raise HTTPException(status_code=400, detail="恢复值不能为空")
        if instance.status != "paused":
            raise HTTPException(status_code=400, detail="只有处于挂起暂停状态的工作流实例才可以恢复")

        definition = self.session.get(WorkflowDefinition, instance.definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="关联的工作流定义丢失")

        # S5：原子 CAS 把 paused → running，消除读-校验-写的 TOCTOU 竞态（避免并发 resume 重复扣费）
        from sqlalchemy import update

        result = self.session.execute(
            update(WorkflowInstance)
            .where(WorkflowInstance.id == instance_id, WorkflowInstance.status == "paused")
            .values(status="running")
        )
        if result.rowcount == 0:
            # 状态已被其他并发请求改走（恢复/取消/失败），拒绝本次
            self.session.rollback()
            raise HTTPException(status_code=409, detail="实例状态已变更，可能已被其他请求恢复，请刷新后重试")
        self.session.commit()
        self.session.refresh(instance)

        # 通过 Celery 异步任务恢复执行，Command(resume=user_input) 继续
        from app.modules.workflow.tasks.workflow_tasks import execute_workflow

        task = execute_workflow.delay(instance.id, definition.id, instance.state_data, json.dumps(user_input))
        instance.celery_task_id = task.id
        self.session.add(instance)
        self.session.commit()

        return instance

    def cancel_instance(self, instance_id: int, current_user: User | None = None) -> WorkflowInstance:
        """
        主动取消运行中或暂停中的工作流实例（修复审查报告 S4）。
        原子迁移到 cancelled + revoke Celery 任务（强制后背）+ 发布 cancelled 事件。
        """
        instance = self.session.get(WorkflowInstance, instance_id)
        if not instance:
            raise HTTPException(status_code=404, detail="工作流实例不存在")
        assert_workflow_owner(self.session, instance, current_user)

        if instance.status in TERMINAL_STATUSES:
            raise HTTPException(status_code=400, detail="已结束的实例无法取消")

        # 原子 CAS：仅 running/paused/pending 可取消，避免与 resume/执行循环的并发状态迁移冲突
        from sqlalchemy import update

        result = self.session.execute(
            update(WorkflowInstance)
            .where(
                WorkflowInstance.id == instance_id,
                WorkflowInstance.status.in_(["running", "paused", "pending"]),
            )
            .values(status="cancelled", error_message="用户主动取消")
        )
        if result.rowcount == 0:
            self.session.rollback()
            raise HTTPException(status_code=409, detail="实例状态已变更，无法取消")
        self.session.commit()
        self.session.refresh(instance)

        # 强制后背：revoke 正在执行的任务（执行主循环同时协作式轮询 status 做优雅退出）
        if instance.celery_task_id:
            from app.celery_app import celery_app

            try:
                celery_app.control.revoke(instance.celery_task_id, terminate=True)
            except Exception:
                logger.warning("revoke 工作流任务失败 instance=%d", instance_id, exc_info=True)

        from app.modules.workflow.service.event_bus import publish_event

        publish_event(instance_id, "cancelled", {"status": "cancelled"})
        return instance

    # ==========================================
    # 节点级运行（开发期调试 / 强一致性）
    # ==========================================

    async def _resolve_node_for_test(
        self,
        definition_id: int,
        node_id: str,
        current_user: User | None,
    ) -> tuple[dict[str, Any], Any]:
        """解析待测试节点：校验定义/版本/节点，返回 (config, executor)。失败抛 HTTPException。"""
        from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
        from app.modules.workflow.service.compiler import (
            UNTESTABLE_NODE_TYPES,
            convert_keys_to_snake,
            node_registry,
        )

        definition = self.session.get(WorkflowDefinition, definition_id)
        if not definition:
            raise HTTPException(status_code=404, detail="工作流定义不存在")
        assert_workflow_owner(self.session, definition, current_user)

        # 节点测试在 editor 编辑草稿过程中，测草稿版（无草稿回退 current）
        draft_vid = definition.draft_version_id or definition.current_version_id
        if draft_vid is None:
            raise HTTPException(status_code=400, detail="该工作流尚无任何版本，无法测试节点")
        version = self.session.get(WorkflowDefinitionVersion, draft_vid)
        if not version:
            raise HTTPException(status_code=404, detail="版本不存在")
        try:
            graph_json = json.loads(version.graph_json)
        except Exception:
            raise HTTPException(status_code=400, detail="工作流拓扑解析失败")

        node = next((n for n in graph_json.get("nodes", []) if n.get("id") == node_id), None)
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
        return config, executor

    async def test_node(
        self,
        definition_id: int,
        node_id: str,
        mock_variables: dict[str, Any],
        current_user: User | None = None,
    ) -> "NodeTestResponse":
        """
        单节点测试：直接调用注册的节点执行器，不走完整的 LangGraph，不创建实例和日志。
        """
        from app.core.config import settings
        from app.core.redis import redis_client
        from app.modules.workflow.model.workflow import NodeTestResponse
        from app.modules.workflow.service.compiler import resolve_node_inputs

        # 1. 解析节点（校验定义/版本/节点/类型，返回 config + executor）
        config, executor = await self._resolve_node_for_test(definition_id, node_id, current_user)

        # 2. 防重放：同一节点 2 秒内不重复执行 (使用 Redis)
        dedup_key = f"loom:workflow:test_node:{definition_id}:{node_id}"
        if not redis_client.set(dedup_key, "1", nx=True, ex=2):
            raise HTTPException(status_code=429, detail="操作过于频繁，请稍后再试")

        # 3. 执行节点（提炼入参 + 超时控制，默认 180 秒；LLM 节点常需 60-180 秒响应）
        node_inputs = resolve_node_inputs(mock_variables, config)
        executor_config = {**config, "id": node_id}
        timeout_seconds = settings.WORKFLOW_NODE_TEST_TIMEOUT

        start_time = time.perf_counter()
        error_msg = None
        is_timeout = False
        updates = {}
        try:
            updates = await asyncio.wait_for(executor(node_inputs, executor_config), timeout=timeout_seconds)
            if updates is None:
                updates = {}
        except TimeoutError:
            logger.warning("单节点测试超时 [%s] (%ds)", node_id, timeout_seconds)
            error_msg = f"节点执行超时（{timeout_seconds}秒），可能是模型响应过慢或配置有误"
            is_timeout = True
        except Exception as e:
            logger.error("单节点测试执行失败 [%s]: %s", node_id, e, exc_info=True)
            error_msg = str(e) if isinstance(e, ValueError) else "节点执行过程中发生内部错误，请联系管理员或查看日志。"
            is_timeout = False

        latency_ms = int((time.perf_counter() - start_time) * 1000)
        # 单节点测试主要关心节点本身的输出 updates，不关心写回全局后的完整 variables 状态
        return NodeTestResponse(output=updates, latency_ms=latency_ms, error=error_msg, is_timeout=is_timeout)


def recover_orphaned_instances(session: Session):
    """
    启动时将长时间卡在 running/pending 状态的实例标记为 failed。
    30 分钟宽限期避免误杀刚启动的正常实例。paused 状态不处理。
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
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
