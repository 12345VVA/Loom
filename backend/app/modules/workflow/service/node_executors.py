"""工作流节点执行器群与 AI 运行时封装。

自 workflow_service.py 拆出：run_ai_chat/run_ai_image 运行时封装、
13 个 execute_*_node 执行器、mock 工具、生图转存，以及模块级
node_registry 注册副作用（import 本模块即完成注册——compiler 的
compile_graph 与 workflow_tasks 依赖此入口）。

注意：执行器经本模块全局查找 run_ai_chat/run_ai_image，
测试 patch 目标应指向本模块（原 workflow_service 锚点已迁移）。
"""

import asyncio
import copy
import json
import logging
import re
from typing import Any

from sqlmodel import select

from app.modules.ai.model.ai import AiChatRequest, AiRuntimeMessage
from app.modules.ai.service.runtime_service import AiModelRuntimeService
from app.modules.workflow.model.workflow import WorkflowInstance
from app.modules.workflow.service.compiler import (
    _deep_get,
    node_registry,
    render_template,
    safe_eval,
    strip_braces,
)
from app.modules.workflow.service.error_format import friendly_error_message
from app.modules.workflow.service.llm_io import (
    _build_llm_response_format,
    _parse_llm_output,
)

logger = logging.getLogger(__name__)


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


def _normalize_intent_label(text: str) -> str:
    """归一化意图标签：剔除空白、markdown 强调符与中英文标点。

    大模型常输出「咨询。」「**咨询**」这类带装饰的答案，精确 == 比较会全部落到默认分支。
    注意：只做归一化后的等值比较，**不做子串包含匹配** —— 那会让「咨询」误命中
    「咨询退款」；路由误判（走错分支）的代价高于漏判（漏判有 default_route 兜底）。
    """
    cleaned = re.sub(r"[*_`\s]", "", text or "")
    return cleaned.strip("。．.,，、；;：:！!？?\"'“”‘’()（）[]【】")


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
    #    3.1 先做原样精确匹配：优先命中配置里的权威意图名，避免归一化把不同标签
    #        （如 VIP_用户 / VIP用户）折叠成同一 key 后误路由。
    #    3.2 无精确命中再归一化匹配（容忍模型输出的标点/markdown 强调符）；若归一化后
    #        出现多个候选，说明标签存在歧义，不静默取首个，记 warning 并保持 default_route 兜底。
    selected_route = default_route
    exact_hits = [i for i in intents if str(i.get("name") or "") == matched_intent_name]
    if exact_hits:
        selected_route = exact_hits[0].get("target_route")
    else:
        matched_label = _normalize_intent_label(matched_intent_name)
        norm_hits = [
            i for i in intents if matched_label and _normalize_intent_label(str(i.get("name") or "")) == matched_label
        ]
        if len(norm_hits) > 1:
            logger.warning(
                "意图标签归一化后存在多个候选，路由存在歧义，回落 default_route：matched=%r candidates=%s",
                matched_intent_name,
                [str(i.get("name")) for i in norm_hits],
            )
        elif norm_hits:
            selected_route = norm_hits[0].get("target_route")

    if _normalize_intent_label(matched_intent_name) == "其他" or not selected_route:
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

    # 走 _deep_get：list_variable 可能被填成跨节点深层路径（如 llm_output.user_list），
    # 直接用 variables.get() 会因键不存在而静默返回空列表，导致循环/批处理空转
    items = _deep_get(variables, list_var) or []
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

    # 走 _deep_get：list_variable 可能被填成跨节点深层路径（如 llm_output.user_list），
    # 直接用 variables.get() 会因键不存在而静默返回空列表，导致循环/批处理空转
    items = _deep_get(variables, list_var) or []
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
        # 带上原始异常摘要（此前整体抹为固定文案，厂商限流/鉴权/参数错误无法区分）
        raise ValueError(f"工作流生图失败: {friendly_error_message(e)}") from e

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
            config.get("id"),
        )
        logger.info(f"工作流生图转存成功: temp={temp_url[:80]}... → permanent={permanent_url}")
    except Exception as e:
        # 回退临时 URL（约 24h 过期）：转存失败明细已在 media 资产 failed 行（归属齐全可重试），
        # temp_url 前缀入日志便于追踪腐化链接
        logger.warning(
            f"工作流生图转存失败，使用临时 URL: {e}",
            extra={"temp_url_prefix": temp_url[:80], "node_id": config.get("id")},
        )

    # 同时输出上游临时 URL（厂商公网地址，约 24h 有效）：转存后的 /uploads 本地地址
    # 在本地部署时厂商服务器无法回源拉取，不能作为图生图参考图；__src 后缀变量专供
    # 下游生图节点 imageVariable 引用（如绘本内页以封面为参考图锁风格与角色一致性）。
    return {output_variable: permanent_url, f"{output_variable}__src": temp_url}


def _persist_image_to_media(
    result: dict[str, Any],
    request_payload: dict[str, Any],
    profile_code: str | None = None,
    node_id: str | None = None,
) -> str:
    """将 AI 生图结果转存到媒体资源库，返回永久存储 URL。转存失败时抛异常由调用方兜底。

    归属：instance 框架信息（instance_id/definition_id/user_id）从 workflow_instance_id_ctx
    读取（asyncio.to_thread 复制上下文，同 runtime_service._log_call 打标机制）；node_id 由
    executor_config 显式传入。单节点测试路径不设置 ctx，转存资产归属为空（仅超管可见）。
    """
    from app.core.database import SessionLocal
    from app.core.logging import workflow_instance_id_ctx
    from app.modules.media.service.media_service import MediaAssetService

    instance_id = workflow_instance_id_ctx.get()
    instance = None
    if instance_id is not None:
        with SessionLocal() as inst_session:
            instance = inst_session.get(WorkflowInstance, instance_id)
        if instance is None:
            # 实例已被删除：ctx 引用失效，归属整体置空，不落孤儿 id
            instance_id = None

    with SessionLocal() as session:
        media_service = MediaAssetService(session)
        assets = media_service.create_from_ai_result(
            task_type="image",
            result=result,
            request_payload=request_payload,
            source_type="workflow",
            profile_code=profile_code,
            created_by=instance.user_id if instance else None,
            workflow_instance_id=instance_id,
            workflow_definition_id=instance.definition_id if instance else None,
            workflow_node_id=node_id,
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
