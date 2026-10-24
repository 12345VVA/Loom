"""LoomChatModel（设计 3.4.2，D2 渠道归 ai）：BaseChatModel 包装 ai runtime_service。

- 工具 schema 经 ``AiChatRequest.options``（openai 标准参数全量透传，已核实无白名单）；
- **trace 关联走 task_id 审计通道**（R5）：``runtime_service.chat(payload, current_user, task_id=trace.id)``
  → ``AiModelCallLog.task_id``（indexed，语义借用，实施首日真机验证五项）；
- **实例纪律**：每个 run 独立创建实例，bind_tools 的可变绑定状态不跨 run/跨智能体共享；
- 一期工具循环仅绑定 openai-compatible 渠道 profile（R1：其他文本 adapter 的 tools 未验证）；
- 一期不做 token 级流式（明确决策）：SSE 事件粒度 = 轮次/工具/最终答案整段。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import PrivateAttr

from app.modules.ai.model.ai import AiChatRequest, AiRuntimeMessage

logger = logging.getLogger("agent.model_wrapper")


def _message_to_openai_dict(message: BaseMessage) -> dict:
    """langchain 消息 → openai 协议 dict（agent 消息链含 tool_calls / tool_call_id 配对）。"""
    role = message.type
    if role == "ai":
        role = "assistant"
    elif role == "human":
        role = "user"
    item: dict[str, Any] = {
        "role": role,
        "content": message.content if isinstance(message.content, str) else str(message.content),
    }
    if role == "assistant":
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            item["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {"name": call["name"], "arguments": json.dumps(call["args"], ensure_ascii=False)},
                }
                for call in tool_calls
            ]
    if isinstance(message, ToolMessage):
        item["role"] = "tool"
        item["tool_call_id"] = message.tool_call_id or ""
        if message.name:
            item["name"] = message.name
    return item


class LoomChatModel(BaseChatModel):
    """经 ai 模型注册表出话的 BaseChatModel（构造即绑定渠道与采样参数）。"""

    model_profile_code: str
    temperature: float = 0.5
    max_tokens: int = 4000
    profile_source: str = "published"  # draft/published（载荷来源，观测用）
    timeout_seconds: int | None = None  # 本轮请求超时（min(run 剩余, profile.timeout)）
    min_context_window: int | None = None  # E15：解析链最小窗口（ai 回退路径校验约束）

    # 非序列化运行时依赖（ai 服务与调用者身份；不参与 pydantic 校验）
    _runtime_service: Any = PrivateAttr(default=None)
    _caller: Any = PrivateAttr(default=None)  # User（审计归因）
    _task_id: int | None = PrivateAttr(default=None)  # trace.id（R5 审计通道）
    _bound_schemas: list[dict] | None = PrivateAttr(default=None)

    @classmethod
    def is_lc_serializable(cls) -> bool:
        return False

    @property
    def _llm_type(self) -> str:
        return "loom-chat"

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> LoomChatModel:
        """经 convert_to_openai_tool 转 schema 存自有字段（openai 标准参数透传）。"""
        self._bound_schemas = [convert_to_openai_tool(tool) for tool in tools]
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self._runtime_service is None:
            # 服务实例由调用方注入（含请求级 Session）；此处兜底自建仅适用于单测装配
            raise RuntimeError("LoomChatModel 未装配 runtime_service（单 run 实例须由 RunService 注入）")

        payload = AiChatRequest(
            profile_code=self.model_profile_code,
            messages=[AiRuntimeMessage(**_message_to_openai_dict(m)) for m in messages],
            options=self._build_options(),
        )
        result = self._runtime_service.chat(
            payload,
            current_user=self._caller,
            task_id=self._task_id,
            min_context_window=self.min_context_window,  # E15：窗口不足的回退路径在 ai 侧拒绝
            # 护栏 system 消息由服务端拼装（内容固定），对其做注入扫描会自证命中拦死全部对话
            # （走查实测「hello」也 400）；用户输入仍在 user/tool 消息全量扫描
            scan_system_messages=False,
        )
        if not result.get("success"):
            raise RuntimeError(f"模型调用失败：{result.get('error') or result}")
        raw = result.get("raw") or {}
        content = result.get("content")
        if content is None:
            content = ""
        tool_calls = _parse_tool_calls(raw)
        message = AIMessage(content=content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
        if tool_calls:
            message.additional_kwargs["tool_calls"] = tool_calls
            message.tool_calls = [
                {
                    "name": call["function"]["name"],
                    "args": _parse_arguments(call["function"].get("arguments")),
                    "id": call["id"],
                    "type": "tool_call",
                }
                for call in tool_calls
                if call.get("function", {}).get("name")
            ]
        usage = result.get("usage") or {}
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={
                "model_profile": self.model_profile_code,
                "usage": usage,
                "request_id": result.get("requestId"),
            },
        )

    def generate_streaming(self, messages: list[BaseMessage], on_delta) -> ChatResult:
        """E1 最终答案候选轮流式：经 ai ``chat_iter`` 管线（task_id 审计通道 + 窗口约束），
        content 增量实时回调 ``on_delta(text)``；返回 ChatResult（tool_calls 归一化、
        usage 计数），供图统一消费与服务端撤销判定。

        注意 messages 为**平铺** list[BaseMessage]（区别于 langchain generate 的 batch
        语义——那是「LLMResult 两层 generations」的来源）；工具决策响应的判定依据 =
        done 事件携带的聚合 toolCalls（openai 流式增量聚合）。仅 openai-compatible
        渠道（R1）；实例纪律同 _generate。
        """
        if self._runtime_service is None:
            raise RuntimeError("LoomChatModel 未装配 runtime_service（单 run 实例须由 RunService 注入）")

        payload = AiChatRequest(
            profile_code=self.model_profile_code,
            messages=[AiRuntimeMessage(**_message_to_openai_dict(m)) for m in messages],
            options=self._build_options(),
        )
        content_parts: list[str] = []
        tool_calls: list[dict] = []
        usage: dict = {}
        request_id = None
        for frame in self._runtime_service.chat_iter(
            payload,
            current_user=self._caller,
            task_id=self._task_id,
            min_context_window=self.min_context_window,
            scan_system_messages=False,  # 同 chat：护栏 system 可信，不参与注入扫描
        ):
            event = _parse_sse_frame(frame)
            if event is None:
                continue  # 心跳注释帧
            name = event.get("event")
            if name == "delta":
                text = event.get("content") or ""
                if text:
                    content_parts.append(text)
                    on_delta(text)
            elif name == "done":
                usage = event.get("usage") or {}
                request_id = event.get("requestId")
                tool_calls = list(event.get("toolCalls") or [])
            elif name == "error":
                raise RuntimeError(f"模型流式调用失败：{event.get('message') or event}")
        content = "".join(content_parts)
        message = AIMessage(content=content)
        if tool_calls:
            message.additional_kwargs["tool_calls"] = tool_calls
            message.tool_calls = [
                {
                    "name": call["function"]["name"],
                    "args": _parse_arguments(call["function"].get("arguments")),
                    "id": call["id"],
                    "type": "tool_call",
                }
                for call in tool_calls
                if call.get("function", {}).get("name")
            ]
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output={
                "model_profile": self.model_profile_code,
                "usage": usage,
                "request_id": request_id,
            },
        )

    def _build_options(self) -> dict:
        """openai 标准采样参数 + 工具 schema（options 全量透传，无白名单——不得放自定义键）。"""
        options: dict[str, Any] = {"temperature": self.temperature, "max_tokens": self.max_tokens}
        if self.timeout_seconds:
            # openai SDK 的请求级超时参数（真正终止阻塞中的模型请求，取消三层语义之三）
            options["timeout"] = self.timeout_seconds
        if self._bound_schemas:
            options["tools"] = self._bound_schemas
        return options


def _parse_sse_frame(frame: str) -> dict | None:
    """ai 流式管线单帧解析：``data: {json}``；注释/心跳帧返回 None。"""
    text = frame.strip()
    if not text.startswith("data:"):
        return None
    return json.loads(text[5:].strip())


def _parse_tool_calls(raw: dict) -> list[dict]:
    """从 openai 响应 raw 中解析 tool_calls（R4：LoomChatModel 内归一化）。"""
    try:
        calls = ((raw.get("choices") or [{}])[0].get("message") or {}).get("tool_calls") or []
    except (AttributeError, IndexError, TypeError):
        return []
    normalized = []
    for call in calls:
        function = call.get("function") or {}
        if function.get("name"):
            normalized.append({"id": call.get("id") or "", "function": function})
    return normalized


def _parse_arguments(arguments: Any) -> dict:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str) and arguments.strip():
        try:
            parsed = json.loads(arguments)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return {"_raw": arguments}
    return {}
