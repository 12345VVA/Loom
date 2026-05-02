import os
import sys
import unittest
from datetime import datetime

from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings  # noqa: E402
from app.core.database import transaction  # noqa: E402
from app.core.startup_checks import validate_startup_settings  # noqa: E402
from app.framework.io import ImportExportField, ImportExportSchema, import_rows_from_csv  # noqa: E402
from app.framework.middleware.metrics import record_metric_event, render_metrics  # noqa: E402
from app.modules.base.service.cache_service import CacheNamespace  # noqa: E402
from app.modules.task.model.task import TaskInfo  # noqa: E402
from app.modules.task.service.task_service import compute_next_run_time, sync_task_schedule_state, TASK_SCHEDULE_CACHE  # noqa: E402


class TxRow(SQLModel, table=True):
    __tablename__ = "test_tx_row"

    id: int | None = Field(default=None, primary_key=True)
    name: str


class ProductionHardeningTests(unittest.TestCase):
    def test_transaction_commits_and_rolls_back(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine, tables=[TxRow.__table__])

        with Session(engine) as session:
            with transaction(session):
                session.add(TxRow(name="ok"))
            self.assertEqual(len(session.exec(select(TxRow)).all()), 1)

            with self.assertRaises(RuntimeError):
                with transaction(session):
                    session.add(TxRow(name="fail"))
                    raise RuntimeError("boom")
            names = [row.name for row in session.exec(select(TxRow)).all()]
            self.assertEqual(names, ["ok"])

    def test_transaction_respects_explicit_outer_transaction(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine, tables=[TxRow.__table__])

        with Session(engine) as session:
            with self.assertRaises(RuntimeError):
                with session.begin():
                    session.add(TxRow(name="outer"))
                    with transaction(session):
                        session.add(TxRow(name="inner"))
                    raise RuntimeError("rollback outer")
            self.assertEqual(session.exec(select(TxRow)).all(), [])

    def test_startup_settings_reports_production_risks(self):
        prod = settings.model_copy(update={
            "DEBUG": False,
            "JWT_SECRET_KEY": "short",
            "DEFAULT_ADMIN_PASSWORD": "admin",
            "CORS_ORIGINS": '["*"]',
            "REDIS_URL": "",
            "CELERY_BROKER_URL": "",
        })
        results = validate_startup_settings(prod)
        keys = {item.key for item in results if item.level == "error"}
        self.assertIn("JWT_SECRET_KEY", keys)
        self.assertIn("DEFAULT_ADMIN_PASSWORD", keys)
        self.assertIn("CORS_ORIGINS", keys)

    def test_cache_namespace_builds_keys_and_clears(self):
        namespace = CacheNamespace("test:ns", default_ttl_seconds=60)
        namespace.set("user", 1, value="cached")
        self.assertEqual(namespace.get("user", 1), "cached")
        self.assertEqual(namespace.clear("user"), 1)
        self.assertIsNone(namespace.get("user", 1))

    def test_import_rows_reports_missing_required_fields(self):
        schema = ImportExportSchema([
            ImportExportField("name", required=True),
            ImportExportField("status"),
        ])
        result = import_rows_from_csv("name,status\n,1\n", schema)
        self.assertFalse(result.success)
        self.assertEqual(result.errors[0].row, 2)
        self.assertEqual(result.errors[0].field, "name")

    def test_metrics_records_framework_events(self):
        record_metric_event("unit_test_event", status="ok")
        rendered = render_metrics()
        self.assertIn('loom_events_total{event="unit_test_event",status="ok"}', rendered)

    def test_task_schedule_state_syncs_cache(self):
        task = TaskInfo(id=12345, name="demo", status=1, every=60000, task_type=1)
        next_run = compute_next_run_time(task)
        self.assertIsNotNone(next_run)
        sync_task_schedule_state(task)
        cached = TASK_SCHEDULE_CACHE.get_json("12345")
        self.assertEqual(cached["id"], 12345)
        self.assertEqual(cached["status"], 1)
        TASK_SCHEDULE_CACHE.delete("12345")

    def test_cron_task_uses_expression_for_next_run_time(self):
        now = datetime(2026, 5, 2, 1, 30)
        task = TaskInfo(id=12346, name="daily", status=1, task_type=0, cron="0 2 * * *")
        next_run = compute_next_run_time(task, now)
        self.assertEqual(next_run, datetime(2026, 5, 2, 2, 0))


if __name__ == "__main__":
    unittest.main()
