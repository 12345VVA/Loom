"""
Base 模块菜单清单
"""
from app.modules.module_config import MenuManifestItem


MENU_ITEMS = (
    MenuManifestItem(
        code="nav_dashboard",
        name="工作台",
        type="menu",
        module="base",
        resource="dashboard",
        path="/base/info",
        component="modules/base/views/info.vue",
        sort_order=10,
        role_codes=("admin", "task_operator"),
    ),
    MenuManifestItem(
        code="nav_system",
        name="系统管理",
        type="group",
        sort_order=30,
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_users",
        name="用户管理",
        type="menu",
        module="base",
        resource="sys/user",
        path="/base/sys/user",
        component="modules/base/views/user/index.vue",
        sort_order=31,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_roles",
        name="角色管理",
        type="menu",
        module="base",
        resource="sys/role",
        path="/base/sys/role",
        component="modules/base/views/role.vue",
        sort_order=32,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_menus",
        name="菜单管理",
        type="menu",
        module="base",
        resource="sys/menu",
        path="/base/sys/menu",
        component="modules/base/views/menu/index.vue",
        sort_order=33,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_params",
        name="参数配置",
        type="menu",
        module="base",
        resource="sys/param",
        path="/base/sys/param",
        component="modules/base/views/param.vue",
        sort_order=34,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_logs",
        name="操作日志",
        type="menu",
        module="base",
        resource="sys/log",
        path="/base/sys/log",
        component="modules/base/views/log.vue",
        sort_order=35,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
    MenuManifestItem(
        code="nav_system_login_logs",
        name="登录日志",
        type="menu",
        module="base",
        resource="sys/login_log",
        path="/base/sys/login_log",
        component="modules/base/views/login_log.vue",
        sort_order=36,
        parent_code="nav_system",
        role_codes=("admin",),
    ),
)


def run(session) -> None:
    _ = session
