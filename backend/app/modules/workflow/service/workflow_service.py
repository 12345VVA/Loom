"""
工作流核心管理与运行时服务。
"""
import asyncio
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
from app.modules.workflow.service.compiler import WorkflowCompiler, WorkflowState, node_registry, render_template

logger = logging.getLogger(__name__)

# 全局工作流事件订阅器，用于实时流式推送（规避循环导入）
workflow_event_listeners = []

# Checkpoint 持久化存储由工厂函数按配置动态选择后端
from app.modules.workflow.service.checkpointer import get_checkpointer
# 跨进程事件总线（Redis pub/sub + 进程内 fallback）
from app.modules.workflow.service.event_bus import publish_event


# --- 统一的 AI 运行时操作封装 (避免局部 SessionLocal 导入重复与异常静默吞没) ---

def run_ai_chat(profile_code: str, prompt: str) -> str:
    """
    统一驱动对话模型，做空响应拦截防御
    """
    from app.core.database import SessionLocal
    with SessionLocal() as session:
        runtime_service = AiModelRuntimeService(session)
        chat_request = AiChatRequest(
            profile_code=profile_code,
            messages=[AiRuntimeMessage(role="user", content=prompt)]
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
) -> str:
    """
    统一驱动图像模型，做空响应拦截防御，并支持自适应尺寸与参考图
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
        return image_url


# --- 1. 注册核心节点执行逻辑 ---

async def execute_llm_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    LLM 节点执行逻辑
    """
    profile_code = config.get("model_profile_code")
    prompt_template = config.get("prompt_template", "")
    output_variable = config.get("output_variable", "output")

    # 1. JSON 模式自动注入格式指令
    output_format = config.get("output_format", "text")
    if output_format == "json":
        json_fields = config.get("json_fields", [])
        if json_fields:
            field_desc = ", ".join(
                f'"{f["name"]}": ...' for f in json_fields if f.get("name")
            )
            prompt_template += (
                f'\n\n请以纯 JSON 格式输出，不要包含 markdown 代码块或任何额外文本。\n'
                f'JSON 结构如下：\n{{{field_desc}}}'
            )

    # 2. 解析 Prompt 变量渲染
    prompt = render_template(prompt_template, variables)

    # 3. 调用统一的 AI 对话驱动
    content = await asyncio.to_thread(run_ai_chat, profile_code, prompt)

    # 4. 输出格式处理：JSON 模式自动解析结构化输出
    if output_format == "json":
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
    循环控制器节点执行逻辑（实现列表/数组遍历）
    """
    node_id = config.get("id", "loop_controller")
    list_var_name = config.get("list_variable", "list_variable")
    array_list = variables.get(list_var_name) or []
    if not isinstance(array_list, list):
        array_list = []
        
    loop_index = variables.get("loop_index", 0)
    item_variable = config.get("item_variable", "loop_item")
    loop_body_route = config.get("loop_body_route")
    exit_route = config.get("exit_route")

    if loop_index < len(array_list):
        # 还有剩余子项：提取单项，递增索引，走向循环体内
        current_item = array_list[loop_index]
        return {
            item_variable: current_item,
            "loop_index": loop_index + 1,
            f"{node_id}_next_route": loop_body_route
        }
    else:
        # 已遍历完毕：重置索引，流向出口
        return {
            "loop_index": 0,
            f"{node_id}_next_route": exit_route
        }


async def execute_batch_processor_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    批处理并发节点执行逻辑
    """
    batch_list_var_name = config.get("batch_list_variable", "batch_list_variable")
    input_list = variables.get(batch_list_var_name) or []
    if not isinstance(input_list, list):
        input_list = []
        
    action_template = config.get("action_template", {})
    action_type = action_template.get("type", "llm")
    action_config = action_template.get("config", {})
    # 限制最大并发数在 1 至 20 之间，防御恶意或过大的并发量导致资源耗尽
    concurrency_limit = min(max(int(config.get("concurrency_limit", 5) or 5), 1), 20)
    output_variable = config.get("output_variable", "batch_results")

    if not input_list:
        return {output_variable: []}

    semaphore = asyncio.Semaphore(concurrency_limit)

    async def run_single_task(item: Any) -> Any:
        async with semaphore:
            if action_type == "llm":
                profile_code = action_config.get("model_profile_code")
                prompt_template = action_config.get("prompt_template", "")
                try:
                    if isinstance(item, dict):
                        prompt = render_template(prompt_template, item)
                    else:
                        prompt = render_template(prompt_template, {"topic": item, "item": item})
                except Exception:
                    prompt = prompt_template

                try:
                    return await asyncio.to_thread(run_ai_chat, profile_code, prompt)
                except Exception as e:
                    logger.error(f"批处理大模型调用失败: {e}")
                    return f"Error: {e}"
            
            await asyncio.sleep(0.1)
            return f"Processed: {item}"

    tasks = [run_single_task(item) for item in input_list]
    results = await asyncio.gather(*tasks)

    return {output_variable: results}


async def execute_image_generator_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    生图节点执行逻辑，已增强支持自适应尺寸、参考图、以及自定义 options。
    """
    profile_code = config.get("model_profile_code")
    prompt_template = config.get("prompt_template", "")
    size = config.get("size") or None  # 不强加默认的 "1024x1024"，以向下继承模型默认设置
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

    # 3. 提取其他自定义参数配置
    custom_options = config.get("options") or {}

    try:
        image_url = await asyncio.to_thread(
            run_ai_image, 
            profile_code, 
            prompt, 
            size, 
            image_val, 
            custom_options
        )
    except Exception as e:
        logger.error(f"工作流生图 API 呼叫失败: {e}")
        image_url = ""

    return {output_variable: image_url}


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


async def execute_tool_executor_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    通用工具执行器节点逻辑
    """
    tool_code = config.get("tool_code", "unknown")
    arguments = variables.get("arguments") or config.get("arguments", {})
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
        else:
            res = f"[工具中心] 找不到系统工具 Code: '{tool_code}'"
    except Exception as e:
        res = f"[工具中心报错] 执行异常: {e}"

    return {output_variable: res}


async def execute_end_node(variables: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    结束节点：支持结构化字段输出和文本/JSON 两种模式
    """
    output_format = config.get("output_format", "")

    if output_format == "json" and config.get("output_fields"):
        # 结构化字段模式：逐字段渲染，组装 JSON 对象
        result = {}
        for field in config["output_fields"]:
            name = field.get("name", "")
            value_tpl = field.get("value", "")
            if not name:
                continue
            rendered = render_template(value_tpl, variables)
            try:
                result[name] = json.loads(rendered)
            except (json.JSONDecodeError, ValueError):
                result[name] = rendered
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
node_registry.register("switch", execute_switch_node)


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
