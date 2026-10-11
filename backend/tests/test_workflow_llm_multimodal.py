"""工作流 LLM 节点多模态图片输入测试（WFI-2a，多模态一期阶段二）。

覆盖：
- _resolve_image_inputs：变量引用（str/list）/模板回退/渲染失败降级/空值过滤
- execute_llm_node：有图组装 OpenAI 风格 IR parts，无图维持纯文本（零变化）
- DTO 链路：AiRuntimeMessage/AiChatRequest 接受 list content 且 model_dump 保留结构
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.modules.ai.model.ai import AiChatRequest, AiRuntimeMessage
from app.modules.workflow.service.node_executors import _resolve_image_inputs, execute_llm_node


class ResolveImageInputsTest(unittest.TestCase):
    def test_single_variable(self):
        urls = _resolve_image_inputs({"image_variables": ["input_image"]}, {"input_image": "/uploads/a.png"})
        self.assertEqual(urls, ["/uploads/a.png"])

    def test_list_of_variables_flattened_with_blank_filtered(self):
        urls = _resolve_image_inputs(
            {"image_variables": ["a", "b", "missing"]},
            {"a": "https://x/1.jpg", "b": ["https://x/2.jpg", "", "  "]},
        )
        self.assertEqual(urls, ["https://x/1.jpg", "https://x/2.jpg"])

    def test_string_shorthand_and_template_fallback(self):
        # image_variables 为字符串简写
        self.assertEqual(
            _resolve_image_inputs({"image_variables": "img"}, {"img": "/uploads/b.png"}), ["/uploads/b.png"]
        )
        # 无变量绑定时走模板渲染兜底
        self.assertEqual(
            _resolve_image_inputs({"image_template": "{ref}"}, {"ref": "https://x/c.jpg"}),
            ["https://x/c.jpg"],
        )

    def test_template_render_failure_degrades_to_empty(self):
        # render_template 对未闭合模板本身是原样返回（不抛），渲染异常路径需 mock 触发
        with patch("app.modules.workflow.service.node_executors.render_template", side_effect=ValueError("boom")):
            urls = _resolve_image_inputs({"image_template": "{ref}"}, {"ref": "x"})
        self.assertEqual(urls, [])

    def test_no_binding_returns_empty(self):
        self.assertEqual(_resolve_image_inputs({}, {}), [])
        self.assertEqual(_resolve_image_inputs({"image_variables": []}, {"a": 1}), [])

    def test_non_string_values_filtered(self):
        urls = _resolve_image_inputs({"image_variables": ["n", "o"]}, {"n": 10, "o": {"k": "v"}})
        self.assertEqual(urls, [])


class ExecuteLlmNodeMultimodalTest(unittest.TestCase):
    def _run(self, config, variables):
        with patch("app.modules.workflow.service.node_executors.run_ai_chat", return_value="ok") as mocked:
            result = asyncio.run(execute_llm_node(variables, config))
        return result, mocked

    def test_builds_multimodal_ir_parts(self):
        config = {
            "model_profile_code": "p1",
            "prompt_template": "分析 {input_image}",
            "output_variable": "out",
            "image_variables": ["input_image"],
        }
        result, mocked = self._run(config, {"input_image": "/uploads/a.png"})
        self.assertEqual(result, {"out": "ok"})
        user_content = mocked.call_args[0][1]
        self.assertEqual(
            user_content,
            [
                {"type": "text", "text": "分析 /uploads/a.png"},
                {"type": "image_url", "image_url": {"url": "/uploads/a.png"}},
            ],
        )

    def test_no_image_keeps_plain_text(self):
        config = {"model_profile_code": "p1", "prompt_template": "你好", "output_variable": "out"}
        _, mocked = self._run(config, {})
        self.assertEqual(mocked.call_args[0][1], "你好")

    def test_multi_images_append_multiple_parts(self):
        config = {
            "model_profile_code": "p1",
            "prompt_template": "对比",
            "output_variable": "out",
            "image_variables": ["imgs"],
        }
        _, mocked = self._run(config, {"imgs": ["https://x/1.jpg", "https://x/2.jpg"]})
        user_content = mocked.call_args[0][1]
        image_parts = [p for p in user_content if p["type"] == "image_url"]
        self.assertEqual(len(image_parts), 2)


class MultimodalDtoChainTest(unittest.TestCase):
    """DTO 放宽后：list content 全链路构造/序列化无损（WFI-2a）。"""

    IR = [
        {"type": "text", "text": "这张图里有什么？"},
        {"type": "image_url", "image_url": {"url": "https://example.com/photo.png"}},
    ]

    def test_runtime_message_accepts_and_dumps_list(self):
        msg = AiRuntimeMessage(role="user", content=self.IR)
        self.assertEqual(msg.model_dump()["content"], self.IR)

    def test_chat_request_accepts_list_content_message(self):
        payload = AiChatRequest(profile_code="p1", messages=[{"role": "user", "content": self.IR}])
        dumped = payload.messages[0].model_dump()
        self.assertEqual(dumped["role"], "user")
        self.assertEqual(dumped["content"], self.IR)

    def test_plain_text_unchanged(self):
        msg = AiRuntimeMessage(role="system", content="纯文本")
        self.assertEqual(msg.content, "纯文本")
