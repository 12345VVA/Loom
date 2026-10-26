"""附件上传分析单元测试（走查反馈：图片视觉 + 文本文档注入）。

覆盖：附件归类/校验（404/403/400）、多模态 content 组装、token 估算不含 base64、
消息转换保真（model_wrapper / _as_user_message）、附件 parts 读取降级。
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException
from helpers import make_test_engine
from langchain_core.messages import HumanMessage
from sqlmodel import Session

from app.modules.agent.service.runtime import run_service as rs
from app.modules.agent.service.runtime.memory_service import (
    IMAGE_PART_TOKEN_ESTIMATE,
    _as_user_message,
    _content_part_tokens,
    _message_text,
    _message_tokens,
)
from app.modules.agent.service.runtime.model_wrapper import _message_to_openai_dict
from app.modules.media.model.media import MediaAsset


class _FakeUser:
    """最小用户桩（对齐 test_agent_profile 同款）。"""

    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin


_BIG_B64 = "A" * 200_000  # 模拟 base64 图片数据（≈20 万字符）


def _image_part() -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_BIG_B64}"}}


class AttachmentKindTestCase(unittest.TestCase):
    """_attachment_kind：mime 优先、扩展名兜底、不支持返回 None。"""

    def test_image_mimes(self):
        for mime in ("image/png", "image/jpeg", "image/webp", "image/gif"):
            self.assertEqual(rs._attachment_kind(mime, "x.bin"), "image")

    def test_text_mimes_and_extensions(self):
        self.assertEqual(rs._attachment_kind("text/plain", "a.txt"), "text")
        self.assertEqual(rs._attachment_kind("application/json", "a.json"), "text")
        # mime 缺失/通按时扩展名兜底
        self.assertEqual(rs._attachment_kind("", "a.md"), "text")
        self.assertEqual(rs._attachment_kind("application/octet-stream", "a.py"), "text")
        self.assertEqual(rs._attachment_kind(None, "a.csv"), "text")

    def test_unsupported(self):
        self.assertIsNone(rs._attachment_kind("application/pdf", "a.pdf"))
        self.assertIsNone(rs._attachment_kind("application/zip", "a.zip"))
        self.assertIsNone(rs._attachment_kind("image/svg+xml", "a.svg"))


class AttachmentValidationTestCase(unittest.TestCase):
    """_validate_attachments：404/403/400 与 meta 结构（SQLite 内存表）。"""

    def setUp(self):
        self.engine = make_test_engine(tables=[MediaAsset.__table__])
        self.session = Session(self.engine)
        self.owner = _FakeUser(1)
        self.admin = _FakeUser(9, is_super_admin=True)
        self.image = MediaAsset(
            id=1,
            asset_type="image",
            source_type="upload",
            storage_url="/uploads/202610/a.png",
            file_name="a.png",
            mime_type="image/png",
            size_bytes=1024,
            created_by=1,
        )
        self.text = MediaAsset(
            id=2,
            asset_type="document",
            source_type="upload",
            storage_url="/uploads/202610/b.txt",
            file_name="b.txt",
            mime_type="text/plain",
            size_bytes=100,
            created_by=1,
        )
        self.big = MediaAsset(
            id=3,
            asset_type="image",
            source_type="upload",
            storage_url="/uploads/202610/c.png",
            file_name="c.png",
            mime_type="image/png",
            size_bytes=6 * 1024 * 1024,
            created_by=1,
        )
        self.foreign = MediaAsset(
            id=4,
            asset_type="image",
            source_type="upload",
            storage_url="/uploads/202610/d.png",
            file_name="d.png",
            mime_type="image/png",
            size_bytes=10,
            created_by=2,
        )
        self.pdf = MediaAsset(
            id=5,
            asset_type="document",
            source_type="upload",
            storage_url="/uploads/202610/e.pdf",
            file_name="e.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            created_by=1,
        )
        for row in (self.image, self.text, self.big, self.foreign, self.pdf):
            self.session.add(row)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_ok_returns_meta(self):
        metas = rs._validate_attachments(self.session, [1, 2], self.owner)
        self.assertEqual([m["id"] for m in metas], [1, 2])
        self.assertEqual(metas[0]["kind"], "image")
        self.assertEqual(metas[1]["kind"], "text")
        self.assertEqual(metas[0]["url"], "/uploads/202610/a.png")

    def test_missing_404(self):
        with self.assertRaises(HTTPException) as ctx:
            rs._validate_attachments(self.session, [999], self.owner)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_foreign_403_admin_ok(self):
        with self.assertRaises(HTTPException) as ctx:
            rs._validate_attachments(self.session, [4], self.owner)
        self.assertEqual(ctx.exception.status_code, 403)
        metas = rs._validate_attachments(self.session, [4], self.admin)  # 超管放行
        self.assertEqual(metas[0]["id"], 4)

    def test_oversize_400(self):
        with self.assertRaises(HTTPException) as ctx:
            rs._validate_attachments(self.session, [3], self.owner)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_pdf_400(self):
        with self.assertRaises(HTTPException) as ctx:
            rs._validate_attachments(self.session, [5], self.owner)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("不支持的附件类型", ctx.exception.detail)


class InitialContentTestCase(unittest.TestCase):
    """_build_initial_content：无附件零变化；有附件组多模态数组。"""

    def test_no_attachments_returns_str(self):
        self.assertEqual(rs._build_initial_content("你好", []), "你好")

    def test_with_image_parts(self):
        content = rs._build_initial_content("图里是什么", [_image_part()])
        self.assertIsInstance(content, list)
        self.assertEqual(content[0], {"type": "text", "text": "图里是什么"})
        self.assertEqual(content[1]["type"], "image_url")

    def test_blank_question_image_only(self):
        content = rs._build_initial_content("  ", [{"type": "text", "text": "[附件文件 a.txt]\nx"}])
        self.assertEqual([p["type"] for p in content], ["text"])


class AttachmentPartsTestCase(unittest.TestCase):
    """_build_attachment_parts：图片 dataURI / 文本解码截断 / 读取失败降级。"""

    def test_image_and_text_parts(self):
        metas = [
            {"id": 1, "name": "a.png", "mime": "image/png", "kind": "image", "url": "/uploads/202610/a.png"},
            {"id": 2, "name": "b.txt", "mime": "text/plain", "kind": "text", "url": "/uploads/202610/b.txt"},
        ]

        class _FakeStorage:
            def read(self, path):
                return b"\x89PNG fake" if path.endswith("a.png") else "你好世界".encode() * 5000  # >8000 字符

        with patch("app.framework.storage.StorageService.get_instance", return_value=_FakeStorage()):
            parts = rs._build_attachment_parts(metas)
        self.assertEqual(parts[0]["type"], "image_url")
        self.assertTrue(parts[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        self.assertEqual(parts[1]["type"], "text")
        self.assertIn("[附件文件 b.txt]", parts[1]["text"])
        self.assertIn("已截断", parts[1]["text"])

    def test_read_failure_degrades(self):
        class _BrokenStorage:
            def read(self, path):
                raise OSError("disk gone")

        with patch("app.framework.storage.StorageService.get_instance", return_value=_BrokenStorage()):
            parts = rs._build_attachment_parts(
                [{"id": 1, "name": "a.png", "mime": "image/png", "kind": "image", "url": "/uploads/x.png"}]
            )
        self.assertEqual(parts[0]["type"], "text")
        self.assertIn("读取失败", parts[0]["text"])


class MultimodalTokenTestCase(unittest.TestCase):
    """token 估算：base64 严禁进入文本估算；图片按常数。"""

    def test_message_text_excludes_image_data(self):
        msg = HumanMessage(content=[{"type": "text", "text": "看图"}, _image_part()])
        self.assertNotIn(_BIG_B64, _message_text(msg))
        self.assertIn("看图", _message_text(msg))

    def test_content_part_tokens_constant_for_image(self):
        tokens = _content_part_tokens([{"type": "text", "text": "ab"}, _image_part()])
        # 文本部分可忽略，图片常数主导且远小于 base64 字符数
        self.assertLess(tokens, IMAGE_PART_TOKEN_ESTIMATE * 2)
        self.assertGreaterEqual(tokens, IMAGE_PART_TOKEN_ESTIMATE)

    def test_message_tokens_multimodal_bounded(self):
        msg = HumanMessage(content=[{"type": "text", "text": "x"}, _image_part()])
        self.assertLess(_message_tokens(msg), IMAGE_PART_TOKEN_ESTIMATE * 3)

    def test_as_user_message_preserves_list(self):
        msg = _as_user_message([{"type": "text", "text": "hi"}])
        self.assertIsInstance(msg, HumanMessage)
        self.assertEqual(msg.content, [{"type": "text", "text": "hi"}])

    def test_build_model_messages_multimodal_input(self):
        """回归：多模态 current_input 过预算组装不炸（ord() 只收字符串）。"""
        from app.modules.agent.service.runtime.memory_service import build_model_messages

        msgs = build_model_messages(
            system_message="sys",
            tool_schema_tokens=10,
            injected_context="",
            history=[],
            current_input=[{"type": "text", "text": "看图"}, _image_part()],
            token_budget=6000,
        )
        last = msgs[-1]
        self.assertIsInstance(last.content, list)
        self.assertEqual(last.content[0]["type"], "text")


class MessageConvertTestCase(unittest.TestCase):
    """_message_to_openai_dict：多模态数组保真（此前 str() 化会污染 base64）。"""

    def test_multimodal_content_passthrough(self):
        content = [{"type": "text", "text": "看图"}, _image_part()]
        item = _message_to_openai_dict(HumanMessage(content=content))
        self.assertEqual(item["role"], "user")
        self.assertEqual(item["content"], content)  # 结构保真（langchain 可能拷贝列表，值等价即可）

    def test_str_content_unchanged(self):
        item = _message_to_openai_dict(HumanMessage(content="纯文本"))
        self.assertEqual(item["content"], "纯文本")


if __name__ == "__main__":
    unittest.main()
