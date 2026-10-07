"""工作流节点执行器群与 AI 运行时封装。

自 workflow_service.py 拆出：run_ai_chat/run_ai_image 运行时封装、
13 个 execute_*_node 执行器、mock 工具、生图转存，以及模块级
node_registry 注册副作用（import 本模块即完成注册——compiler 的
compile_graph 与 workflow_tasks 依赖此入口）。

注意：执行器经本模块全局查找 run_ai_chat/run_ai_image，
测试 patch 目标应指向本模块（原 workflow_service 锚点已迁移）。

执行器上下文契约（三期B4 / WF-P1-1）：
- 绑定输入/模板渲染/表达式求值 = 第一形参 variables（node_inputs，声明优先——
  由 resolve_node_inputs 按 inputs schema / input_mappings 提炼）；
- 跨节点全局读取 = config["_global_vars"]（node_runner 运行时注入的只读快照，
  经 _globals_from 取用，缺省降级 node_inputs 以兼容直调执行器的既有测试路径）。
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
    strip_var_prefix,
)
from app.modules.workflow.service.error_format import friendly_error_message
from app.modules.workflow.service.graph_validate import MOCK_TOOL_CODES
from app.modules.workflow.service.llm_io import (
    _build_llm_response_format,
    _parse_llm_output,
)

logger = logging.getLogger(__name__)


def _globals_from(config: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """跨节点全局读取的统一入口（三期B4 / WF-P1-1）。

    config["_global_vars"] 由 node_runner / run_node_standalone 运行时注入
    （state["variables"] 只读快照）；缺省（直调执行器的测试路径、旧调用方）时
    降级 node_inputs——未配置 inputs 的节点其 node_inputs 即全量变量，行为不变。
    """
    return config.get("_global_vars") or variables


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


# 注册至全局注册表（idempotent=False：重试 = 整体重跑或重复计费的非幂等节点）
# deprecated `tool` 节点已下架（三期B7 / WF-P2-10）：存量图在加载入口自动迁移为
# tool_executor（graph_validate.migrate_legacy_tool_nodes），不再注册执行器。
node_registry.register("llm", execute_llm_node)
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
    意图识别与语义分流节点执行逻辑。

    待分类文本属跨节点全局读取：input_variable / query / user_query 均从
    _global_vars 取（支持点路径）；LLM 调用失败时降级为「其他」走 default_route
    （业务性路由降级，非静默语义错误——见 X-1 审计口径）。
    """
    node_id = config.get("id", "intent_classifier")
    globals_ = _globals_from(config, variables)
    input_var = config.get("input_variable", "")
    if input_var:
        var_name = strip_var_prefix(input_var.strip())
        val = _deep_get(globals_, var_name)
        query = str(val) if val is not None else ""
    else:
        query = globals_.get("query") or globals_.get("user_query") or ""
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

    # 复审 P1-4：删去「模型输出 == 其他 → 强制 default」判定——未命中任何具名意图时
    # selected_route 本就保持 default_route 初值（含模型输出「其他」的情况），该判定
    # 反而会把用户显式配置的「其他」意图（exact/norm 命中、target_route 已解析）覆盖
    # 回 default_route。保留仅兜底「命中的意图未配置路由」场景。
    if not selected_route:
        selected_route = default_route

    return {f"{node_id}_selected_route": selected_route}


async def execute_loop_controller_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    循环控制器节点执行逻辑（状态链式循环：上一次迭代的输出作为下一次的输入）。
    只在循环开始前做一次 deepcopy，后续迭代链式传递状态，支持跨迭代状态累积。

    - collect_keys（list[str]，前端 collectKeys）：配置后每轮迭代只收集白名单键进
      results（须与运行时变量名完全一致，不做大小写/命名归一）；未配置保持兼容行为
      （收集除循环临时变量外的全量快照）。
    - persist_globals（前端 persistGlobals，默认 False）：True 时把迭代期**新增**的
      变量（键差集，排除循环临时变量）以原名并入返回值，进而合入全局状态；对既有
      变量的改写不回写（防意外覆盖主图状态）。diff 键不受 output_mappings 路由，
      恒以原变量名合并——若需重命名落点，应在循环体内用 variable_assignment 产出
      目标名变量。
    - 子图超时（WF-P1-5）：整个迭代过程受 timeout_seconds（前端 timeoutSeconds）或
      WORKFLOW_SUBGRAPH_TIMEOUT 约束。⚠️ 超时抛 ValueError 会经节点级重试链路
      （默认 max_attempts=1 无碍）；调大重试次数会导致整个循环从头重跑，务必配合
      retry_max_attempts=1 使用。
    """
    from app.core.config import settings

    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError(
            "循环控制器节点缺少已编译的体子图。请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。"
        )
    list_var = strip_var_prefix(config.get("list_variable") or config.get("array_variable", "list_variable"))
    item_var = config.get("item_variable", "loop_item")
    globals_ = _globals_from(config, variables)
    output_var = config.get("output_variable", "loop_results")
    stop_on_error = config.get("stop_on_error", True)
    subgraph_timeout = float(config.get("timeout_seconds") or settings.WORKFLOW_SUBGRAPH_TIMEOUT)
    collect_keys_raw = config.get("collect_keys")
    collect_keys = (
        [str(k).strip() for k in collect_keys_raw if str(k).strip()] if isinstance(collect_keys_raw, list) else []
    )
    persist_globals = bool(config.get("persist_globals", False))

    # 走 _deep_get：list_variable 可能被填成跨节点深层路径（如 llm_output.user_list），
    # 直接用 get() 会因键不存在而静默返回空列表，导致循环/批处理空转；
    # 三期B4：读取源改为 _global_vars（配 inputs 窄化 node_inputs 后仍能读到全局列表）
    items = _deep_get(globals_, list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}
    if len(items) > 200:
        raise ValueError(f"循环项数量({len(items)})超过系统硬上限(200)，请缩小批次或调整上游数据。")

    # 只做一次初始拷贝，后续迭代链式传递状态
    iter_vars = copy.deepcopy(variables)
    initial_keys = set(iter_vars.keys())  # persist_globals 键差集基准
    results: list[dict[str, Any]] = []
    index_key = f"{item_var}_index"

    async def _iterate() -> None:
        nonlocal iter_vars
        for idx, item in enumerate(items):
            iter_vars[item_var] = item
            iter_vars[index_key] = idx
            body_state = {"variables": iter_vars, "current_node": "start"}
            try:
                body_result = await compiled_body.ainvoke(body_state)
                iter_vars = body_result.get("variables", {})
                if collect_keys:
                    iter_output = {k: iter_vars[k] for k in collect_keys if k in iter_vars}
                else:
                    # 兼容默认：收集除临时注入循环变量外的全量快照
                    iter_output = {k: v for k, v in iter_vars.items() if k != item_var and k != index_key}
                results.append(iter_output)
                logger.info("[Loop] Iteration %d/%d complete: item=%s", idx + 1, len(items), str(item)[:80])
            except Exception as e:
                logger.error("[Loop] Iteration %d/%d failed: %s", idx + 1, len(items), e)
                results.append({"error": str(e), "item_index": idx})
                if stop_on_error:
                    break

    try:
        await asyncio.wait_for(_iterate(), timeout=subgraph_timeout)
    except TimeoutError:
        raise ValueError(
            f"循环体执行超时（{int(subgraph_timeout)}秒，共 {len(items)} 项）。"
            "可在节点配置 timeoutSeconds 收紧；注意调大节点重试次数会导致整个循环从头重跑。"
        ) from None

    result = {output_var: results}
    if persist_globals:
        diff = {k: v for k, v in iter_vars.items() if k not in initial_keys and k != item_var and k != index_key}
        result.update(diff)
    return result


async def execute_batch_processor_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    批处理并发节点执行逻辑（子图模式：并发遍历列表，每项独立调用体子图）。
    使用 asyncio.gather + Semaphore 控制并发，return_exceptions=True 容错。

    - collect_keys（list[str]，前端 collectKeys）：配置后每项结果只收集白名单键
      （须与运行时变量名完全一致）；未配置保持兼容行为（返回全量变量快照）。
    - persist_globals：**不支持并忽略**（warning）——并发迭代无全序，回写全局的
      语义不明确；需要跨项累积全局状态请改用循环控制器。
    - 子图超时（WF-P1-5）：整个 gather 过程受 timeout_seconds（前端 timeoutSeconds）
      或 WORKFLOW_SUBGRAPH_TIMEOUT 约束。⚠️ 超时抛 ValueError 会经节点级重试链路
      （默认 max_attempts=1 无碍）；调大重试次数会导致整个批处理从头重跑，务必配合
      retry_max_attempts=1 使用。wait_for 取消并发协程时，已在 to_thread 中运行的
      调用无法中断（线程自然耗尽），与外层 superstep 兜底行为一致。
    """
    from app.core.config import settings

    compiled_body = config.get("_compiled_body")
    if not compiled_body:
        raise ValueError("批处理节点缺少已编译的体子图。请重新保存工作流以触发编译，或检查循环体入口节点配置是否正确。")
    list_var = strip_var_prefix(config.get("list_variable") or config.get("array_variable", "batch_list_variable"))
    item_var = config.get("item_variable", "batch_item")
    globals_ = _globals_from(config, variables)
    output_var = config.get("output_variable", "batch_results")
    concurrency_limit = min(max(int(config.get("concurrency_limit", 5) or 5), 1), 20)
    subgraph_timeout = float(config.get("timeout_seconds") or settings.WORKFLOW_SUBGRAPH_TIMEOUT)
    collect_keys_raw = config.get("collect_keys")
    collect_keys = (
        [str(k).strip() for k in collect_keys_raw if str(k).strip()] if isinstance(collect_keys_raw, list) else []
    )
    if config.get("persist_globals"):
        logger.warning(
            "批处理节点 '%s' 配置了 persist_globals，因并发迭代无全序、回写全局语义不明确，已忽略；"
            "需要跨项累积全局状态请改用循环控制器。",
            config.get("id", "batch_processor"),
        )

    # 走 _deep_get：list_variable 可能被填成跨节点深层路径（如 llm_output.user_list），
    # 直接用 get() 会因键不存在而静默返回空列表，导致循环/批处理空转；
    # 三期B4：读取源改为 _global_vars（配 inputs 窄化 node_inputs 后仍能读到全局列表）
    items = _deep_get(globals_, list_var) or []
    if not isinstance(items, list) or not items:
        return {output_var: []}
    if len(items) > 200:
        raise ValueError(f"批处理项数量({len(items)})超过系统硬上限(200)，请缩小批次或调整上游数据。")

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_body(item: Any) -> dict[str, Any]:
        async with semaphore:
            iter_vars = copy.deepcopy(variables)
            iter_vars[item_var] = item
            body_state = {"variables": iter_vars, "current_node": "start"}
            body_result = await compiled_body.ainvoke(body_state)
            vs = body_result.get("variables", {})
            if collect_keys:
                return {k: vs[k] for k in collect_keys if k in vs}
            return vs

    try:
        raw_results = await asyncio.wait_for(
            asyncio.gather(*[run_body(item) for item in items], return_exceptions=True),
            timeout=subgraph_timeout,
        )
    except TimeoutError:
        raise ValueError(
            f"批处理体执行超时（{int(subgraph_timeout)}秒，共 {len(items)} 项，并发={concurrency_limit}）。"
            "可在节点配置 timeoutSeconds 收紧；注意调大节点重试次数会导致整个批处理从头重跑。"
        ) from None

    results = []
    for idx, r in enumerate(raw_results):
        if isinstance(r, Exception):
            logger.error("[Batch] Iteration %d failed: %s", idx, r)
            results.append({"error": str(r), "item_index": idx})
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

    参数来源（三期B4 迁移）：arguments 整体与参数值的 variables. 引用均从
    _global_vars 读取（支持点路径）；config 声明（arguments/arguments_json）优先。
    注意：web_search / file_system / mock_weather_api 当前为 [Mock] 占位实现，
    返回演示数据；生产部署请替换为真实工具接入（见 tool_web_search 等）。
    """
    from app.core.config import settings

    tool_code = config.get("tool_code", "unknown")
    # WF-P0-2：mock 占位工具在生产环境（非 DEBUG）直接失败，杜绝演示数据
    # 以 success 流入下游与产物；DEBUG 保留演示行为。异常不再吞成字符串返回
    # （原 :593-594 的 except 会把工具执行异常伪装成成功输出），交由重试/失败链路。
    if tool_code in MOCK_TOOL_CODES and not settings.DEBUG:
        raise ValueError(f"工具 '{tool_code}' 为演示占位实现，生产环境不可用；如需演示请在 DEBUG 模式运行")
    globals_ = _globals_from(config, variables)
    # 复审 P1-5：config 声明（arguments/arguments_json）优先——原 `globals_.get("arguments")`
    # 优先于节点配置，与 docstring 相反，且全局同名键会覆盖用户在面板配置的参数
    # （B4 迁移残留的 mock fallback 遗迹）。参数值的 variables. 引用解析仍走 globals_。
    arguments = config.get("arguments") or {}
    if not arguments:
        arguments_json_str = config.get("arguments_json", "")
        if arguments_json_str:
            try:
                arguments = json.loads(arguments_json_str)
            except json.JSONDecodeError as e:
                # X-1（三期B6）：参数 JSON 解析失败曾静默落 {}（工具以空参数执行、
                # 节点假成功）——改为显式失败，交由节点失败链路定位
                raise ValueError(f"工具 '{tool_code}' 的参数 JSON（argumentsJson）解析失败，请检查配置: {e}") from e
    output_variable = config.get("output_variable", "tool_result")

    # 参数级联转换：variables. 引用走 _deep_get（原浅层 get 不支持点路径）
    resolved_args = {}
    for arg_name, arg_val in arguments.items():
        if isinstance(arg_val, str) and arg_val.startswith("variables."):
            var_key = arg_val.removeprefix("variables.")
            resolved_args[arg_name] = _deep_get(globals_, var_key)
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
            # 未登记的 tool_code：显式失败而非返回可疑文案（调用方按节点失败处理）
            raise ValueError(f"[工具中心] 找不到系统工具 Code: '{tool_code}'")
    except Exception as e:
        # WF-P0-2：执行异常原样冒泡（原实现吞成字符串返回，节点假 success），
        # 交由节点级重试/失败链路处理
        logger.error("工具执行器 '%s' 执行失败: %s", tool_code, e)
        raise

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

    表达式求值上下文（三期B4）：全局变量打底（_global_vars，未注入时降级
    node_inputs）、inputs 声明覆盖、本轮已算出的 updates 最优先（允许前后变量依赖）。
    """
    globals_ = _globals_from(config, variables)
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
                # X-1 口径（复审 P1-3）：静默赋 0 是危险值（下游计算拿 0 继续，
                # 失败被推迟且难归因）——与同节点 expression 失败同语义，显式失败
                raise ValueError(f"变量赋值 '{var_name}' 的 number 值 '{val}' 无法解析为数字，请检查赋值配置") from None
        elif val_type == "boolean":
            updates[var_name] = str(val).lower() in ("true", "1", "yes")
        elif val_type == "expression":
            try:
                # 全局打底 + 声明覆盖 + updates 最优先（允许前后变量依赖）
                ctx = {**globals_, **variables, **updates}
                updates[var_name] = safe_eval(str(val), ctx)
            except Exception as e:
                # X-1 / D3 同款语义（三期B6）：表达式失败曾静默赋 None 流入下游，
                # 默认以节点失败收尾；节点 config onExpressionError="fallback"
                # 显式选择保留旧行为（赋 None 继续）
                if str(config.get("on_expression_error", "fail")).lower() != "fallback":
                    logger.error("变量赋值表达式 '%s' 执行失败（fail-fast）: %s", val, e)
                    raise
                logger.warning(f"变量赋值表达式 '{val}' 执行失败，已按 fallback 赋 None: {e}")
                updates[var_name] = None
        else:
            updates[var_name] = val

    return updates


async def execute_variable_transform_node(variables: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    """
    变量转换/聚合节点执行逻辑。

    input_variable 属跨节点全局读取（三期B4）：从 _global_vars 取并支持点路径；
    eval_expression 上下文与 variable_assignment 同口径（全局打底、声明覆盖）。
    """
    globals_ = _globals_from(config, variables)
    input_var = strip_var_prefix(config.get("input_variable", ""))
    transform_type = config.get("transform_type", "join_array")
    transform_args = config.get("transform_args", {})
    output_var = config.get("output_variable", "transformed_value")

    input_val = _deep_get(globals_, input_var)
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
            ctx = {**globals_, **variables, "input_value": input_val}
            result = safe_eval(expression, ctx)

        else:
            result = input_val

    except Exception as e:
        # X-1（三期B6）：转换整体异常曾静默落 result=None 流入下游（下游拿 None
        # 继续运算，失败被推迟且难以归因）——改为以节点失败收尾
        logger.error("变量转换节点执行失败: %s", e)
        raise

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
# 非幂等声明（三期B6 / WF-P2-3）：loop/batch 超时经重试 = 整个子图从头重跑
# （docstring 自警）；image_generator 重试 = 重复调用生图 API 重复计费。
node_registry.register("intent_classifier", execute_intent_classifier_node)
node_registry.register("loop_controller", execute_loop_controller_node, idempotent=False)
node_registry.register("batch_processor", execute_batch_processor_node, idempotent=False)
node_registry.register("image_generator", execute_image_generator_node, idempotent=False)
node_registry.register("tool_executor", execute_tool_executor_node)
node_registry.register("end", execute_end_node)
node_registry.register("condition", execute_condition_node)
node_registry.register("switch", execute_switch_node)
node_registry.register("variable_assignment", execute_variable_assignment_node)
node_registry.register("variable_transform", execute_variable_transform_node)
