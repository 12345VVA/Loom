"""工作流图片 URL 消费调度测试（WFI-4a，多模态一期阶段四）。

决策表五级：公网直传短路 → remote_url 优先 → 公网域名拼接 → wf-temp/ 中转 →
情景 C 友好报错。双执行器接入后公网 URL（含 __src 引用）不查库零开销。
"""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from app.core.config import settings
from app.modules.media.service.image_ingress import resolve_consumable_image_url, resolve_image_input_value


class ResolveConsumableImageUrlTest(unittest.TestCase):
    def test_public_url_short_circuits_without_db(self):
        """公网 URL / data URI 直传短路——不查库（现有 __src 工作流零影响）。"""
        with patch("app.modules.media.service.image_ingress._lookup_remote_url") as lookup:
            self.assertEqual(
                resolve_consumable_image_url("https://cdn.example.com/a.jpg"),
                "https://cdn.example.com/a.jpg",
            )
            self.assertEqual(resolve_consumable_image_url("data:image/png;base64,xx"), "data:image/png;base64,xx")
        lookup.assert_not_called()

    def test_prefers_remote_url(self):
        """/uploads 引用且 MediaAsset 已回写 remote_url → 直接返回（0 搬运）。"""
        with patch(
            "app.modules.media.service.image_ingress._lookup_remote_url",
            return_value="https://mirror.example.com/assets/a.png",
        ):
            self.assertEqual(
                resolve_consumable_image_url("/uploads/20261011/a.png"),
                "https://mirror.example.com/assets/a.png",
            )

    def test_falls_back_to_absolute_url(self):
        """无 remote_url + 配置了公网域名 → 绝对 URL 拼接（优先 BACKEND_URL）。"""
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url", return_value=None),
            patch.object(settings, "BACKEND_URL", "http://backend:8000"),
            patch.object(settings, "EXTERNAL_URL", ""),
        ):
            self.assertEqual(resolve_consumable_image_url("/uploads/a.png"), "http://backend:8000/uploads/a.png")
        # BACKEND_URL 缺省回落 EXTERNAL_URL
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url", return_value=None),
            patch.object(settings, "BACKEND_URL", ""),
            patch.object(settings, "EXTERNAL_URL", "https://ext.example.com"),
        ):
            self.assertEqual(resolve_consumable_image_url("/uploads/a.png"), "https://ext.example.com/uploads/a.png")

    def test_ingress_transit_when_mirror_available(self):
        """私网兜底地址 + 镜像存储可用 → wf-temp/ 中转上传被调用。"""
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url", return_value=None),
            patch.object(settings, "BACKEND_URL", ""),
            patch.object(settings, "EXTERNAL_URL", ""),
            patch.object(settings, "MEDIA_MIRROR_ENABLED", True),
            patch.object(settings, "MEDIA_MIRROR_BUCKET", "mirror-bucket"),
            patch("app.modules.media.service.image_ingress._read_local_bytes", return_value=b"png"),
            patch("app.modules.media.service.mirror_service.MediaMirrorService") as mirror_cls,
        ):
            mirror_cls.return_value.upload_mirror_object.return_value = "https://bucket.tos.example/wf-temp/a.png"
            result = resolve_consumable_image_url("/uploads/20261011/a.png")
        self.assertEqual(result, "https://bucket.tos.example/wf-temp/a.png")
        kwargs = mirror_cls.return_value.upload_mirror_object.call_args.kwargs
        self.assertEqual(kwargs["prefix"], "wf-temp")

    def test_ingress_transit_disabled_without_mirror(self):
        """镜像开关关闭 → 中转不可用 → 落情景 C。"""
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url", return_value=None),
            patch.object(settings, "BACKEND_URL", ""),
            patch.object(settings, "EXTERNAL_URL", ""),
            patch.object(settings, "MEDIA_MIRROR_ENABLED", False),
        ):
            with self.assertRaises(ValueError) as ctx:
                resolve_consumable_image_url("/uploads/a.png")
        self.assertIn("EXTERNAL_URL", ctx.exception.args[0])
        self.assertIn("对象存储", ctx.exception.args[0])

    def test_prefer_remote_false_skips_lookup(self):
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url") as lookup,
            patch.object(settings, "BACKEND_URL", "http://b:8000"),
            patch.object(settings, "EXTERNAL_URL", ""),
        ):
            self.assertEqual(
                resolve_consumable_image_url("/uploads/a.png", prefer_remote=False),
                "http://b:8000/uploads/a.png",
            )
        lookup.assert_not_called()

    def test_bare_relative_path_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            resolve_consumable_image_url("uploads/a.png")
        self.assertIn("以 / 开头", ctx.exception.args[0])


class ResolveImageInputValueTest(unittest.TestCase):
    """形态保持：str 进 str 出、list 进 list 出、None 直通。"""

    def test_shape_preserved(self):
        self.assertIsNone(resolve_image_input_value(None))
        self.assertEqual(resolve_image_input_value("https://x/1.jpg"), "https://x/1.jpg")
        self.assertEqual(
            resolve_image_input_value(["https://x/1.jpg", "https://x/2.jpg"]),
            ["https://x/1.jpg", "https://x/2.jpg"],
        )


class ExecutorIntegrationTest(unittest.TestCase):
    """双执行器接入：公网 URL 不查库直传（run_ai_image 收到原值）。"""

    def test_image_generator_public_url_no_lookup(self):
        from app.modules.workflow.service.node_executors import execute_image_generator_node

        config = {
            "id": "n1",
            "model_profile_code": "p1",
            "prompt_template": "画",
            "output_variable": "image_url",
            "image_variable": "ref",
        }
        with (
            patch(
                "app.modules.workflow.service.node_executors.run_ai_image",
                return_value={"url": "https://out/1.png", "result": {}, "request_payload": {}},
            ) as run,
            patch(
                "app.modules.workflow.service.node_executors._persist_image_to_media", return_value="/uploads/out.png"
            ),
            patch("app.modules.media.service.image_ingress._lookup_remote_url") as lookup,
        ):
            result = asyncio.run(execute_image_generator_node({"ref": "https://vendor/tmp/0.jpeg"}, config))
        lookup.assert_not_called()
        # run_ai_image(profile_code, prompt, size, image, options)——image 是第 4 个位置参数
        self.assertEqual(run.call_args[0][3], "https://vendor/tmp/0.jpeg")
        self.assertEqual(result["image_url"], "/uploads/out.png")

    def test_llm_node_scenario_c_raises_friendly(self):
        from app.modules.workflow.service.node_executors import execute_llm_node

        config = {
            "model_profile_code": "p1",
            "prompt_template": "看图",
            "output_variable": "out",
            "image_variables": ["img"],
        }
        with (
            patch("app.modules.media.service.image_ingress._lookup_remote_url", return_value=None),
            patch.object(settings, "BACKEND_URL", ""),
            patch.object(settings, "EXTERNAL_URL", ""),
            patch.object(settings, "MEDIA_MIRROR_ENABLED", False),
        ):
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(execute_llm_node({"img": "/uploads/a.png"}, config))
        self.assertIn("对象存储", ctx.exception.args[0])


if __name__ == "__main__":
    unittest.main()
