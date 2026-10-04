"""EPS 契约基线导出与校验（G5/M2）。

后端接口面（路由/入参模型/列元数据/OpenAPI schema）的规范化快照，作为 CI 门禁基线：
- 生成/更新：python scripts/dump_eps.py
- 校验（CI 用）：python scripts/dump_eps.py --check，不一致退出码 1

与 frontend/build/cool/eps.json 的关系：后者是 vite-plugin 对本导出做二次变换后
的产物（字段裁剪 + search 派生），Python 侧不复刻其字节格式——基线走 sort_keys
规范化对比，语义等价。接口面变更时的操作顺序：
  1. 启动 dev server 重新生成 frontend/build/cool/eps.d.ts（与 eps.json）
  2. python scripts/dump_eps.py 更新本基线
  3. 三者一并提交
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from main import app  # noqa: E402  导入即完成模块装载与路由注册（lifespan 不执行）
from app.modules.base.service.eps_service import EpsService  # noqa: E402

BASELINE_PATH = BACKEND_ROOT / "eps_baseline.json"


def render(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def main() -> int:
    data = EpsService(app).export_admin()
    entity_count = sum(len(v) for v in data.values())

    if "--check" in sys.argv:
        if not BASELINE_PATH.exists():
            print(f"FAIL: 基线不存在，请运行 python scripts/dump_eps.py 生成: {BASELINE_PATH}")
            return 1
        if BASELINE_PATH.read_text(encoding="utf-8") != render(data):
            print("FAIL: EPS 导出与基线不一致——后端接口面已变更。")
            print("处理：① dev server 重新生成 frontend/build/cool/eps.d.ts；")
            print("      ② python scripts/dump_eps.py 更新基线；③ 一并提交。")
            return 1
        print(f"OK: EPS 契约基线一致（{entity_count} 个实体）")
        return 0

    BASELINE_PATH.write_text(render(data), encoding="utf-8", newline="\n")
    print(f"EPS 基线已写入 {BASELINE_PATH}（{entity_count} 个实体）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
