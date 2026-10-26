"""工具 SPI 注册表：分布式收集 + 允许列表封闭 + 资源层同步 + 契约兼容/执行安全两套判定。

设计基线：docs/02-业务模块/智能体模块设计-2026-10-23.md 3.3（v1.5 设计冻结）。
- 收集机制（评审 11）：应用启动时扫描 ``app/modules/*/service/agent_tools.py``，结构校验 +
  全局 name 冲突 fail-fast → build-then-swap 原子替换；失败保留最近有效注册表并标记 degraded；
- 首版封闭清单（D11 + 评审 v1.4）：``RUNTIME_ALLOWED_TOOLS`` 代码级允许列表强制——不在列表内
  的工具不进注册表、不进资源层（封闭性由代码规则强制，不依赖「当前注册的恰好只有这些」）；
- 资源层同步（评审 10）：sync 只更新系统维护字段，**绝不触碰 status**（管理员紧急禁用
  不因代码刷新被意外恢复，D14）；refresh 端点仅做资源层 sync，不重建执行注册表；
- 两套独立判断（评审 v1.4）：
  * 契约兼容性（is_contract_compatible）：快照冻结 schema vs 当前代码 schema 递归判定，
    fail-close——未识别约束默认不兼容；
  * 执行安全性（assert_execution_allowed）：实时判定 level 升级/启停/绑定/允许列表，
    level 升级即使 schema 不变也拒绝。
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.modules.agent.model.agent import (
    AGENT_TOOL_CHANGE_BOTH,
    AGENT_TOOL_CHANGE_CONTRACT,
    AGENT_TOOL_CHANGE_CREATED,
    AGENT_TOOL_CHANGE_META,
    AGENT_TOOL_LEVEL_DANGEROUS_WRITE,
    AGENT_TOOL_LEVEL_READONLY,
    AGENT_TOOL_LEVEL_REVERSIBLE_WRITE,
    AGENT_TOOL_LEVELS,
    AGENT_TOOL_SOURCE_BUILTIN,
    AgentToolResource,
    AgentToolResourceVersion,
)

logger = logging.getLogger("agent.tool_registry")

# --- 首版封闭清单（D11，全部 readonly；扩展新工具须修改此列表并过评审）---

RUNTIME_ALLOWED_TOOLS = {
    "query_asset",  # asset：按标识查询 IP 资产（调用者可见性过滤）
    "search_media",  # media：关键词搜索媒体库
    "list_workflow_definitions",  # workflow：列出已发布工作流定义
    "system_info",  # agent 内置
    "current_time",  # agent 内置
    # E3 可逆写首批（D11 二级；each 声明须带 safety 机制表，reversible_write 不走审批）
    "create_asset_draft",  # asset：创建角色/场景/物件草稿（默认 draft 态，可软删）
    "update_asset_draft",  # asset：编辑本人 draft 态资产字段（published 拒绝）
    "rename_media",  # media：重命名媒体文件（expected_updated_at 乐观比对）
    "tag_media",  # media：追加媒体标签（追加去重，expected_updated_at 乐观比对）
}

# 工具声明结构校验必需键（module 由收集器注入，声明方可不写）
_REQUIRED_KEYS = ("name", "description", "level", "args_model", "func")
# E3 安全机制表必需键（reversible_write 必须声明——逐项防线替代人工审批）
_SAFETY_REQUIRED_KEYS = ("reversible_how", "concurrency", "audit_ref")

# level 风险序（执行安全判定：当前代码 level 高于快照 level = 升级，拒绝执行）
_LEVEL_ORDER = {
    AGENT_TOOL_LEVEL_READONLY: 0,
    AGENT_TOOL_LEVEL_REVERSIBLE_WRITE: 1,
    AGENT_TOOL_LEVEL_DANGEROUS_WRITE: 2,
}

# 契约兼容性判定的约束键分类（fail-close：current 新增未识别约束 → 不兼容）
# title：pydantic schema 自带展示元数据，手写快照可省——语义无影响
_COMPAT_IGNORED_KEYS = {"description", "default", "title"}  # 语义无影响
# 可放宽键：current 约束 ≥ snapshot（更宽松）则兼容，收紧则不兼容
_COMPAT_RELAXABLE_KEYS = {"enum", "minimum", "maximum"}
# 结构递归键
_COMPAT_STRUCT_KEYS = {"type", "properties", "required", "items"}


@dataclass(frozen=True)
class RegisteredTool:
    """注册表条目：一次声明的不可变视图。"""

    name: str
    description: str
    level: str
    args_model: type[BaseModel]
    func: Callable[[Any, Any], str]
    module: str
    safety: dict | None = None  # E3 安全机制表（reversible_write 必填；只读工具为 None）

    @property
    def parameters(self) -> dict:
        """JSON schema（经 pydantic 生成；进 LLM bind_tools 与资源层 schema_summary）。"""
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return schema


# --- 注册表状态（进程内；代码静态，各 worker import 同源无漂移）---

_registry: dict[str, RegisteredTool] = {}
_degraded_error: str | None = None


def get_registry() -> dict[str, RegisteredTool]:
    return dict(_registry)


def get_tool(name: str) -> RegisteredTool | None:
    return _registry.get(name)


def get_tool_safety(name: str) -> dict | None:
    """E3：写工具的安全机制表（发布校验消费；只读/未注册返回 None）。"""
    tool = _registry.get(name)
    return tool.safety if tool is not None else None


def degraded_error() -> str | None:
    """None = 正常；否则为启动/收集失败原因（Agent 功能 degraded，run 拒绝执行）。"""
    return _degraded_error


def registry_status() -> dict:
    """管理面状态（tool.list / registryStatus 消费）。"""
    return {
        "degraded": _degraded_error is not None,
        "error": _degraded_error,
        "toolCount": len(_registry),
        "tools": sorted(_registry.keys()),
    }


# --- 收集（结构校验 + 冲突 fail-fast + 允许列表过滤）---


def _default_module_dirs() -> list[Path]:
    modules_dir = Path(__file__).resolve().parents[2]  # app/modules
    return sorted(p for p in modules_dir.iterdir() if (p / "service" / "agent_tools.py").is_file())


def _validate_entry(entry: Any, module: str) -> RegisteredTool:
    """结构校验：五键全备 + 类型合法。缺项/非法即 raise（启动期暴露）。"""
    if not isinstance(entry, dict):
        raise TypeError(f"[{module}] 工具声明必须是 dict，得到 {type(entry).__name__}")
    missing = [k for k in _REQUIRED_KEYS if k not in entry]
    if missing:
        raise KeyError(f"[{module}] 工具声明缺少必需键: {missing}")
    name = entry["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"[{module}] 工具 name 必须为非空字符串")
    if entry["level"] not in AGENT_TOOL_LEVELS:
        raise ValueError(f"[{module}] 工具 {name} 的 level 非法: {entry['level']!r}（必填，三级枚举）")
    if not (isinstance(entry["args_model"], type) and issubclass(entry["args_model"], BaseModel)):
        raise TypeError(f"[{module}] 工具 {name} 的 args_model 必须是 pydantic BaseModel 子类")
    if not callable(entry["func"]):
        raise TypeError(f"[{module}] 工具 {name} 的 func 必须可调用")
    safety = entry.get("safety")
    if entry["level"] == AGENT_TOOL_LEVEL_REVERSIBLE_WRITE:
        # E3 逐项安全机制表：可逆写必须声明（收集期 fail-fast，发布校验复查）
        if not isinstance(safety, dict):
            raise ValueError(f"[{module}] 可逆写工具 {name} 必须声明 safety 安全机制表")
        missing = [k for k in _SAFETY_REQUIRED_KEYS if k not in safety]
        if missing:
            raise ValueError(f"[{module}] 可逆写工具 {name} 的 safety 缺少必需键: {missing}")
    elif safety is not None and not isinstance(safety, dict):
        raise TypeError(f"[{module}] 工具 {name} 的 safety 必须是 dict")
    return RegisteredTool(
        name=name,
        description=str(entry["description"]),
        level=entry["level"],
        args_model=entry["args_model"],
        func=entry["func"],
        module=module,
        safety=safety if isinstance(safety, dict) else None,
    )


def collect_agent_tools(
    module_dirs: list[Path] | None = None,
    *,
    package_prefix: str = "app.modules",
) -> dict[str, RegisteredTool]:
    """扫描各模块 service/agent_tools.py 并构建新注册表（构建不替换，替换由 bootstrap_registry 做）。

    允许列表外的声明**跳过并记日志**（不报错——长覆盖目标分批落地的正常路径）；
    冲突/结构错误 raise，由调用方决定 degraded 处置。
    package_prefix 供测试注入临时模块目录（模块名 = 目录名）。
    """
    dirs = module_dirs if module_dirs is not None else _default_module_dirs()
    collected: dict[str, RegisteredTool] = {}
    for module_dir in dirs:
        module_name = module_dir.name
        tool_file = module_dir / "service" / "agent_tools.py"
        if not tool_file.is_file():
            continue
        dotted = ".".join(filter(None, (package_prefix, module_name, "service", "agent_tools")))
        mod = importlib.import_module(dotted)
        getter = getattr(mod, "get_agent_tools", None)
        if not callable(getter):
            raise TypeError(f"[{module_name}] agent_tools.py 必须暴露 get_agent_tools()")
        for entry in getter():
            tool = _validate_entry(entry, module_name)
            if tool.name in collected:
                raise ValueError(f"工具名冲突：{tool.name} 同时由 {collected[tool.name].module} 与 {module_name} 声明")
            if tool.name not in RUNTIME_ALLOWED_TOOLS:
                logger.info("工具 %s（%s）不在 RUNTIME_ALLOWED_TOOLS 允许列表内，跳过注册", tool.name, module_name)
                continue
            collected[tool.name] = tool
    return collected


def bootstrap_registry(
    module_dirs: list[Path] | None = None,
    *,
    package_prefix: str = "app.modules",
) -> None:
    """启动时收集 + build-then-swap：成功原子替换并清除 degraded；失败保留旧表并标记 degraded。"""
    global _registry, _degraded_error
    try:
        collected = collect_agent_tools(module_dirs, package_prefix=package_prefix)
    except Exception as exc:  # noqa: BLE001 —— 启动期兜底：失败不阻断全站（设计 3.3）
        _degraded_error = f"工具收集失败（保留{'旧' if _registry else '空'}注册表）: {exc}"
        logger.error("agent 工具收集失败，Agent 功能 degraded：%s", exc)
        return
    _registry = collected
    _degraded_error = None
    logger.info("agent 工具注册表构建完成：%s", sorted(_registry.keys()))


# --- 资源层同步（绝不触碰 status）---


def metadata_hash_of(description: str, parameters: dict, level: str) -> str:
    source = description + json.dumps(parameters, sort_keys=True, ensure_ascii=False) + level
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def contract_hash_of(parameters: dict, level: str) -> str:
    """契约哈希（E12）：parameters + level——兼容判定与「已过期提示」只看它。"""
    source = json.dumps(parameters, sort_keys=True, ensure_ascii=False) + level
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def meta_hash_of(description: str) -> str:
    """元数据哈希（E12）：description（展示元数据）——变更仅入版本，不影响兼容判定。"""
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def _append_version_row(
    session: Session,
    *,
    tool_name: str,
    change_kind: str,
    contract_hash: str,
    meta_hash: str,
    level: str,
    description: str | None,
    schema_summary: str | None,
    operator_id: int | None,
) -> None:
    """版本表只增不改（E12）：version = 活跃行最大值 + 1，行内存变更时点完整形态。"""
    last = session.exec(
        select(AgentToolResourceVersion.version)
        .where(
            AgentToolResourceVersion.tool_name == tool_name,
            AgentToolResourceVersion.delete_time == None,  # noqa: E711
        )
        .order_by(AgentToolResourceVersion.version.desc())  # type: ignore[attr-defined]
        .limit(1)
    ).first()
    session.add(
        AgentToolResourceVersion(
            tool_name=tool_name,
            version=(last or 0) + 1,
            change_kind=change_kind,
            contract_hash=contract_hash,
            meta_hash=meta_hash,
            level=level,
            description=description,
            schema_summary=schema_summary,
            created_by=operator_id,
        )
    )


def sync_resources(session: Session, operator_id: int | None = None) -> dict:
    """注册表 → agent_tool_resource upsert + 版本表入册（E12 双哈希分类）。

    只更新系统维护字段（display_name/description/category/schema_summary/level/哈希列/
    source_type），**绝不触碰 status**；新建工具默认启用。refresh 端点复用本函数（不重建注册表）。

    版本入册规则（二批 3.13）：
    - 新工具 / 存量行当前值列为 NULL（迁移 0032 前的旧行首次入体系）→ v1 change_kind=created；
    - contract_hash 或 meta_hash 相对当前值列变化 → 按分类入新版本行（both/contract_change/
      meta_change），当前值列同步维护；
    - 双哈希均未变 → 不入版本（无变更空转）；兼容判定只看 contract_hash（meta 变更不触发）。
    """
    synced = []
    for name in sorted(_registry.keys()):
        tool = _registry[name]
        parameters = tool.parameters
        row = session.exec(
            select(AgentToolResource).where(
                AgentToolResource.tool_name == name,
                AgentToolResource.delete_time == None,  # noqa: E711
            )
        ).first()
        schema_summary = json.dumps(parameters, ensure_ascii=False)
        contract_hash = contract_hash_of(parameters, tool.level)
        meta_hash = meta_hash_of(tool.description)
        combined = metadata_hash_of(tool.description, parameters, tool.level)
        # E3：安全机制表并入 prompt_metadata_json（管理面可见；只读工具保持 None 不动既有值）
        safety_metadata = json.dumps({"safety": tool.safety}, ensure_ascii=False) if tool.safety else None
        version_added = None
        if row is None:
            row = AgentToolResource(
                tool_name=name,
                display_name=name,
                description=tool.description,
                source_type=AGENT_TOOL_SOURCE_BUILTIN,
                level=tool.level,
                status=True,  # 新建默认启用（D14：管理员随后可显式禁用）
                schema_summary=schema_summary,
                prompt_metadata_json=safety_metadata,
                metadata_hash=combined,
                contract_hash=contract_hash,
                meta_hash=meta_hash,
                created_by=operator_id,
                updated_by=operator_id,
            )
            session.add(row)
            _append_version_row(
                session,
                tool_name=name,
                change_kind=AGENT_TOOL_CHANGE_CREATED,
                contract_hash=contract_hash,
                meta_hash=meta_hash,
                level=tool.level,
                description=tool.description,
                schema_summary=schema_summary,
                operator_id=operator_id,
            )
            version_added = AGENT_TOOL_CHANGE_CREATED
            synced.append((name, "created"))
        else:
            row.display_name = row.display_name or name
            row.description = tool.description
            row.source_type = AGENT_TOOL_SOURCE_BUILTIN
            row.level = tool.level
            row.schema_summary = schema_summary
            if safety_metadata is not None or tool.level == AGENT_TOOL_LEVEL_READONLY:
                row.prompt_metadata_json = safety_metadata  # 写工具同步机制表；只读不覆盖管理员/历史值
            row.metadata_hash = combined
            row.updated_by = operator_id
            uninitialized = row.contract_hash is None or row.meta_hash is None
            if uninitialized:
                change_kind = AGENT_TOOL_CHANGE_CREATED  # 旧行首次入版本体系（视为 v1 基线）
            else:
                contract_changed = row.contract_hash != contract_hash
                meta_changed = row.meta_hash != meta_hash
                if contract_changed and meta_changed:
                    change_kind = AGENT_TOOL_CHANGE_BOTH
                elif contract_changed:
                    change_kind = AGENT_TOOL_CHANGE_CONTRACT
                elif meta_changed:
                    change_kind = AGENT_TOOL_CHANGE_META
                else:
                    change_kind = None  # 无变更：不入版本（防空转版本线，对齐发布幂等纪律）
            if change_kind is not None:
                _append_version_row(
                    session,
                    tool_name=name,
                    change_kind=change_kind,
                    contract_hash=contract_hash,
                    meta_hash=meta_hash,
                    level=tool.level,
                    description=tool.description,
                    schema_summary=schema_summary,
                    operator_id=operator_id,
                )
                version_added = change_kind
            row.contract_hash = contract_hash
            row.meta_hash = meta_hash
            session.add(row)
            synced.append((name, "updated"))
        if version_added is not None:
            logger.info("工具 %s 资源版本入册：%s", name, version_added)
    session.commit()
    return {"synced": synced, "count": len(synced)}


# --- 契约兼容性（fail-close，递归）---


def is_contract_compatible(snapshot_params: dict, current_params: dict) -> bool:
    """快照冻结的参数 schema 是否仍被当前代码 schema 接受（旧调用形式仍有效才判兼容）。

    规则（设计 3.3，评审 v1.4）：
    - required 集合不得扩大；snapshot 的每个属性必须在 current 中存在且 type 一致（递归）；
    - 可放宽键（enum/minimum/maximum）收紧 → 不兼容；current 新增约束键（未识别）→ 不兼容；
    - current 新增可选属性 → 兼容。
    """
    return _params_compatible(snapshot_params or {}, current_params or {})


def _params_compatible(snap: dict, cur: dict) -> bool:
    if not isinstance(snap, dict) or not isinstance(cur, dict):
        return snap == cur
    # required 不得扩大
    if set(cur.get("required") or []) - set(snap.get("required") or []):
        return False
    # current 新增的未识别约束键（snapshot 没有的）→ fail-close
    known = _COMPAT_IGNORED_KEYS | _COMPAT_STRUCT_KEYS | _COMPAT_RELAXABLE_KEYS
    if set(cur.keys()) - set(snap.keys()) - known:
        return False
    # snapshot 属性逐个核对
    snap_props = snap.get("properties") or {}
    cur_props = cur.get("properties") or {}
    if not isinstance(cur_props, dict):
        return False
    for prop_name, snap_prop in snap_props.items():
        if prop_name not in cur_props:
            return False  # 删除属性 → 旧调用形式无法满足
        if not _prop_compatible(snap_prop, cur_props[prop_name]):
            return False
    return True


def _prop_compatible(snap: dict, cur: dict) -> bool:
    if not isinstance(snap, dict) or not isinstance(cur, dict):
        return snap == cur
    # 类型必须一致（含数组 items 递归）
    if snap.get("type") != cur.get("type"):
        return False
    # 对象/数组级通用规则（逐层生效，与顶层同口径）：required 不得扩大；
    # current 新增未识别约束键 → fail-close（设计 3.3：未识别约束默认不兼容）
    if set(cur.get("required") or []) - set(snap.get("required") or []):
        return False
    known = _COMPAT_IGNORED_KEYS | _COMPAT_STRUCT_KEYS | _COMPAT_RELAXABLE_KEYS
    if set(cur.keys()) - set(snap.keys()) - known:
        return False
    # 可放宽键：current 收紧（含新增约束——snap 无约束时任何 current 值都是收紧）→ 不兼容
    for key in _COMPAT_RELAXABLE_KEYS:
        snap_v = snap.get(key)
        cur_v = cur.get(key)
        if cur_v is None:
            continue  # 移除约束 = 放宽 = 兼容
        if snap_v is None:
            return False  # 新增约束 → 旧调用值可能失效
        if key == "enum":
            if not set(snap_v).issubset(set(cur_v)):
                return False  # current 枚举值缩减，旧值可能失效
        elif key == "minimum":
            if float(cur_v) > float(snap_v):
                return False
        elif key == "maximum":
            if float(cur_v) < float(snap_v):
                return False
    # snapshot 属性递归（嵌套对象）
    snap_props = snap.get("properties") or {}
    cur_props = cur.get("properties") or {}
    for prop_name, snap_prop in snap_props.items():
        if prop_name not in cur_props:
            return False
        if not _prop_compatible(snap_prop, cur_props[prop_name]):
            return False
    # 嵌套对象 required / 数组 items
    if "items" in snap and "items" in cur:
        if not _prop_compatible(snap["items"], cur["items"]):
            return False
    return True


# --- 执行安全性（实时判定，独立于契约兼容）---


def assert_execution_allowed(
    tool_name: str,
    *,
    snapshot_level: str | None,
    bound_tool_names: set[str],
    session: Session | None = None,
) -> RegisteredTool:
    """执行前实时安全校验（设计 3.3）：注册在案 + 允许列表 + 绑定 + 资源层启用 + level 未升级。

    任一不过即 403（ToolExecutor 转为该工具的失败 ToolMessage，不中止一轮内其他工具）。
    """
    tool = _registry.get(tool_name)
    if tool is None:
        raise HTTPException(status_code=403, detail=f"工具 {tool_name} 未注册（可能契约已变更，需重新发布智能体）")
    if tool_name not in RUNTIME_ALLOWED_TOOLS:
        raise HTTPException(status_code=403, detail=f"工具 {tool_name} 不在运行时允许列表内")
    if tool_name not in bound_tool_names:
        raise HTTPException(status_code=403, detail=f"工具 {tool_name} 未绑定到当前智能体")
    # level 升级拒绝（readonly → 写操作即使 schema 不变也不得凭 schema 校验通过继续执行）
    if snapshot_level is not None:
        if _LEVEL_ORDER.get(tool.level, 99) > _LEVEL_ORDER.get(snapshot_level, -1):
            raise HTTPException(
                status_code=403,
                detail=f"工具 {tool_name} 风险等级已从 {snapshot_level} 升级为 {tool.level}，需重新发布智能体并通过前置条件",
            )
    # 资源层实时启停（D14：紧急禁用立即生效，覆盖快照）
    if session is not None:
        row = session.exec(
            select(AgentToolResource).where(
                AgentToolResource.tool_name == tool_name,
                AgentToolResource.delete_time == None,  # noqa: E711
            )
        ).first()
        if row is not None and not row.status:
            raise HTTPException(status_code=403, detail=f"工具 {tool_name} 已被管理员禁用")
    return tool
