"""E3 可逆写工具测试（二批 3.4）：发布 ack 双道校验 / 写工具执行与 target_ref 审计 /
乐观比对冲突拒绝 / 属主限定 / draft 状态机边界 / reversible 不触发审批（与 E4 边界）。

装配：真实注册表（4 个 reversible_write 工具经 SPI 收集）+ 直插发布快照行（绕过发布流
校验的场景用 ack=true 预置）。
"""

from __future__ import annotations

import base64
import json
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from helpers import make_test_engine, seed_chat_channel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_RUN_TERMINAL_STATUSES,
    AgentMessage,
    AgentProfile,
    AgentProfileDraft,
    AgentProfilePublishRecord,
    AgentProfileSnapshot,
    AgentRunTrace,
    AgentSession,
    AgentToolApproval,
    AgentToolCallLog,
    AgentToolResource,
    AgentToolResourceVersion,
)
from app.modules.agent.service.runtime import model_wrapper as model_wrapper_module
from app.modules.agent.service.runtime.run_service import AgentRunService
from app.modules.agent.service.tool_registry import bootstrap_registry, get_tool, sync_resources
from app.modules.ai.model.ai import AiModel, AiModelProfile, AiProvider
from app.modules.asset.model.asset import AssetCharacter
from app.modules.asset.service.agent_tools import (
    CreateAssetDraftArgs,
    UpdateAssetDraftArgs,
    create_asset_draft,
    update_asset_draft,
)
from app.modules.base.model.sys import SysLog
from app.modules.media.model.media import MediaAsset
from app.modules.media.service.agent_tools import RenameMediaArgs, TagMediaArgs, rename_media, tag_media


class _FakeUser:
    def __init__(self, id: int, is_super_admin: bool = False):
        self.id = id
        self.is_super_admin = is_super_admin
        self.name = f"user-{id}"


class _Ctx:
    """工具执行的鸭子类型 ctx（含 E3 audit_target_ref 约定属性）。"""

    def __init__(self, session: Session, user_id: int = 1, is_super_admin: bool = False):
        self.db = session
        self.user_id = user_id
        self.user_name = f"user-{user_id}"
        self.is_super_admin = is_super_admin
        self.audit_target_ref = None
        self.trace_id = None  # generate_image 的 R5 审计归因通道（单元场景无 trace）


class _ScriptedRenameModel:
    """首轮要求 rename_media（args 合法）；恢复/收尾轮给最终回答。

    anchor 为类属性：invoke 用例建媒体行后注入实际 updated_at（default_factory 非
    显式可控——显式传值不生效，见 WriteToolUnitTest 锚点口径）。
    """

    anchor: str = ""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def bind_tools(self, tools, **kwargs):
        # 生产装配无条件接线（工具 schema 下发）；桩无需绑定状态，适配为透传
        return self

    # 生产装配 sync 轮已切 generate_raw（usage 断链修复）——桩委托对齐
    def generate_raw(self, messages, **kwargs):
        return self.generate(messages, **kwargs)

    def generate(self, messages, **kwargs):
        msgs = messages[0] if messages and isinstance(messages[0], list) else messages
        last = msgs[-1] if msgs else None
        if isinstance(last, ToolMessage):
            return LLMResult(
                generations=[[ChatGeneration(message=AIMessage(content="写操作已完成"))]],
                llm_output={"usage": {"totalTokens": 20}},
            )
        return LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "rename_media",
                                    "args": {
                                        "media_id": 1,
                                        "new_name": "银发少女-v2.png",
                                        "expected_updated_at": self.anchor,
                                    },
                                    "id": "call_w1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            ],
            llm_output={"usage": {"totalTokens": 50}},
        )


class WriteToolUnitTest(unittest.TestCase):
    """写工具单元级：执行链 / 审计 / 乐观锁 / 属主 / 状态机。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AssetCharacter.__table__,
                MediaAsset.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        sync_resources(self.session)
        self.owner_ctx = _Ctx(self.session, user_id=1)
        self.other_ctx = _Ctx(self.session, user_id=2)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _make_media(self, owner_id: int = 1) -> MediaAsset:
        """建媒体行；锚点口径 = commit+refresh 后的实际 updated_at（default_factory 时刻）。"""
        row = MediaAsset(file_name="old.png", mime_type="image/png", status="success", created_by=owner_id)
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def _anchor(self, row: MediaAsset) -> str:
        self.session.refresh(row)
        return row.updated_at.isoformat()

    def test_create_and_update_asset_draft_lifecycle(self):
        """创建 draft（code 自动生成）→ 本人编辑 → published 拒改 → 他人拒改。"""
        result = json.loads(
            create_asset_draft(CreateAssetDraftArgs(asset_type="character", name="小白"), self.owner_ctx)
        )
        self.assertTrue(result["created"])
        self.assertTrue(result["code"].startswith("ch-"))  # asset code 前例
        self.assertEqual(result["status"], "draft")
        self.assertEqual(self.owner_ctx.audit_target_ref, f"character:{result['id']}")

        updated = json.loads(
            update_asset_draft(
                UpdateAssetDraftArgs(
                    asset_type="character", asset_id=result["id"], name="小白-改", tags=["主角", " 银发 "]
                ),
                self.owner_ctx,
            )
        )
        self.assertTrue(updated["updated"])
        row = self.session.get(AssetCharacter, result["id"])
        self.assertEqual(row.name, "小白-改")
        self.assertEqual(json.loads(row.tags or "[]"), ["主角", "银发"])  # 标签清洗

        # published 态拒改（状态机边界）
        row.status = "published"
        self.session.add(row)
        self.session.commit()
        denied = json.loads(
            update_asset_draft(
                UpdateAssetDraftArgs(asset_type="character", asset_id=result["id"], name="越权"), self.owner_ctx
            )
        )
        self.assertFalse(denied["updated"])
        self.assertIn("draft", denied["error"])

        # 他人 draft 拒改（属主限定）
        row.status = "draft"
        self.session.add(row)
        self.session.commit()
        foreign = json.loads(
            update_asset_draft(
                UpdateAssetDraftArgs(asset_type="character", asset_id=result["id"], name="越权"), self.other_ctx
            )
        )
        self.assertFalse(foreign["updated"])
        self.assertIn("创建者", foreign["error"])

    def test_rename_media_optimistic_lock_and_owner(self):
        """乐观比对：锚点一致成功；过期锚点拒绝；非属主拒绝；target_ref 上报。"""
        row = self._make_media()
        self._anchor_stale_before = self._anchor(row)
        ok = json.loads(
            rename_media(
                RenameMediaArgs(media_id=row.id, new_name="new.png", expected_updated_at=self._anchor_stale_before),
                self.owner_ctx,
            )
        )
        self.assertTrue(ok["renamed"])
        self.assertEqual(self.owner_ctx.audit_target_ref, f"media:{row.id}")

        stale = json.loads(
            rename_media(
                # 成功写已滚动 updated_at——旧锚点即过期（乐观锁生效的证据）
                RenameMediaArgs(media_id=row.id, new_name="again.png", expected_updated_at=self._anchor_stale_before),
                self.owner_ctx,
            )
        )
        self.assertFalse(stale["renamed"])
        self.assertIn("已被其他人修改", stale["error"])

        foreign = json.loads(
            rename_media(
                RenameMediaArgs(media_id=row.id, new_name="steal.png", expected_updated_at=self._anchor_stale_before),
                self.other_ctx,
            )
        )
        self.assertFalse(foreign["renamed"])
        self.assertIn("属主", foreign["error"])

    def test_tag_media_appends_and_dedups(self):
        """标签追加去重：坏值/空 tags 归 []；不覆盖既有标签。"""
        row = self._make_media()
        row.tags = json.dumps(["已有"], ensure_ascii=False)
        self.session.add(row)
        self.session.commit()
        result = json.loads(
            tag_media(
                TagMediaArgs(media_id=row.id, tags=["新标签", "已有", " "], expected_updated_at=self._anchor(row)),
                self.owner_ctx,
            )
        )
        self.assertTrue(result["tagged"])
        self.assertEqual(result["tags"], ["已有", "新标签"])  # 去重 + 空白剔除
        self.assertEqual(self.owner_ctx.audit_target_ref, f"media:{row.id}")

    def test_safety_contract_and_approval_boundary(self):
        """E4 边界：reversible_write 不触发审批判定；dangerous_write 才触发。"""
        from app.modules.agent.service.approval_service import approval_required_for

        self.assertFalse(approval_required_for("rename_media"))
        self.assertFalse(approval_required_for("create_asset_draft"))
        self.assertIsNotNone(get_tool("rename_media").safety)


class WritePublishFlowTestCase(unittest.TestCase):
    """发布/发起双道 ack 校验 + reversible 全链不挂起（invoke）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentSession.__table__,
                AgentMessage.__table__,
                AgentRunTrace.__table__,
                AgentToolApproval.__table__,
                AgentToolCallLog.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                MediaAsset.__table__,
                AiProvider.__table__,
                AiModel.__table__,
                AiModelProfile.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        seed_chat_channel(self.engine)
        sync_resources(self.session)
        self.profile = AgentProfile(
            code="ag-e3test",
            name="写工具测试",
            model_profile_code="deepseek-chat",
            system_prompt="测试",
            tools=json.dumps(["rename_media"]),
            write_tools_ack=True,
            status="published",
            created_by=1,
        )
        self.session.add(self.profile)
        self.session.commit()
        self.session.refresh(self.profile)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _publish_snapshot(self) -> None:
        tool = get_tool("rename_media")
        payload = {
            "profile": {
                "name": "写工具测试",
                "systemPrompt": "测试",
                "maxTokens": 4000,
                "maxToolRounds": 12,
                "timeoutSeconds": 60,
                "temperature": 0.5,
                "enableMemory": True,
            },
            "modelProfileCode": "deepseek-chat",
            "tools": ["rename_media"],
            "toolResourceSnapshots": [
                {
                    "toolName": "rename_media",
                    "displayName": "重命名",
                    "level": "reversible_write",
                    "parameters": tool.parameters,
                }
            ],
            "guardrailsVersion": "1",
        }
        snapshot = AgentProfileSnapshot(
            profile_id=self.profile.id,
            version=1,
            source_draft_version=1,
            snapshot_hash="e3-hash",
            agent_name="写工具测试",
            agent_code=self.profile.code,
            snapshot_json=json.dumps(payload, ensure_ascii=False),
            created_by=1,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        self.session.add(
            AgentProfilePublishRecord(
                profile_id=self.profile.id, snapshot_id=snapshot.id, action="publish", is_current=1, operated_by=1
            )
        )
        self.session.commit()

    def test_publish_requires_write_ack(self):
        """发布第一道：绑定写工具但未 ack → 400（writeToolsAck 文案）；ack 后放行。"""
        from app.modules.agent.service.profile_service import AgentProfileService

        self.profile.write_tools_ack = False
        self.session.add(self.profile)
        self.session.commit()
        with self.assertRaises(HTTPException) as ctx:
            AgentProfileService(self.session).publish(self.profile.id, current_user=_FakeUser(1))
        self.assertIn("writeToolsAck", ctx.exception.detail)

        self.profile.write_tools_ack = True
        self.session.add(self.profile)
        self.session.commit()
        AgentProfileService(self.session).publish(self.profile.id, current_user=_FakeUser(1))  # 不抛

    def test_run_requires_write_ack_realtime(self):
        """发起第二道（实时）：发布后撤回 ack → invoke 400。"""
        self._publish_snapshot()
        self.profile.write_tools_ack = False  # 发布后撤回确认
        self.session.add(self.profile)
        self.session.commit()
        with self.assertRaises(HTTPException) as ctx:
            AgentRunService(self.session).invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="改名",
                run_mode="published",
                current_user=_FakeUser(1),
            )
        self.assertIn("writeToolsAck", ctx.exception.detail)

    def test_reversible_write_executes_without_approval(self):
        """与 E4 边界：reversible_write 全链执行不挂起，target_ref 落 tool_call_log。"""
        self._publish_snapshot()
        media = MediaAsset(file_name="old.png", mime_type="image/png", status="success", created_by=1)
        self.session.add(media)
        self.session.commit()
        self.session.refresh(media)
        _ScriptedRenameModel.anchor = media.updated_at.isoformat()

        with patch.object(model_wrapper_module, "LoomChatModel", _ScriptedRenameModel):
            result = AgentRunService(self.session).invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="把图改名",
                run_mode="published",
                current_user=_FakeUser(1),
            )
        self.session.expire_all()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(self.session.exec(select(AgentToolApproval)).all(), [])  # 零审批行（不挂起）

        media2 = self.session.get(MediaAsset, media.id)
        self.assertEqual(media2.file_name, "银发少女-v2.png")  # 模型桩的写调用真实执行
        log = self.session.exec(select(AgentToolCallLog)).one()
        self.assertEqual(log.target_ref, f"media:{media.id}")  # 审计目标引用落库
        self.assertTrue(log.success)

        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertIn(trace.status, AGENT_RUN_TERMINAL_STATUSES)


# --- generate_image 生图工具（media 侧文生图落媒体库）---


def _png_bytes(color: tuple[int, int, int]) -> bytes:
    """生成最小合法 PNG（字节头探测宽高与 md5 去重都需要真实字节）。"""
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (2, 2), color).save(buf, format="PNG")
    return buf.getvalue()


def _image_result(data: list[dict]) -> dict:
    """AiModelRuntimeService.image 的最小返回形态（runtime_service.py:651 组装子集）。"""
    return {"success": True, "provider": "prov-x", "model": "img-1", "profile": "agent-image-p", "data": data}


def _patch_storage():
    storage = Mock()
    storage.save.return_value = "/uploads/20260503/generated.png"
    return patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage)


class GenerateImageUnitTest(unittest.TestCase):
    """generate_image 单元级：入库管线 / 软失败 / 错误冒泡 / 参数校验 / 多图。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                MediaAsset.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        sync_resources(self.session)
        self.ctx = _Ctx(self.session, user_id=1)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _patch_image(self, return_value=None, side_effect=None):
        return patch(
            "app.modules.ai.service.runtime_service.AiModelRuntimeService.image",
            return_value=return_value,
            side_effect=side_effect,
        )

    def test_generate_image_happy_path_b64(self):
        """b64 产物入库：ai_sync/success/prompt/三码/宽高（字节探测）+ audit_ref + 返回 mediaId。"""
        result = _image_result([{"b64_json": base64.b64encode(_png_bytes((255, 0, 0))).decode()}])
        with self._patch_image(result), _patch_storage():
            from app.modules.media.service.agent_tools import GenerateImageArgs, generate_image

            payload = json.loads(generate_image(GenerateImageArgs(prompt="银发少女"), self.ctx))
        row = self.session.exec(select(MediaAsset)).one()
        self.assertEqual(row.source_type, "ai_sync")
        self.assertEqual(row.status, "success")
        self.assertEqual(row.asset_type, "image")
        self.assertEqual(row.prompt, "银发少女")
        self.assertEqual(row.provider_code, "prov-x")
        self.assertEqual(row.model_code, "img-1")
        self.assertEqual(row.profile_code, "agent-image-p")
        self.assertEqual((row.width, row.height), (2, 2))  # 字节头探测生效
        self.assertEqual(row.created_by, 1)
        self.assertEqual(self.ctx.audit_target_ref, f"media:{row.id}")
        self.assertEqual(payload["mediaId"], row.id)
        self.assertEqual(payload["mediaIds"], [row.id])
        self.assertEqual(payload["url"], "/uploads/20260503/generated.png")

    def test_generate_image_url_path(self):
        """url 产物走 _validate_remote_url + _download_remote_file 下载链（SSRF 防线所在）。"""
        result = _image_result([{"url": "https://cdn.example.com/x/a.png"}])
        png = _png_bytes((0, 255, 0))
        with (
            self._patch_image(result),
            _patch_storage(),
            patch(
                "app.modules.media.service.media_service._validate_remote_url",
                return_value=("https://cdn.example.com/x/a.png", "cdn.example.com"),
            ),
            patch(
                "app.modules.media.service.media_service._download_remote_file",
                return_value=(png, "image/png"),
            ),
        ):
            from app.modules.media.service.agent_tools import GenerateImageArgs, generate_image

            payload = json.loads(generate_image(GenerateImageArgs(prompt="风景"), self.ctx))
        row = self.session.exec(select(MediaAsset)).one()
        self.assertEqual(row.status, "success")
        self.assertEqual(row.original_url, "https://cdn.example.com/x/a.png")
        self.assertEqual(payload["mediaId"], row.id)

    def test_generate_image_soft_failure_when_all_transfer_failed(self):
        """全部转存失败（单张失败不抛异常落 failed 行）→ B2 软失败 ok:false。"""
        result = _image_result([{"b64_json": base64.b64encode(_png_bytes((0, 0, 255))).decode()}])
        storage = Mock()
        storage.save.side_effect = RuntimeError("disk full")
        with (
            self._patch_image(result),
            patch("app.modules.media.service.media_service.StorageService.get_instance", return_value=storage),
        ):
            from app.modules.media.service.agent_tools import GenerateImageArgs, generate_image

            payload = json.loads(generate_image(GenerateImageArgs(prompt="测试"), self.ctx))
        self.assertFalse(payload["ok"])  # B2：执行器归 success=False + skipped_reason=soft_failure
        row = self.session.exec(select(MediaAsset)).one()
        self.assertEqual(row.status, "failed")

    def test_generate_image_invocation_error_propagates(self):
        """渠道未配置（404 AiInvocationError/HTTPException 子类）冒泡 + 零媒体行。"""
        with self._patch_image(side_effect=HTTPException(status_code=404, detail="未找到可用的模型调用配置")):
            from app.modules.media.service.agent_tools import GenerateImageArgs, generate_image

            with self.assertRaises(HTTPException) as caught:
                generate_image(GenerateImageArgs(prompt="测试"), self.ctx)
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(self.session.exec(select(MediaAsset)).all(), [])

    def test_generate_image_prompt_validation(self):
        """prompt 空/超 2000 → ValidationError（执行器归 invalid_args）。"""
        from pydantic import ValidationError as PydValidationError

        from app.modules.media.service.agent_tools import GenerateImageArgs

        with self.assertRaises(PydValidationError):
            GenerateImageArgs(prompt="")
        with self.assertRaises(PydValidationError):
            GenerateImageArgs(prompt="画" * 2001)

    def test_multi_image_ingests_all_returns_first(self):
        """多张全量入库（计费已发生）：mediaIds 长 2、mediaId=首个成功行。"""
        result = _image_result(
            [
                {"b64_json": base64.b64encode(_png_bytes((255, 0, 0))).decode()},
                {"b64_json": base64.b64encode(_png_bytes((0, 0, 255))).decode()},  # 不同字节避 md5 去重合并
            ]
        )
        with self._patch_image(result), _patch_storage():
            from app.modules.media.service.agent_tools import GenerateImageArgs, generate_image

            payload = json.loads(generate_image(GenerateImageArgs(prompt="两联画"), self.ctx))
        rows = self.session.exec(select(MediaAsset)).all()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r.status == "success" for r in rows))
        self.assertEqual(len(payload["mediaIds"]), 2)
        self.assertEqual(payload["mediaId"], payload["mediaIds"][0])


class _ScriptedImageModel:
    """首轮要求 generate_image（args 合法）；工具结果轮给最终回答。"""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self._runtime_service = None

    def bind_tools(self, tools, **kwargs):
        return self

    def generate_raw(self, messages, **kwargs):
        return self.generate(messages, **kwargs)

    def generate(self, messages, **kwargs):
        msgs = messages[0] if messages and isinstance(messages[0], list) else messages
        last = msgs[-1] if msgs else None
        if isinstance(last, ToolMessage):
            return LLMResult(
                generations=[[ChatGeneration(message=AIMessage(content="图已生成并保存到媒体库"))]],
                llm_output={"usage": {"totalTokens": 20}},
            )
        return LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "generate_image",
                                    "args": {"prompt": "银发少女，动漫风"},
                                    "id": "call_img1",
                                    "type": "tool_call",
                                }
                            ],
                        )
                    )
                ]
            ],
            llm_output={"usage": {"totalTokens": 50}},
        )


class GenerateImagePublishFlowTestCase(unittest.TestCase):
    """发布/发起双道 timeout 校验 + 生图全链执行（invoke）。"""

    def setUp(self):
        self.engine = make_test_engine(
            tables=[
                AgentProfile.__table__,
                AgentProfileDraft.__table__,
                AgentProfilePublishRecord.__table__,
                AgentProfileSnapshot.__table__,
                AgentSession.__table__,
                AgentMessage.__table__,
                AgentRunTrace.__table__,
                AgentToolApproval.__table__,
                AgentToolCallLog.__table__,
                AgentToolResource.__table__,
                AgentToolResourceVersion.__table__,
                MediaAsset.__table__,
                AiProvider.__table__,
                AiModel.__table__,
                AiModelProfile.__table__,
                SysLog.__table__,
            ]
        )
        self.session = Session(self.engine)
        bootstrap_registry()
        seed_chat_channel(self.engine)
        sync_resources(self.session)
        self.profile = AgentProfile(
            code="ag-imgtest",
            name="生图测试",
            model_profile_code="deepseek-chat",
            system_prompt="测试",
            tools=json.dumps(["generate_image"]),
            write_tools_ack=True,
            timeout_seconds=120,
            status="published",
            created_by=1,
        )
        self.session.add(self.profile)
        self.session.commit()
        self.session.refresh(self.profile)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()
        bootstrap_registry()

    def _publish_snapshot(self) -> None:
        tool = get_tool("generate_image")
        payload = {
            "profile": {
                "name": "生图测试",
                "systemPrompt": "测试",
                "maxTokens": 4000,
                "maxToolRounds": 12,
                "timeoutSeconds": 120,
                "temperature": 0.5,
                "enableMemory": True,
            },
            "modelProfileCode": "deepseek-chat",
            "tools": ["generate_image"],
            "toolResourceSnapshots": [
                {
                    "toolName": "generate_image",
                    "displayName": "生成图片",
                    "level": "reversible_write",
                    "parameters": tool.parameters,
                }
            ],
            "guardrailsVersion": "1",
        }
        snapshot = AgentProfileSnapshot(
            profile_id=self.profile.id,
            version=1,
            source_draft_version=1,
            snapshot_hash="img-hash",
            agent_name="生图测试",
            agent_code=self.profile.code,
            snapshot_json=json.dumps(payload, ensure_ascii=False),
            created_by=1,
        )
        self.session.add(snapshot)
        self.session.commit()
        self.session.refresh(snapshot)
        self.session.add(
            AgentProfilePublishRecord(
                profile_id=self.profile.id, snapshot_id=snapshot.id, action="publish", is_current=1, operated_by=1
            )
        )
        self.session.commit()

    def test_publish_generate_image_requires_timeout_120(self):
        """发布第一道：绑定生图工具 + run 时限 <120 → 400；调到 120 放行。"""
        from app.modules.agent.service.profile_service import AgentProfileService

        self.profile.timeout_seconds = 60
        self.session.add(self.profile)
        self.session.commit()
        with self.assertRaises(HTTPException) as caught:
            AgentProfileService(self.session).publish(self.profile.id, current_user=_FakeUser(1))
        self.assertIn("120", caught.exception.detail)

        self.profile.timeout_seconds = 120
        self.session.add(self.profile)
        self.session.commit()
        AgentProfileService(self.session).publish(self.profile.id, current_user=_FakeUser(1))  # 不抛

    def test_run_rejects_lowered_timeout_realtime(self):
        """发起实时道：发布后把活行 timeout 调回 60 → invoke 400（run deadline 读活行）。"""
        self._publish_snapshot()
        self.profile.timeout_seconds = 60
        self.session.add(self.profile)
        self.session.commit()
        with self.assertRaises(HTTPException) as caught:
            AgentRunService(self.session).invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="画一张",
                run_mode="published",
                current_user=_FakeUser(1),
            )
        self.assertIn("120", caught.exception.detail)

    def test_generate_image_full_chain_executes(self):
        """全链：脚本模型发起 generate_image → 真入库 → target_ref 审计 → 零审批行。"""
        self._publish_snapshot()
        result = _image_result([{"b64_json": base64.b64encode(_png_bytes((128, 0, 128))).decode()}])
        with (
            patch.object(model_wrapper_module, "LoomChatModel", _ScriptedImageModel),
            patch("app.modules.ai.service.runtime_service.AiModelRuntimeService.image", return_value=result),
            _patch_storage(),
        ):
            run_result = AgentRunService(self.session).invoke_run(
                profile_id=self.profile.id,
                session_id=None,
                question="画一只银发少女",
                run_mode="published",
                current_user=_FakeUser(1),
            )
        self.session.expire_all()
        self.assertEqual(run_result["status"], "completed")
        self.assertEqual(self.session.exec(select(AgentToolApproval)).all(), [])  # reversible 不挂起

        row = self.session.exec(select(MediaAsset)).one()
        self.assertEqual(row.status, "success")
        self.assertEqual(row.created_by, 1)
        log = self.session.exec(select(AgentToolCallLog)).one()
        self.assertEqual(log.target_ref, f"media:{row.id}")
        self.assertTrue(log.success)

        trace = self.session.exec(select(AgentRunTrace)).first()
        self.assertIn(trace.status, AGENT_RUN_TERMINAL_STATUSES)
