"""AssetPromptComposer——资产组装协议（模块灵魂）。

契约唯一依据：设计文档附录 B（docs/02-业务模块/IP资产库模块设计-2026-10-22.md）。
单一来源：后端一处实现，测试页（HTTP）/工作流节点（进程内）共用；前端预览必须调
composer/preview API，禁止复刻拼接逻辑（决策 #26）。

流水线七步（顺序即实现顺序）：加载校验 → 变量渲染（先渲染后拼接）→ 正向四段拼接 →
负面四源去重 → 字符预算压缩 → 参考图解析与注入 → 指纹与收口。
身份核心句（appearance_prompt 非变量部分）与用户正文永不压缩（决策 #31/#35）。
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from app.modules.asset.model.asset import (
    ASSET_STATUS_ARCHIVED,
    ASSET_STATUS_DRAFT,
    COMPOSER_VERSION,
)
from app.modules.media.service.image_ingress import resolve_image_input_value

logger = logging.getLogger(__name__)

# 资产变量占位：{{变量名}}。\w 在 Python3 默认匹配中文（如 {{服装}}）。
ASSET_VAR_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")

# 渠道参考图兜底表（决策 #26：随 Composer 常量维护；键 = provider.adapter）。
# 未知名 → 1（保守兜底）。
ADAPTER_REFERENCE_LIMITS: dict[str, int | None] = {
    "poryf": 1,  # 适配器已核实：仅单张，多张截断告警
    # P7 校准（2026-10-23）：已核实适配器经 client.images.generate 无参考图入参
    # （_OPENAI_IMAGE_ALLOWED_OPTION_KEYS 无 image），参考图会被拦截告警，故 1 为
    # 语义占位——真正支持多图的兼容渠道应显式声明专属适配器后再放开。
    "openai-compatible": 1,
    "toapis": None,  # None = 不限，取全局参数 N
}

# 全局参数键（base sys_param，驼峰风格；种子见模块 config.bootstrap）
PARAM_GLOBAL_NEGATIVE = "assetGlobalNegativePrompt"
PARAM_DEFAULT_REF_IMAGES = "assetDefaultReferenceImages"
PARAM_CHAR_BUDGET = "assetPromptCharBudget"
PARAM_MIN_ANCHOR = "assetMinAnchorImages"

_PARAM_DEFAULTS = {
    PARAM_GLOBAL_NEGATIVE: "",
    PARAM_DEFAULT_REF_IMAGES: "1",
    PARAM_CHAR_BUDGET: "2000",
    PARAM_MIN_ANCHOR: "0",
}

_KIND_LABELS = {"AssetCharacter": "角色卡", "AssetScene": "场景卡", "AssetStyle": "风格卡"}

# 参考图跨资产优先序（设计细化 D7）：身份锚点（角色）> 画风锚（风格）> 场景
_ASSET_REF_ORDER = ("character", "style", "scene")
# 推荐参数来源优先序：风格（推荐模型/参数是其重心）> 角色 > 场景
_PREFERRED_ORDER = ("style", "character", "scene")


# --- 错误码族（设计 3.4：中文 message 直出，HTTP/节点层不再二次包装）---


class AssetError(Exception):
    """资产域错误基类。"""


class AssetNotFoundError(AssetError):
    """软删/不存在（fail-fast）。"""


class AssetStateError(AssetError):
    """状态不可引用（执行期防御）。"""


class AssetVariableMissingError(AssetError):
    """变量缺失，message 已定位资产与变量名（验收 7）。"""


class AssetPromptBudgetError(AssetError):
    """预算仍超限（验收 10：不静默截断正文）。"""


class AssetAnchorError(AssetError):
    """低于最低锚定数（决策 #32 严格模式）。"""


# --- 输入 / 输出契约 ---


def _config_get(config: dict[str, Any], key: str) -> Any:
    """双风格取值（对齐 workflow.node_schema.get_config_value，需求 4.2 工程要点）：
    camelCase 权威键优先，miss 回落 snake_case（手写存量图兼容）。
    asset 不得 import workflow（依赖守卫），故本地实现同款语义。"""
    if key in config:
        return config[key]
    return config.get(re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower())


@dataclass
class ComposerWarning:
    code: str
    message: str
    level: str = "warning"  # "warning" | "info"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "level": self.level}


@dataclass
class ComposeInput:
    character: Any | None = None
    scene: Any | None = None
    style: Any | None = None
    user_prompt: str = ""  # 用户当次正文 / 节点渲染后的 prompt_template；永不压缩
    variables: dict[str, str] = field(default_factory=dict)
    current_user_id: int = 0
    profile_code: str | None = None  # None：不做推荐比对、preferred_size 不生效、参考图按兜底 1 张
    user_size: str | None = None  # 用户显式覆盖（P0-1），优先级高于 preferred_size
    extra_reference_images: list[str] = field(default_factory=list)  # 节点显式图（未调度原值，D6）


@dataclass
class ComposeResult:
    prompt: str
    negative_prompt: str
    reference_images: list[str]
    effective_size: str | None
    warnings: list[ComposerWarning]
    composed_prompt_hash: str
    composer_version: str
    segments: list[dict[str, Any]]  # [{source, text, included}]
    reference_segments: list[dict[str, Any]]  # [{mediaId, role, included, skipReason?}]
    asset_refs: dict[str, int]  # {"characterId": id, ...} 仅非空项（回链透传）

    def to_payload(self) -> dict[str, Any]:
        """API 出口形态（segments/referenceSegments/warnings 结构化，供透明组装）。"""
        return {
            "prompt": self.prompt,
            "negativePrompt": self.negative_prompt,
            "referenceImages": self.reference_images,
            "effectiveSize": self.effective_size,
            "warnings": [w.to_dict() for w in self.warnings],
            "composedPromptHash": self.composed_prompt_hash,
            "composerVersion": self.composer_version,
            "segments": self.segments,
            "referenceSegments": self.reference_segments,
            "assetRefs": self.asset_refs,
        }


# --- 全局参数 ---


def read_asset_params(session) -> dict[str, str]:
    """读 asset 全局参数（缺种子时按默认值兜底，保证组装链路零依赖可跑）。"""
    from app.modules.base.model.sys import SysParam

    found: dict[str, str] = {}
    rows = session.exec(
        select(SysParam.key_name, SysParam.data).where(SysParam.key_name.in_(list(_PARAM_DEFAULTS)))
    ).all()
    for key_name, data in rows:
        if key_name and data is not None:
            found[key_name] = str(data)
    return {**_PARAM_DEFAULTS, **found}


def _int_param(params: dict[str, str], key: str, default: int) -> int:
    try:
        return int(str(params.get(key, "")).strip() or default)
    except (TypeError, ValueError):
        return default


# --- 渠道能力解析（真链依赖 ai RegistryService；单测经 patch 注入）---


def _resolve_channel(session, profile_code: str | None) -> tuple[list[str], str | None]:
    """profile → (model.capabilities 列表, provider.adapter)。None/解析失败 → ([], None)。"""
    if not profile_code:
        return [], None
    try:
        from app.modules.ai.service.registry_service import AiModelRegistryService

        resolved = AiModelRegistryService(session).resolve(model_type="image", profile_code=profile_code)
    except Exception:  # noqa: BLE001——渠道解析失败按未知渠道兜底，不阻断组装
        logger.warning("渠道能力解析失败 profile_code=%s（按兜底表处理）", profile_code, exc_info=True)
        return [], None
    model = resolved.get("model")
    provider = resolved.get("provider")
    capabilities = [c.strip() for c in (getattr(model, "capabilities", None) or "").lower().split(",") if c.strip()]
    return capabilities, getattr(provider, "adapter", None)


# --- 渲染 / 拼接工具 ---


def _kind_label(entity: Any) -> str:
    return _KIND_LABELS.get(type(entity).__name__, "资产卡")


def _render_variables(template: str, variables: dict[str, str], label: str, name: str) -> str:
    """{{变量}} 渲染（资产片段内生效）；缺失 fail-fast 定位资产与变量名（验收 7）。

    注意：不复用 workflow expressions.render_template——那是单括号 {var} 语法且缺失返空串，
    与资产变量的双括号语法、fail-fast 语义均不同源（设计 3.4 步骤 2）。
    """

    def _sub(match: re.Match) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None or str(value) == "":
            raise AssetVariableMissingError(f"{label}「{name}」的变量「{key}」未提供")
        return str(value)

    return ASSET_VAR_PATTERN.sub(_sub, template)


def _split_identity_core(template: str) -> str:
    """身份核心句 = 模板去除占位后的静态文本（压缩下界，决策 #35）。"""
    core = ASSET_VAR_PATTERN.sub("", template)
    parts = [part.strip(" ,，;；") for part in core.split(",")]
    return ", ".join(part for part in parts if part)


def _merge_negative(*sources: str) -> list[tuple[str, str]]:
    """负面四源去重（大小写不敏感精确匹配，保序留首现，决策 #33）。

    返回 [(origin, text)]，origin ∈ style/scene/character/global。
    """
    origins = ("style", "scene", "character", "global")
    seen: set[str] = set()
    merged: list[tuple[str, str]] = []
    for origin, raw in zip(origins, sources):
        for piece in (raw or "").split("\n"):
            text = piece.strip()
            if not text:
                continue
            folded = text.casefold()
            if folded in seen:
                continue
            seen.add(folded)
            merged.append((origin, text))
    return merged


# --- 参考图解析（决策表 #28/#32 + D6 合并注入）---


def _resolve_references(
    session,
    input: ComposeInput,
    capabilities: list[str],
    adapter_type: str | None,
    params: dict[str, str],
    warnings: list[ComposerWarning],
):
    from app.modules.asset.service.reference import normalize_entry_ids, parse_ref_entries
    from app.modules.media.model.media import MediaAsset

    entities = {
        "character": input.character,
        "style": input.style,
        "scene": input.scene,
    }
    ordered_entries: list[dict] = []
    for kind in _ASSET_REF_ORDER:
        entity = entities.get(kind)
        if entity is None or not entity.ref_image_ids:
            continue
        ordered_entries.extend(parse_ref_entries(entity.ref_image_ids))
    # 跨资产去重（同一 media 被多个资产引用时保留首现）
    seen_ids: set[int] = set()
    unique_entries = [entry for entry in ordered_entries if not (entry["id"] in seen_ids or seen_ids.add(entry["id"]))]
    ordered_ids = normalize_entry_ids(unique_entries)

    available: dict[int, MediaAsset] = {}
    if ordered_ids:
        rows = session.exec(
            select(MediaAsset).where(
                MediaAsset.id.in_(ordered_ids),
                MediaAsset.delete_time == None,  # noqa: E711
            )
        ).all()
        available = {row.id: row for row in rows}

    candidates: list[str] = []
    reference_segments: list[dict[str, Any]] = []
    role_by_id = {entry["id"]: entry.get("role") for entry in unique_entries}
    for mid in ordered_ids:
        media = available.get(mid)
        if media is None:
            reference_segments.append(
                {"mediaId": mid, "role": role_by_id.get(mid), "included": False, "skipReason": "missing"}
            )
            _warn(warnings, "REF_IMAGE_MISSING", f"参考图 #{mid} 已不存在，已跳过")
        elif media.status != "success" or not (media.remote_url or media.storage_url):
            reference_segments.append(
                {
                    "mediaId": mid,
                    "role": role_by_id.get(mid),
                    "included": False,
                    "skipReason": f"status:{media.status}" if media.status != "success" else "no_url",
                }
            )
            _warn(warnings, "REF_IMAGE_SKIPPED", f"参考图「{media.file_name or f'#{mid}'}」状态异常，已跳过")
        else:
            url = media.remote_url or media.storage_url or ""
            candidates.append(url)
            reference_segments.append({"mediaId": mid, "role": role_by_id.get(mid), "included": True})

    # 注入张数 = min(全局 N, 渠道能力上限)；primary 排序已在 normalize（决策 #28）
    global_n = max(0, _int_param(params, PARAM_DEFAULT_REF_IMAGES, 1))
    if "multi_reference_image" in capabilities:
        channel_limit: int | None = global_n
    else:
        declared_limit = ADAPTER_REFERENCE_LIMITS.get(adapter_type or "", 1)
        channel_limit = global_n if declared_limit is None else min(global_n, declared_limit)
    total_limit = min(global_n, channel_limit) if channel_limit is not None else global_n

    asset_selected = candidates[:total_limit]
    if len(candidates) > len(asset_selected):
        _warn(
            warnings,
            "MULTI_REF_TRUNCATED",
            f"参考图按渠道能力截断：可用 {len(candidates)} 张，注入 {len(asset_selected)} 张",
            "info",
        )

    # D6：节点显式图在后，剩余配额补足，超限先裁节点图
    remaining = total_limit - len(asset_selected)
    extras = list(input.extra_reference_images or [])
    extra_selected = extras[: max(0, remaining)]
    if len(extras) > len(extra_selected):
        _warn(
            warnings,
            "MULTI_REF_TRUNCATED",
            f"节点显式参考图超渠道配额，已截断 {len(extras) - len(extra_selected)} 张",
            "info",
        )

    # 最低锚定数（决策 #32）：0=降级不阻断（error 日志+实例标注）；≥1 低于下限报错
    min_anchor = _int_param(params, PARAM_MIN_ANCHOR, 0)
    if len(candidates) < min_anchor:
        raise AssetAnchorError(
            f"可用参考图 {len(candidates)} 张，低于最低锚定数 {min_anchor}，已阻止生成（隐性身份丢失视为失败）"
        )
    if ordered_ids and not candidates:
        logger.error(
            "资产参考图全部失效，降级为无图生成（min_anchor=%s）",
            min_anchor,
            extra={"assetCharacterId": input.character.id if input.character else None},
        )

    images = asset_selected + extra_selected
    resolved = resolve_image_input_value(images) if images else []
    if isinstance(resolved, str):  # 防御：调度器对单值返回 str（入参恒为 list，理论不触）
        resolved = [resolved]
    return resolved, reference_segments


# --- 预算压缩（决策 #31）---

_POSITIVE_COMPRESSION = (
    ("style", "STYLE_DROPPED", "字符预算超限，已省略风格片段"),
    ("scene", "SCENE_DROPPED", "字符预算超限，已省略场景片段"),
)
_NEGATIVE_COMPRESSION = (
    ("style", "NEGATIVE_STYLE_DROPPED", "字符预算超限，已省略风格负面词"),
    ("scene", "NEGATIVE_SCENE_DROPPED", "字符预算超限，已省略场景负面词"),
    ("global", "NEGATIVE_GLOBAL_DROPPED", "字符预算超限，已省略全局负面词"),
    ("character", "NEGATIVE_CHARACTER_DROPPED", "字符预算超限，已省略角色负面词"),
)


def _apply_budget(
    positive: list[list[Any]], negative_list: list[tuple[str, str]], budget: int, warnings: list[ComposerWarning]
):
    """正向+负面共享总预算（D4）；压缩序见设计附录 B.4；身份核心句与正文永不压缩。"""
    pos_included = {source: True for source, _text, _core in positive}
    neg_included = {origin: True for origin, _text in negative_list}

    def build() -> tuple[str, str]:
        prompt = "\n".join(text for source, text, _core in positive if pos_included[source] and text)
        negative = "\n".join(text for origin, text in negative_list if neg_included[origin] and text)
        return prompt, negative

    prompt, negative = build()
    if len(prompt) + len(negative) <= budget:
        return prompt, negative, pos_included, neg_included

    # 正向：风格 → 场景（整段丢弃）
    for source, code, message in _POSITIVE_COMPRESSION:
        if pos_included.get(source):
            pos_included[source] = False
            _warn(warnings, code, message)
            prompt, negative = build()
            if len(prompt) + len(negative) <= budget:
                return prompt, negative, pos_included, neg_included

    # 角色：剔除变量渲染值，退回身份核心句（核心句永不压缩的下界即在此落地）
    for index, (source, _text, core) in enumerate(positive):
        if source == "character" and pos_included[source] and core:
            positive[index][1] = core
            _warn(warnings, "CHARACTER_VARS_DROPPED", "字符预算超限，已省略角色外观变量（身份核心句保留）")
            prompt, negative = build()
            if len(prompt) + len(negative) <= budget:
                return prompt, negative, pos_included, neg_included

    # 负面：风格 → 场景 → 全局 → 角色（角色负面最保）
    for origin, code, message in _NEGATIVE_COMPRESSION:
        if neg_included.get(origin):
            neg_included[origin] = False
            _warn(warnings, code, message)
            prompt, negative = build()
            if len(prompt) + len(negative) <= budget:
                return prompt, negative, pos_included, neg_included

    raise AssetPromptBudgetError(
        f"组装结果超出字符预算（{budget}）且无可再压缩内容，请缩短正文后重试（正文不做静默截断）"
    )


def _warn(warnings: list[ComposerWarning], code: str, message: str, level: str = "warning") -> None:
    warnings.append(ComposerWarning(code=code, message=message, level=level))


# --- 组装入口 ---


def compose(session, input: ComposeInput) -> ComposeResult:
    """七步流水线。入参为已加载实体（加载与 id 寻址见 fetch_validated），自身做状态校验。"""
    warnings: list[ComposerWarning] = []
    params = read_asset_params(session)

    # 步骤 1：状态校验（draft 归属 / 软删 fail-fast / archived 放行 + warning）
    for entity in (input.style, input.scene, input.character):
        if entity is None:
            continue
        label = _kind_label(entity)
        if entity.delete_time is not None:
            raise AssetNotFoundError(f"{label}「{entity.name}」已被删除")
        if entity.status == ASSET_STATUS_DRAFT and entity.created_by != input.current_user_id:
            raise AssetStateError(f"{label}「{entity.name}」为草稿，仅创建者可试生成")
        if entity.status == ASSET_STATUS_ARCHIVED:
            _warn(warnings, "ASSET_ARCHIVED_REF", f"{label}「{entity.name}」已归档（存量引用放行）", "info")

    # 步骤 2：变量渲染（先渲染后拼接，保证错误定位与预览一致）
    rendered: dict[str, str] = {}
    cores: dict[str, str] = {}
    for kind, entity in (("style", input.style), ("scene", input.scene), ("character", input.character)):
        template = (entity.appearance_prompt or "") if entity is not None else ""
        if not template.strip():
            continue
        rendered[kind] = _render_variables(template, input.variables, _kind_label(entity), entity.name)
        cores[kind] = _split_identity_core(template)

    # 步骤 3：正向四段拼接（风格→场景→角色→正文；空段跳过，换行分隔）
    positive: list[list[Any]] = [
        ["style", rendered.get("style", ""), cores.get("style", "")],
        ["scene", rendered.get("scene", ""), cores.get("scene", "")],
        ["character", rendered.get("character", ""), cores.get("character", "")],
        ["user", (input.user_prompt or "").strip(), (input.user_prompt or "").strip()],
    ]

    # 步骤 4：负面四源去重（风格→场景→角色→全局）
    negative_list = _merge_negative(
        (input.style.negative_prompt or "") if input.style else "",
        (input.scene.negative_prompt or "") if input.scene else "",
        (input.character.negative_prompt or "") if input.character else "",
        params.get(PARAM_GLOBAL_NEGATIVE, ""),
    )

    # 步骤 5：字符预算压缩
    prompt, negative_prompt, pos_included, neg_included = _apply_budget(
        positive, negative_list, _int_param(params, PARAM_CHAR_BUDGET, 2000), warnings
    )

    # 步骤 6：参考图解析与注入（渠道自适应 + 悬空决策表 + D6 合并）
    capabilities, adapter_type = _resolve_channel(session, input.profile_code)
    reference_images, reference_segments = _resolve_references(
        session, input, capabilities, adapter_type, params, warnings
    )

    # size 判定（P0-1：用户覆盖最高优先；推荐参数来源按 风格→角色→场景）
    effective_size, size_warnings = _resolve_size(input)
    warnings.extend(size_warnings)

    # 步骤 7：指纹与收口（P1-3：版本参与 hash 输入，升版即换指纹）
    digest = hashlib.sha256(f"{COMPOSER_VERSION}\x1f{prompt}\x1f{negative_prompt}".encode()).hexdigest()[:32]
    asset_refs: dict[str, int] = {}
    for kind, key in (("character", "characterId"), ("scene", "sceneId"), ("style", "styleId")):
        entity = getattr(input, kind)
        if entity is not None and entity.id is not None:
            asset_refs[key] = entity.id

    segments = [
        {"source": source, "text": text, "included": bool(pos_included[source] and text)}
        for source, text, _core in positive
    ]
    return ComposeResult(
        prompt=prompt,
        negative_prompt=negative_prompt,
        reference_images=reference_images,
        effective_size=effective_size,
        warnings=warnings,
        composed_prompt_hash=digest,
        composer_version=COMPOSER_VERSION,
        segments=segments,
        reference_segments=reference_segments,
        asset_refs=asset_refs,
    )


def _resolve_size(input: ComposeInput) -> tuple[str | None, list[ComposerWarning]]:
    """size 判定（设计附录 B.3）：用户覆盖最高优先；渠道不匹配才 SIZE_IGNORED。"""
    warnings: list[ComposerWarning] = []
    source = next(
        (
            getattr(input, kind)
            for kind in _PREFERRED_ORDER
            if getattr(input, kind) is not None and getattr(input, kind).preferred_profile_code
        ),
        None,
    )
    if source is None:
        return (input.user_size or None), warnings

    if input.profile_code is None:
        # 未选 profile：不做比对、preferred_size 不生效
        return (input.user_size or None), warnings

    if input.profile_code == source.preferred_profile_code:
        return (input.user_size or source.preferred_size or None), warnings

    label = _kind_label(source)
    _warn(warnings, "PROFILE_MISMATCH", f"当前 profile 与{label}「{source.name}」的推荐 profile 不一致")
    if input.user_size:
        return input.user_size, warnings
    if source.preferred_size:
        _warn(
            warnings,
            "SIZE_IGNORED",
            f"{label}「{source.name}」的推荐尺寸 {source.preferred_size} 仅在推荐渠道生效，已忽略",
        )
    return None, warnings


def compose_for_node(
    config: dict,
    variables: dict,
    profile_code: str | None,
    node_image: str | list[str] | None = None,
    user_prompt: str = "",
    *,
    session: Session | None = None,
) -> ComposeResult:
    """工作流生图节点专用入口（设计 4.3）：读 config 三键 → 短会话加载资产 → compose()。

    短会话纪律（流式 SSE 专项教训）：生产路径（session 未传）用全局 engine 建独立
    短会话，勿复用请求级 session；测试可注入局部会话。执行期无用户语境
    （current_user_id=0）：draft 引用因归属不匹配 fail-fast（权限矩阵
    「工作流执行期」行，验收 4）。
    """
    from app.modules.asset.model.asset import AssetCharacter, AssetScene, AssetStyle

    node_images = [node_image] if isinstance(node_image, str) else list(node_image or [])
    own_session = session is None
    if own_session:
        from app.core.database import engine

        session = Session(engine)
    try:
        input_ = ComposeInput(
            character=session.get(AssetCharacter, cid) if (cid := _config_get(config, "characterId")) else None,
            scene=session.get(AssetScene, sid) if (sid := _config_get(config, "sceneId")) else None,
            style=session.get(AssetStyle, stid) if (stid := _config_get(config, "styleId")) else None,
            user_prompt=user_prompt,
            variables=variables or {},
            current_user_id=0,
            profile_code=profile_code,
            extra_reference_images=node_images,
        )
        return compose(session, input_)
    finally:
        if own_session:
            session.close()


def fetch_validated(session, model, asset_id: int) -> Any:
    """按 id 加载资产（preview 端点 / 节点执行器寻址入口；软删/归属校验在 compose 内执行）。"""
    entity = session.get(model, asset_id)
    if entity is None:
        raise AssetNotFoundError(f"{_KIND_LABELS.get(model.__name__, '资产卡')}不存在（id={asset_id}）")
    return entity
