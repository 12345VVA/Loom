"""修正 ai_model.default_config 里 ToAPIs gpt-image 的尺寸档位。

背景
----
`_sizes` 里声明了 `864x1152 (3:4)`，但上游 ToAPIs gpt-image VIP/Official 版
不兑现任意像素，会按宽高比做档位规范化（2026-09-21 实测：864x1152 -> 768x1024）。
下拉里放一个"填了会变"的值却不加提示，等于持续制造「设了 A 却得到 B」的困惑。

本脚本做三件事（幂等，可重复执行）
1. 把 864x1152 的 label 改成带实测产出的说明
2. 补 1536x2048 / 768x1024 两条实测兑现的档位
3. 其余字段一律不动；非 ToAPIs 像素档位的模型（如 seedream）不受影响

seedream 之所以不动：它确实兑现任意像素（实测请求 1728x2304 原样返回），
864x1152 对它是有效值。

用法
----
    # 扫描，不写任何数据
    python scripts/fix_model_catalog_sizes.py

    # 实际写入（自动备份）
    python scripts/fix_model_catalog_sizes.py --apply

必须从 backend/ 目录运行（需要 import app.*）。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime
from typing import Any

_HERE = pathlib.Path(__file__).resolve()
_BACKEND = _HERE.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

ANNOTATED_864 = {
    "label": "864x1152 (3:4，上游会规范化为 768x1024)",
    "value": "864x1152",
}
REALIZED_ENTRIES = [
    {"label": "1536x2048 (3:4 竖版，实测兑现)", "value": "1536x2048"},
    {"label": "768x1024 (3:4 竖版，实测兑现)", "value": "768x1024"},
]
TARGET_VALUE = "864x1152"


def build_new_sizes(sizes: list[Any]) -> tuple[list[Any], list[str]]:
    """返回 (新 _sizes, 变更说明)。不含 864x1152 的列表原样返回。"""
    values = {entry.get("value") for entry in sizes if isinstance(entry, dict)}
    if TARGET_VALUE not in values:
        return list(sizes), []

    changes: list[str] = []
    result: list[Any] = []
    for entry in sizes:
        if isinstance(entry, dict) and entry.get("value") == TARGET_VALUE:
            if entry.get("label") != ANNOTATED_864["label"]:
                changes.append("864x1152 的 label 改为带实测产出的说明")
            result.append(dict(ANNOTATED_864))
        else:
            result.append(entry)

    existing = {entry.get("value") for entry in result if isinstance(entry, dict)}
    to_add = [entry for entry in REALIZED_ENTRIES if entry["value"] not in existing]
    if to_add:
        anchor = next(
            (i for i, entry in enumerate(result) if isinstance(entry, dict) and entry.get("value") == "1024x1024"),
            None,
        )
        if anchor is None:
            result.extend(to_add)
        else:
            result[anchor + 1 : anchor + 1] = to_add
        changes.append("新增档位 %s" % ", ".join(entry["value"] for entry in to_add))

    return result, changes


def main() -> int:
    ap = argparse.ArgumentParser(description="修正 ai_model 的 ToAPIs 尺寸档位")
    ap.add_argument("--apply", action="store_true", help="实际写入（缺省只扫描）")
    args = ap.parse_args()

    from sqlmodel import select

    from app.core.database import SessionLocal
    from app.modules.ai.model.ai import AiModel

    with SessionLocal() as session:
        models = list(session.exec(select(AiModel).where(AiModel.model_type == "image")).all())

        targets: list[tuple[Any, list[Any], list[str]]] = []
        print("=" * 96)
        print("扫描 ai_model 图像模型 (%d 个)" % len(models))
        print("=" * 96)
        for model in models:
            config = model.default_config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    continue
            if not isinstance(config, dict):
                continue
            sizes = config.get("_sizes")
            if not isinstance(sizes, list):
                continue
            new_sizes, changes = build_new_sizes(sizes)
            if not changes:
                continue
            targets.append((model, new_sizes, changes))
            print("  id=%-3s %-30s" % (model.id, model.code))
            for change in changes:
                print("        - %s" % change)

        if not targets:
            print("无需修改（没有模型的 _sizes 含 864x1152，或已完成标注）。")
            return 0

        print()
        print("涉及模型 %d 个。" % len(targets))
        if not args.apply:
            print()
            print("当前为扫描模式，未写入任何数据。加 --apply 才会执行修复。")
            return 0

        backup_dir = _HERE.parent.parent / "deliverables"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / ("ai-model-default-config-backup-%s.json" % stamp)
        backup_path.write_text(
            json.dumps(
                {
                    str(model.id): {
                        "code": model.code,
                        "default_config": model.default_config,
                    }
                    for model, _, _ in targets
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("已备份原 default_config -> %s (%d bytes)" % (backup_path, backup_path.stat().st_size))
        print()

        for model, new_sizes, _ in targets:
            config = model.default_config
            if isinstance(config, str):
                config = json.loads(config)
            config = dict(config)
            config["_sizes"] = new_sizes
            # default_config 列是 VARCHAR，存 JSON 字符串（直接赋 dict 会 adaptive 失败）
            model.default_config = json.dumps(config, ensure_ascii=False)
            session.add(model)
            print("  id=%-3s %-30s -> _sizes 共 %d 条" % (model.id, model.code, len(new_sizes)))
        session.commit()
        print("已提交。")

        print()
        print("=" * 96)
        print("复检")
        print("=" * 96)
        for model in session.exec(select(AiModel).where(AiModel.model_type == "image")).all():
            config = model.default_config
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    continue
            if not isinstance(config, dict):
                continue
            sizes = config.get("_sizes")
            if not isinstance(sizes, list):
                continue
            if not any(isinstance(e, dict) and e.get("value") == TARGET_VALUE for e in sizes):
                continue
            has_new = all(
                any(isinstance(e, dict) and e.get("value") == entry["value"] for e in sizes)
                for entry in REALIZED_ENTRIES
            )
            annotated = any(
                isinstance(e, dict) and e.get("value") == TARGET_VALUE and e.get("label") == ANNOTATED_864["label"]
                for e in sizes
            )
            print(
                "  id=%-3s %-30s 实测档位=%s 标注=%s"
                % (model.id, model.code, "OK" if has_new else "缺失", "OK" if annotated else "缺失")
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
