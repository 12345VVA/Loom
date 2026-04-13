"""
Task 模块菜单清单
"""
from app.modules.module_config import MenuManifestItem


MENU_ITEMS = (
    MenuManifestItem(
        code="nav_tasks",
        name="任务列表",
        type="menu",
        module="task",
        resource="task",
        path="/tasks",
        component="modules/task/views/list.vue",
        sort_order=20,
        role_codes=("admin", "task_operator"),
    ),
)


def run(session) -> None:
    _ = session
