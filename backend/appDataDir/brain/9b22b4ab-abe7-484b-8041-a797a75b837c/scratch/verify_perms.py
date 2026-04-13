import os
import sys

# Add the project root to sys.path
sys.path.append(os.getcwd())

from app.modules.loader import load_permission_configs

# Force import controllers to trigger registration
import app.modules.base.controller.admin.menu
import app.modules.base.controller.admin.role
import app.modules.base.controller.admin.user
import app.modules.task.controller.admin.task
import app.modules.base.controller.admin.sys.dict
import app.modules.base.controller.admin.sys.dict_data

configs = load_permission_configs()
perms = sorted([p.permission for p in configs])

print("\n".join(perms))
