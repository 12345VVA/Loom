"""迁移双轨一致性测试（M7：迁移双轨已两次实际漂移——0002 补漏表、0019 对齐索引/类型）。

双轨现状：轨 A = alembic 迁移链（生产升级/CI 空库部署路径）；轨 B = init_db 的
create_all + _ensure_indexes（开发启动路径）。两轨各自演进时会在表/列/索引上漂移，
CI 的 `alembic check` 只对账「模型 vs 迁移链结果」，对账不到「init_db 结果 vs 迁移链结果」。

本测试对三条链路全量断言（需 PostgreSQL，无 PG 时 skip——D6 先例）：
1. 迁移链可从空库 upgrade head（正统从零部署路径不破）；
2. alembic check 零 drift（模型与迁移链结果一致，镜像 CI 门禁使本地可复现）；
3. 迁移链 schema 与 init_db schema 的结构对账（表/列/索引/主键 + 类型），漂移在此拦截。

运行方式：在 DATABASE_URL 指向的 PG 库上创建两个一次性 schema（loom_drift_chain /
loom_drift_models），跑完即删，不触碰业务 schema。SQLite（无 PG）自动跳过。
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from sqlalchemy import inspect
from sqlalchemy.engine import Engine, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]

SCHEMA_CHAIN = "loom_drift_chain"
SCHEMA_MODELS = "loom_drift_models"


def _schema_url(base_url: str, schema: str) -> str:
    """在基础连接串上追加 search_path（CI 同款 options 语法，密码等 query 参数原样保留）。"""
    return f"{base_url}?options=-csearch_path%3D{schema}"


class MigrationDriftTestCase(unittest.TestCase):
    def setUp(self):
        base_url = os.environ.get("DATABASE_URL", "")
        if not base_url.startswith("postgresql"):
            self.skipTest("需要 PostgreSQL（DATABASE_URL 非 PG，双轨对账测试跳过——D6 先例）")

        import psycopg

        # 原始 psycopg 连接不识别 SQLAlchemy 方言后缀（checkpointer.py 同款剥离）
        self.base_url = base_url
        self.admin_url = base_url.replace("postgresql+psycopg://", "postgresql://", 1)
        admin = psycopg.connect(self.admin_url, autocommit=True)
        try:
            # 从零建 schema：上次残留（崩溃遗留）先清掉，保证两轨都从空白开始
            for schema in (SCHEMA_CHAIN, SCHEMA_MODELS):
                admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                admin.execute(f'CREATE SCHEMA "{schema}"')
        finally:
            admin.close()

        env = {**os.environ, "DATABASE_URL": _schema_url(base_url, SCHEMA_CHAIN)}

        # 轨 A：迁移链从空库升级（子进程隔离——settings/engine 已在测试进程导入，无法重指 URL）
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(r.returncode, 0, f"迁移链空库 upgrade head 失败：\n{r.stdout}\n{r.stderr}")

        # 轨 B：init_db create_all（开发启动路径）
        r = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.core.database import init_db; init_db()",
            ],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": _schema_url(base_url, SCHEMA_MODELS)},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(r.returncode, 0, f"init_db 建表失败：\n{r.stdout}\n{r.stderr}")

        # alembic check：模型 vs 迁移链结果零 drift（镜像 CI 门禁，使本地可复现）
        r = subprocess.run(
            [sys.executable, "-m", "alembic", "check"],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(r.returncode, 0, f"alembic check 检出 drift：\n{r.stdout}\n{r.stderr}")

    def tearDown(self):
        try:
            import psycopg

            admin = psycopg.connect(self.admin_url, autocommit=True)
            try:
                for schema in (SCHEMA_CHAIN, SCHEMA_MODELS):
                    admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            finally:
                admin.close()
        except Exception:
            pass

    # ---------------------------------- 对账 ----------------------------------

    def test_chain_schema_matches_initdb_schema(self):
        chain_engine = self._engine_for(SCHEMA_CHAIN)
        models_engine = self._engine_for(SCHEMA_MODELS)

        chain_tables = set(inspect(chain_engine).get_table_names(schema=SCHEMA_CHAIN))
        models_tables = set(inspect(models_engine).get_table_names(schema=SCHEMA_MODELS))
        # langgraph checkpoint 系表由 PostgresSaver.setup() 自建自管，两轨都不含，排除口径与 env.py 一致
        chain_tables = {t for t in chain_tables if not t.startswith("checkpoint")}
        models_tables = {t for t in models_tables if not t.startswith("checkpoint")}
        # alembic_version 是轨 A 的版本标记，非业务结构
        chain_tables.discard("alembic_version")

        # 防空洞绿：两侧都必须拿到全量表（与架构守卫的 metadata ≥38 同源），否则对账无意义
        self.assertGreaterEqual(
            len(chain_tables), 38, f"迁移链 schema 表数异常（upgrade 未生效？）：{len(chain_tables)}"
        )
        self.assertGreaterEqual(
            len(models_tables), 38, f"init_db schema 表数异常（create_all 未生效？）：{len(models_tables)}"
        )

        self.assertEqual(
            models_tables - chain_tables,
            set(),
            "init_db（create_all）有而迁移链没有的表——模型加了表未写迁移（0002 同类漂移）",
        )
        self.assertEqual(
            chain_tables - models_tables,
            set(),
            "迁移链有而 init_db 没有的表——迁移链与模型 metadata 脱节",
        )

        problems: list[str] = []
        for table in sorted(chain_tables & models_tables):
            problems += self._compare_table(chain_engine, models_engine, table)
        self.assertEqual(problems, [], "迁移链 schema 与 init_db schema 结构漂移：\n" + "\n".join(problems))

    # ---------------------------------- 辅助 ----------------------------------

    def _engine_for(self, schema: str) -> Engine:
        from sqlalchemy import create_engine

        # URL 自带 ?options=-csearch_path（CI 同款 schema 隔离语法），psycopg 原生识别
        return create_engine(make_url(_schema_url(self.base_url, schema)))

    def _compare_table(self, chain_engine: Engine, models_engine: Engine, table: str) -> list[str]:
        problems: list[str] = []
        ci, mi = inspect(chain_engine), inspect(models_engine)

        chain_cols = {c["name"]: c for c in ci.get_columns(table, schema=SCHEMA_CHAIN)}
        models_cols = {c["name"]: c for c in mi.get_columns(table, schema=SCHEMA_MODELS)}
        for name in sorted(models_cols.keys() - chain_cols.keys()):
            problems.append(f"表 {table}: 列 {name} 迁移链缺失（模型有）")
        for name in sorted(chain_cols.keys() - models_cols.keys()):
            problems.append(f"表 {table}: 列 {name} 模型已删但迁移链残留")

        for name in sorted(chain_cols.keys() & models_cols.keys()):
            ct, mt = str(chain_cols[name]["type"]), str(models_cols[name]["type"])
            if not _types_equivalent(ct, mt):
                problems.append(f"表 {table}: 列 {name} 类型漂移 迁移链={ct} init_db={mt}")

        # 索引对账（按名字+列集合；init_db 的 _ensure_indexes 与迁移各自建，漏建/多建都在此暴露）
        chain_idx = {i["name"]: set(i["column_names"]) for i in ci.get_indexes(table, schema=SCHEMA_CHAIN)}
        models_idx = {i["name"]: set(i["column_names"]) for i in mi.get_indexes(table, schema=SCHEMA_MODELS)}
        for name in sorted(models_idx.keys() - chain_idx.keys()):
            problems.append(f"表 {table}: 索引 {name} 迁移链缺失（0019 同类漂移）")
        for name in sorted(chain_idx.keys() - models_idx.keys()):
            problems.append(f"表 {table}: 索引 {name} 模型/迁移链多余")

        # 主键对账
        chain_pk = set(ci.get_pk_constraint(table, schema=SCHEMA_CHAIN).get("constrained_columns") or [])
        models_pk = set(mi.get_pk_constraint(table, schema=SCHEMA_MODELS).get("constrained_columns") or [])
        if chain_pk != models_pk:
            problems.append(f"表 {table}: 主键漂移 迁移链={sorted(chain_pk)} init_db={sorted(models_pk)}")

        return problems


def _types_equivalent(chain_type: str, models_type: str) -> bool:
    """类型串等价判定（反射串 vs metadata 编译串的已知拼写差异在此归一）。"""
    if chain_type == models_type:
        return True
    # 反射可能带可见度差异（如 VARCHAR(n) vs VARCHAR(n)、TIMESTAMP WITH TIME ZONE vs TIMESTAMPTZ）
    aliases = {
        "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
    }
    return aliases.get(chain_type, chain_type) == aliases.get(models_type, models_type)


if __name__ == "__main__":
    unittest.main()
