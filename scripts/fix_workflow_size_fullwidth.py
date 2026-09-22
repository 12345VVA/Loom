"""修复工作流生图节点 size 里的全角乘号 U+00D7（应为 ASCII 'x'）。

背景
----
`examples/workflows/12_XHS_PictureBook_Pipeline.json` 里两个生图节点硬编码了
`"size":"864×1152"`（全角乘号），导入 Loom 后脏值进入 `workflow_definition_version.graph_json`。
ToAPIs 适配器判定尺寸时用 `"x" in size`（ASCII），命中失败 → 静默回落 1024x1024。

graph_json 结构（同一份配置有 6 处副本，都要修）
- `nodes[i].config.size`                    ← 编译器运行时读这份（compiler.py L226/L705/L900）
- `elements[i].data.config.size`            ← 前端画布；保存草稿时可能回写覆盖 nodes
- `elements[i].targetNode/sourceNode.data.config.size`  ← 边元素内嵌的节点副本

注意：这不是纯粹的字符问题。实测 ToAPIs gpt-image-vip 不兑现 864x1152，
会把 3:4 规范化为 768x1024（资产 35 已证）。本脚本只做字符归一化，
若目标尺寸需要精确等于所填值，请单独评估取值层问题。

用法
----
    # 1) 只扫描，不改任何数据（默认）
    python scripts/fix_workflow_size_fullwidth.py

    # 2) 修复指定版本并重新发布（会让 current_version_id 指向新发布版）
    python scripts/fix_workflow_size_fullwidth.py --apply \
        --definition-id 11 --version-ids 27,28 --publish

    # 3) 修复示例文件（纯文本替换，不触碰 JSON 转义层）
    python scripts/fix_workflow_size_fullwidth.py --examples --apply

数据库模式必须从 backend/ 目录运行（需要 import app.*）；--examples 模式无此限制。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime

# 允许从 backend/ 或项目根目录运行
_HERE = pathlib.Path(__file__).resolve()
_BACKEND = _HERE.parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

FULLWIDTH = chr(0xD7)
ASCII_X = "x"


def _bad_pattern(size: str) -> str:
    """构造 graph_json 中需要替换的精确子串，如 '"size":"864×1152"'"""
    return '"size":"%s"' % size


def _collect_sizes(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "size" and isinstance(v, str) and FULLWIDTH in v:
                out.append(v)
            _collect_sizes(v, out)
    elif isinstance(node, list):
        for x in node:
            _collect_sizes(x, out)


def scan_version(graph_json: str) -> dict:
    """返回该版本的分析结果。"""
    res = {
        "total_fullwidth": graph_json.count(FULLWIDTH),
        "dirty_sizes": [],
        "in_size_field": 0,
        "problems": [],
    }
    try:
        doc = json.loads(graph_json)
    except Exception as e:
        res["problems"].append("graph_json 解析失败: %s" % e)
        return res

    sizes: list[str] = []
    _collect_sizes(doc, sizes)
    uniq = sorted(set(sizes))
    res["dirty_sizes"] = uniq
    for s in uniq:
        res["in_size_field"] += graph_json.count(_bad_pattern(s))

    if res["in_size_field"] != res["total_fullwidth"]:
        res["problems"].append(
            "全角乘号出现在 size 字段之外：总 %d 处，size 字段内仅 %d 处（脚本拒绝处理）"
            % (res["total_fullwidth"], res["in_size_field"])
        )
    return res


def fix_graph_json(graph_json: str, sizes: list[str]) -> tuple[str, int]:
    """把 size 字段里的全角乘号换成 ASCII x，返回 (新串, 替换处数)。"""
    new = graph_json
    replaced = 0
    for s in sizes:
        fixed = s.replace(FULLWIDTH, ASCII_X)
        pattern = _bad_pattern(s)
        n = new.count(pattern)
        new = new.replace(pattern, '"size":"%s"' % fixed)
        replaced += n
    json.loads(new)  # 保底：结果必须仍是合法 JSON
    return new, replaced


_EXAMPLE_SIZE_RE = re.compile(r"(\d+)\s*%s\s*(\d+)" % re.escape(FULLWIDTH))


def fix_example_file(path: pathlib.Path, apply: bool) -> tuple[int, int, list[str]]:
    """修复示例工作流 JSON 文件，返回 (命中处数, 实际替换处数, 问题列表)。

    只做精确文本替换（`<数字>×<数字>` -> `<数字>x<数字>`），不经过 json.load/dump
    往返，以免破坏内嵌 graph_json 字符串的转义和原有缩进。
    """
    raw = path.read_text(encoding="utf-8")
    hits = raw.count(FULLWIDTH)
    problems: list[str] = []
    if hits == 0:
        return 0, 0, problems

    matches = _EXAMPLE_SIZE_RE.findall(raw)
    if len(matches) != hits:
        problems.append(
            "存在非『数字×数字』形态的全角乘号（× 共 %d 处，尺寸形态仅 %d 处），脚本拒绝处理" % (hits, len(matches))
        )

    new = _EXAMPLE_SIZE_RE.sub(lambda m: "%s%s%s" % (m.group(1), ASCII_X, m.group(2)), raw)
    if new.count(FULLWIDTH) != 0:
        problems.append("替换后仍残留全角乘号")

    try:
        doc = json.loads(new)
    except Exception as exc:  # noqa: BLE001
        problems.append("替换后不是合法 JSON: %s" % exc)
        doc = None

    # 内层 graph_json 也要复验
    if doc is not None and isinstance(doc.get("graph_json"), str):
        try:
            json.loads(doc["graph_json"])
        except Exception as exc:  # noqa: BLE001
            problems.append("graph_json 内层解析失败: %s" % exc)

    if problems:
        return hits, 0, problems

    if apply:
        path.write_text(new, encoding="utf-8")
    return hits, len(matches), []


def run_examples(apply: bool) -> int:
    root = _HERE.parent.parent
    files = sorted((root / "examples").rglob("*.json"))

    print("=" * 96)
    print("示例文件扫描")
    print("=" * 96)
    dirty: list[tuple[pathlib.Path, int]] = []
    for p in files:
        n = p.read_text(encoding="utf-8").count(FULLWIDTH)
        if n:
            dirty.append((p, n))
            print("  %-56s 全角乘号 %d 处" % (str(p.relative_to(root)), n))

    if not dirty:
        print("示例文件中未发现全角乘号。")
        return 0

    total = sum(n for _, n in dirty)
    print()
    print("涉及文件 %d 个，合计 %d 处。" % (len(dirty), total))
    if not apply:
        print()
        print("当前为扫描模式，未写入任何文件。加 --apply 才会执行修复。")
        return 0

    backup_dir = root / "deliverables"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / ("examples-backup-%s.json" % stamp)
    backup_path.write_text(
        json.dumps(
            {str(p.relative_to(root)): p.read_text(encoding="utf-8") for p, _ in dirty},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("已备份原文件 -> %s (%d bytes)" % (backup_path, backup_path.stat().st_size))
    print()

    failed = False
    for p, _ in dirty:
        hits, replaced, problems = fix_example_file(p, apply=True)
        if problems:
            failed = True
            print("  %-56s 中止" % str(p.relative_to(root)))
            for x in problems:
                print("      !! %s" % x)
        else:
            left = p.read_text(encoding="utf-8").count(FULLWIDTH)
            print("  %-56s 替换 %d/%d 处，剩余全角乘号 %d" % (str(p.relative_to(root)), replaced, hits, left))
    return 2 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="修复 workflow graph_json 中 size 的全角乘号")
    ap.add_argument("--apply", action="store_true", help="实际写入（缺省只扫描）")
    ap.add_argument("--examples", action="store_true", help="改为处理 examples/ 下的示例工作流文件（不连数据库）")
    ap.add_argument("--definition-id", type=int, default=None, help="限定工作流定义 id")
    ap.add_argument("--version-ids", type=str, default=None, help="限定版本 id，逗号分隔")
    ap.add_argument("--publish", action="store_true", help="修复草稿后重新发布（迁移 current_version_id）")
    ap.add_argument("--note", type=str, default="修复生图节点 size 全角乘号 ×  U+00D7", help="发布说明")
    args = ap.parse_args()

    if args.examples:
        return run_examples(args.apply)

    from sqlmodel import select

    from app.core.database import SessionLocal
    from app.modules.workflow.model.workflow import WorkflowDefinition
    from app.modules.workflow.model.workflow_version import WorkflowDefinitionVersion
    from app.modules.workflow.service.workflow_version_service import WorkflowVersionService

    only_vids = None
    if args.version_ids:
        only_vids = {int(x) for x in args.version_ids.split(",") if x.strip()}

    with SessionLocal() as session:
        stmt = select(WorkflowDefinitionVersion).order_by(
            WorkflowDefinitionVersion.definition_id, WorkflowDefinitionVersion.version_no
        )
        if args.definition_id is not None:
            stmt = stmt.where(WorkflowDefinitionVersion.definition_id == args.definition_id)

        versions = list(session.exec(stmt).all())

        # 定义指针，用于标注哪些版本是 effective 的
        defs = {d.id: d for d in session.exec(select(WorkflowDefinition)).all()}

        dirty = []
        print("=" * 96)
        print("扫描结果")
        print("=" * 96)
        for v in versions:
            res = scan_version(v.graph_json or "")
            if res["total_fullwidth"] == 0:
                continue
            d = defs.get(v.definition_id)
            role = []
            if d and d.current_version_id == v.id:
                role.append("current(正式运行)")
            if d and d.draft_version_id == v.id:
                role.append("draft(编辑器试跑)")
            dirty.append((v, res, role))
            print(
                "def %-3s v%-2s (vid %-3s) %-9s %-22s 全角=%-2d size字段内=%-2d %s"
                % (
                    v.definition_id,
                    v.version_no,
                    v.id,
                    v.status,
                    ",".join(role),
                    res["total_fullwidth"],
                    res["in_size_field"],
                    res["dirty_sizes"],
                )
            )
            for p in res["problems"]:
                print("      !! %s" % p)

        if not dirty:
            print("未发现含全角乘号的 size 值。")
            return 0

        total_sites = sum(r["in_size_field"] for _, r, _ in dirty)
        blocked = any(r["problems"] for _, r, _ in dirty)
        print()
        print("涉及版本 %d 个，脏值落点合计 %d 处。" % (len(dirty), total_sites))
        if blocked:
            print("存在结构性问题，已中止（不做任何写入）。")
            return 2

        if not args.apply:
            print()
            print("当前为扫描模式，未写入任何数据。加 --apply 才会执行修复。")
            return 0

        # 限定要处理的版本
        targets = [v for v, _, _ in dirty]
        if only_vids is not None:
            targets = [v for v in targets if v.id in only_vids]
            if not targets:
                print("--version-ids 未匹配到任何脏版本，中止。")
                return 2
            print("按 --version-ids 限定处理: %s" % [v.id for v in targets])

        # 备份
        backup_dir = _HERE.parent.parent / "deliverables"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = backup_dir / ("workflow-graph-backup-%s.json" % stamp)
        backup_path.write_text(
            json.dumps(
                {
                    str(v.id): {
                        "definition_id": v.definition_id,
                        "version_no": v.version_no,
                        "status": str(v.status),
                        "graph_json": v.graph_json,
                    }
                    for v in targets
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print("已备份原 graph_json -> %s (%d bytes)" % (backup_path, backup_path.stat().st_size))

        # 写入
        print()
        for v in targets:
            res = scan_version(v.graph_json or "")
            new_g, n = fix_graph_json(v.graph_json, res["dirty_sizes"])
            v.graph_json = new_g
            print("vid %-3s (v%s) 修正 %d 处 -> %s" % (v.id, v.version_no, n, v.graph_json.count(FULLWIDTH)))
        session.commit()
        print("已提交。")

        # 发布
        if args.publish:
            if args.definition_id is None:
                print("--publish 需要同时指定 --definition-id，跳过发布。")
                return 2
            svc = WorkflowVersionService(session)
            pub = svc.publish(args.definition_id, args.note, None)
            print()
            print("已发布: vid %s (v%s) status=%s" % (pub.id, pub.version_no, pub.status))

        # 复检
        print()
        print("=" * 96)
        print("复检")
        print("=" * 96)
        d = session.get(WorkflowDefinition, args.definition_id) if args.definition_id else None
        if d:
            print(
                "def %s current_version_id=%s  draft_version_id=%s"
                % (d.id, d.current_version_id, d.draft_version_id)
            )
        stmt2 = select(WorkflowDefinitionVersion).order_by(WorkflowDefinitionVersion.version_no)
        if args.definition_id:
            stmt2 = stmt2.where(WorkflowDefinitionVersion.definition_id == args.definition_id)
        for v in session.exec(stmt2).all():
            fw = (v.graph_json or "").count(FULLWIDTH)
            print(
                "  v%-2s vid=%-3s %-9s 全角乘号剩余=%d %s"
                % (v.version_no, v.id, v.status, fw, "OK" if fw == 0 else "<-- 仍有脏值")
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
