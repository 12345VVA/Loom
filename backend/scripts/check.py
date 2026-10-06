"""CI 快门禁本地预演（提交/推送前一键自检）。

backend job 的失败大多集中在链路早期的「秒级」门禁，且前置失败会掩盖后续
pytest 等真问题。本脚本把这些快门禁按 CI 同序串起来，任一失败立即退出：

  1. ruff check .            （CI：Ruff 检查）
  2. ruff format --check .   （同步骤第二条命令——历史上两次只跑 check 漏掉 format）
  3. dump_eps.py --check     （CI：EPS 契约基线校验——改后端接口面必挂的 G5 门禁）

pytest 不默认执行：相关测试的选取是人工判断（见 CLAUDE.md 验证节），全量太慢；
需要时以 --pytest 透传。

用法（任意目录）：
  python scripts/check.py                      # 上述三项，秒级
  python scripts/check.py --pytest tests/test_ai_module.py
  python scripts/check.py --pytest -q          # 追加全量
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]


def run(step: str, cmd: list[str]) -> bool:
    print(f"\n=== {step} ===\n$ {' '.join(cmd)}", flush=True)
    code = subprocess.call(cmd, cwd=BACKEND_ROOT)
    if code != 0:
        print(f"\nFAIL: {step}（退出码 {code}）——修复后重跑本脚本")
        return False
    return True


def main() -> int:
    # sys.executable 保证 ruff/pytest/dump_eps 与当前 venv 一致（CI 同为 pip 安装）
    python = sys.executable
    steps = [
        ("Ruff 静态检查", [python, "-m", "ruff", "check", "."]),
        ("Ruff 格式检查", [python, "-m", "ruff", "format", "--check", "."]),
        ("EPS 契约基线", [python, "scripts/dump_eps.py", "--check"]),
    ]
    for name, cmd in steps:
        if not run(name, cmd):
            return 1

    args = sys.argv[1:]
    if args:
        if args[0] != "--pytest":
            print(f"未知参数: {args[0]}（支持 --pytest [pytest 参数...]）")
            return 2
        if not run("Pytest", [python, "-m", "pytest", *args[1:]]):
            return 1

    print("\nALL GREEN: 本地快门禁全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
