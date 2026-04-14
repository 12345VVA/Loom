import sys
import os
sys.path.append(os.getcwd())
try:
    from app.modules.base.model.auth import CoolUserInfo
    print("Success: Imported CoolUserInfo")
    from app.modules.base.controller.admin.user import BaseUserController
    print("Success: Imported BaseUserController")
except Exception as e:
    import traceback
    traceback.print_exc()
