"""长期记忆检索/写入性能 benchmark（设计 §12：批次 2 交付）。

度量：
1. search 两阶段管线 P50/P95/P99 @ N=100/500/1000（1536 维向量 + 4000 字符满配 content）
2. store 写路径 P50/P95（含语义相似检查窗口 200 条余弦 + key upsert UPDATE）
3. 余弦分数分布（threshold 0.35 占位值的校准参考——真实定值需人工标注相似/无关对，
   本脚本输出 top1 分数与无关对分数的分位数供人工判断）

口径：SQLite 内存引擎（本机无 PG）；数字为量级参考，PG 生产结论以 CI 环境复测为准。
候选集受 WORKFLOW_MEMORY_SCOPE_CAP（默认 1000）约束——cap 调大时本 benchmark 需重跑（设计 §5.1）。

运行：cd backend && venv/Scripts/python.exe scripts/bench_memory_search.py
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

from sqlmodel import Session, SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from helpers import make_test_engine  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.modules.workflow.model.workflow_memory import WorkflowMemory  # noqa: E402
from app.modules.workflow.service import workflow_memory_service as wms  # noqa: E402
from app.modules.workflow.service.workflow_memory_service import (  # noqa: E402
    search_memories,
    touch_last_accessed,
    upsert_memory,
)

DIM = 1536
CONTENT_LEN = 4000
ROUNDS = 30
random.seed(42)


def _rand_vec() -> list[float]:
    v = [random.gauss(0, 1) for _ in range(DIM)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def _similar_to(base: list[float], noise: float = 0.1) -> list[float]:
    return [x + random.gauss(0, noise) for x in base]


def _seed_rows(session: Session, definition_id: int, n: int) -> None:
    for i in range(n):
        content = (f"记忆{i}：" + "内容" * 2000)[:CONTENT_LEN]
        row = WorkflowMemory(
            definition_id=definition_id,
            memory_env="production",
            memory_type="fact",
            memory_key=f"k{i}" if i % 3 == 0 else None,
            content=content,
            content_hash=wms.content_hash_of(content),
            tags=json.dumps(["bench"], ensure_ascii=False),
            embedding=json.dumps(_rand_vec()),
            embedding_space=f"bench-model:{DIM}",
            source_instance_id=None,
            source_node_id=None,
            source_run_type="admin",
            created_by_user_id=1,
            updated_by_user_id=1,
        )
        session.add(row)
    session.commit()


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)

    def pct(p: float) -> float:
        idx = min(len(ordered) - 1, max(0, round(p * (len(ordered) - 1))))
        return ordered[idx]

    return {"p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99)}


def bench_search(engine, definition_id: int) -> None:
    query_vec = _rand_vec()
    samples: list[float] = []
    result_sample = None
    with Session(engine) as session:
        for _ in range(ROUNDS):
            t0 = time.perf_counter()
            result_sample = search_memories(
                session,
                definition_id=definition_id,
                memory_env="production",
                query="bench 查询",
                query_embedding=query_vec,
                query_space=f"bench-model:{DIM}",
            )
            samples.append((time.perf_counter() - t0) * 1000)
    p = _percentiles(samples)
    print(
        f"search  N={definition_id and '' or ''}{len(samples)}轮: P50={p['p50']:.1f}ms P95={p['p95']:.1f}ms P99={p['p99']:.1f}ms"
        f" 命中={len(result_sample['items']) if result_sample else 0}"
    )


def bench_store(engine, definition_id: int) -> None:
    samples: list[float] = []
    with Session(engine) as session:
        base_vec = _rand_vec()
        for i in range(ROUNDS):
            content = (f"新写入{i}：" + "正文" * 2000)[:CONTENT_LEN]
            t0 = time.perf_counter()
            upsert_memory(
                session,
                definition_id=definition_id,
                memory_env="production",
                content=content,
                memory_key=f"upsert-{i % 5}",  # 1/5 概率走 key upsert UPDATE
                memory_type="fact",
                tags=["bench"],
                embedding=_similar_to(base_vec),  # 高相似 → 触发语义相似 warning 窗口比对
                embedding_space=f"bench-model:{DIM}",
                source_instance_id=None,
                source_node_id="bench",
                source_run_type="production",
                user_id=1,
            )
            samples.append((time.perf_counter() - t0) * 1000)
    p = _percentiles(samples)
    print(
        f"store   {ROUNDS}轮(含语义窗口比对+key upsert): P50={p['p50']:.1f}ms P95={p['p95']:.1f}ms P99={p['p99']:.1f}ms"
    )


def bench_touch(engine, definition_id: int) -> None:
    with Session(engine) as session:
        rows = session.exec(select(WorkflowMemory.id).limit(20)).all()
        ids = [r[0] if not isinstance(r, int) else r for r in rows]
        samples = []
        for _ in range(10):
            t0 = time.perf_counter()
            touch_last_accessed(session, ids)
            samples.append((time.perf_counter() - t0) * 1000)
    p = _percentiles(samples)
    print(f"touch   {len(ids)}条批量回写: P50={p['p50']:.1f}ms P95={p['p95']:.1f}ms")


def bench_score_distribution(engine, definition_id: int) -> None:
    """threshold 校准参考：无关对（随机向量 vs 库内向量）的余弦分数分位数。

    1536 维高斯随机向量对的余弦集中在 0 附近（|r| < 0.06 @P99）；
    threshold 应落在「无关对上界」与「人工标注相似对下界」之间。
    """
    with Session(engine) as session:
        rows = session.exec(select(WorkflowMemory).limit(50)).all()
        # SQLModel exec 的单列包装 Row 怪癖防御（部分场景 select(Model) 返回 Row(Model) 而非实体）
        rows = [r if isinstance(r, WorkflowMemory) else r[0] for r in rows]
        vectors = [json.loads(r.embedding) for r in rows if r.embedding]
    random_scores = []
    for _ in range(200):
        q = _rand_vec()
        row_vec = random.choice(vectors)
        random_scores.append(wms._cosine_similarity(q, row_vec))
    p = _percentiles(sorted(random_scores))
    print(
        f"score   无关对余弦分布: P50={p['p50']:+.4f} P95={p['p95']:+.4f} P99={p['p99']:+.4f}"
        f" max={max(random_scores):+.4f}（threshold 占位 0.35 应显著高于 P99 上界）"
    )


def main() -> None:
    print("=== Workflow Memory benchmark（SQLite 内存引擎，1536 维 / 4000 字符满配）===")
    for n in (100, 500, 1000):
        print(f"\n--- N={n} ---")
        engine = make_test_engine()
        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            _seed_rows(session, definition_id=1, n=n)
        bench_search(engine, 1)
        if n == 1000:
            bench_store(engine, 1)
            bench_touch(engine, 1)
            bench_score_distribution(engine, 1)
        engine.dispose()
    print("\n结论口径：候选集 ≤ cap(1000) 时内存余弦量级可接受则维持一期方案；")
    print("显著劣化（P95 > 数百 ms）则触发 pgvector 评估（设计 §5.5）。")


if __name__ == "__main__":
    main()
