"""IP 资产库模块配置。"""

from sqlmodel import Session, select

from app.framework.middleware.module_access import ModuleAccessMiddleware
from app.modules.module_config import ModuleConfig

MODULE_CONFIG = ModuleConfig(
    name="asset",
    label="IP 资产库",
    description="角色 / 场景 / 风格资产沉淀与组装协议（AssetPromptComposer）",
    order=10,
    scopes=("admin",),
    middlewares=(ModuleAccessMiddleware,),
    config_namespace="ASSET",
    init_db_file="init_db.py",
    init_menu_file="menu.json",
    bootstrap="app.modules.asset.config.bootstrap",
)

# 全局参数种子（设计 3.8；键名对齐 sys_param 既有驼峰短键风格，如 logKeep）
_PARAM_DEFAULTS = (
    ("全局负面词（资产组装第四源）", "assetGlobalNegativePrompt", "", "角色/场景/风格负面词之外的全局负面词"),
    ("参考图默认注入张数", "assetDefaultReferenceImages", "1", "实际注入张数 = min(本值, 渠道能力上限)"),
    ("组装字符预算", "assetPromptCharBudget", "2000", "正向+负面共享总预算；超出按降级序压缩，仍超限报错"),
    ("最低锚定数", "assetMinAnchorImages", "0", "0=参考图全部失效时降级无图生成不阻断；≥1 时低于下限报错"),
)


def bootstrap(session: Session) -> None:
    """幂等写入 asset 全局参数（bootstrap 由模块加载器启动时调用）。"""
    from app.modules.base.model.sys import SysParam

    for name, key, data, remark in _PARAM_DEFAULTS:
        if session.exec(select(SysParam).where(SysParam.key_name == key)).first() is None:
            session.add(SysParam(name=name, key_name=key, data=data, data_type=0, remark=remark))
    session.commit()
