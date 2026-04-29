import os
import sys
import unittest
from datetime import datetime
from typing import Optional

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app  # noqa: E402
from app.framework.router.query_builder import QueryBuilder  # noqa: E402
from app.modules.base.model.sys import (  # noqa: E402
    SysLoginLogCreateRequest,
    SysLoginLogRead,
    SysParamCreateRequest,
    SysParamRead,
    SysSecurityLogCreateRequest,
    SysSecurityLogRead,
)
from app.modules.base.service.cache_service import cache_get  # noqa: E402
from app.modules.base.service.data_scope_service import DataScopeContext  # noqa: E402
from app.core.config import settings  # noqa: E402


class ScopedRow(SQLModel, table=True):
    __tablename__ = "test_framework_scoped_row"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    department_id: Optional[int] = Field(default=None, index=True)
    name: str


class PlainRow(SQLModel, table=True):
    __tablename__ = "test_framework_plain_row"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class FrameworkAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def _login_headers(self) -> dict[str, str]:
        captcha_res = self.client.get("/admin/base/open/captcha")
        captcha_data = captcha_res.json()["data"]
        verify_code = cache_get(f"verify:img:{captcha_data['captchaId']}")
        login_res = self.client.post(
            "/admin/base/open/login",
            json={
                "username": settings.DEFAULT_ADMIN_USERNAME,
                "password": settings.DEFAULT_ADMIN_PASSWORD,
                "captchaId": captcha_data["captchaId"],
                "verifyCode": verify_code,
            },
        )
        self.assertEqual(login_res.status_code, 200)
        return {"Authorization": f"Bearer {login_res.json()['data']['token']}"}

    def test_query_builder_data_scope_filters_self_and_department(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine, tables=[ScopedRow.__table__])
        with Session(engine) as session:
            session.add_all(
                [
                    ScopedRow(user_id=1, department_id=10, name="self"),
                    ScopedRow(user_id=2, department_id=20, name="dept"),
                    ScopedRow(user_id=3, department_id=30, name="blocked"),
                ]
            )
            session.commit()

            statement = QueryBuilder(ScopedRow).apply_all(
                select(ScopedRow),
                data_scope=DataScopeContext(allowed_department_ids=frozenset({20}), self_only=False),
                current_user_id=1,
            )
            names = {row.name for row in session.exec(statement).all()}

        self.assertEqual(names, {"self", "dept"})

    def test_query_builder_data_scope_allows_super_admin_and_plain_models(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(engine, tables=[ScopedRow.__table__, PlainRow.__table__])
        with Session(engine) as session:
            session.add_all(
                [
                    ScopedRow(user_id=1, department_id=10, name="a"),
                    ScopedRow(user_id=2, department_id=20, name="b"),
                    PlainRow(name="plain-a"),
                    PlainRow(name="plain-b"),
                ]
            )
            session.commit()

            super_statement = QueryBuilder(ScopedRow).apply_all(
                select(ScopedRow),
                data_scope=DataScopeContext(allow_all=True, self_only=False),
                current_user_id=1,
            )
            plain_statement = QueryBuilder(PlainRow).apply_all(
                select(PlainRow),
                data_scope=DataScopeContext(allowed_department_ids=frozenset({20}), self_only=False),
                current_user_id=1,
            )

            self.assertEqual(len(session.exec(super_statement).all()), 2)
            self.assertEqual(len(session.exec(plain_statement).all()), 2)

    def test_crud_page_and_list_support_get_and_post(self):
        headers = self._login_headers()

        get_page = self.client.get("/admin/dict/type/page", headers=headers, params={"page": 1, "size": 5})
        post_page = self.client.post("/admin/dict/type/page", headers=headers, json={"page": 1, "size": 5})
        self.assertEqual(get_page.status_code, 200)
        self.assertEqual(post_page.status_code, 200)
        self.assertEqual(get_page.json()["data"]["pagination"]["size"], post_page.json()["data"]["pagination"]["size"])
        self.assertIn("list", get_page.json()["data"])

        get_list = self.client.get("/admin/dict/type/list", headers=headers)
        post_list = self.client.post("/admin/dict/type/list", headers=headers, json={})
        self.assertEqual(get_list.status_code, 200)
        self.assertEqual(post_list.status_code, 200)
        self.assertIsInstance(get_list.json()["data"], list)
        self.assertIsInstance(post_list.json()["data"], list)

    def test_sys_models_accept_and_serialize_camel_case(self):
        param = SysParamCreateRequest.model_validate({"name": "站点", "keyName": "siteName", "dataType": 1})
        self.assertEqual(param.key_name, "siteName")
        self.assertEqual(param.data_type, 1)

        now = datetime.utcnow()
        param_read = SysParamRead(
            id=1,
            name="站点",
            key_name="siteName",
            data_type=1,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True)
        self.assertIn("keyName", param_read)
        self.assertIn("createTime", param_read)

        login = SysLoginLogCreateRequest.model_validate({"userId": 1, "loginType": "password", "riskHit": 1})
        self.assertEqual(login.user_id, 1)
        self.assertEqual(login.login_type, "password")
        self.assertEqual(login.risk_hit, 1)

        security = SysSecurityLogCreateRequest.model_validate(
            {
                "operatorId": 1,
                "operatorName": "admin",
                "targetType": "user",
                "operation": "update",
                "module": "user",
            }
        )
        self.assertEqual(security.operator_id, 1)
        self.assertEqual(security.target_type, "user")

        login_read = SysLoginLogRead(
            id=1,
            login_type="password",
            status=1,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True)
        security_read = SysSecurityLogRead(
            id=1,
            operator_id=1,
            operator_name="admin",
            target_type="user",
            operation="update",
            module="user",
            status=1,
            created_at=now,
            updated_at=now,
        ).model_dump(by_alias=True)
        self.assertIn("loginType", login_read)
        self.assertIn("operatorId", security_read)

    def test_eps_uses_public_prop_and_source_field(self):
        response = self.client.get("/admin/base/open/eps")
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]

        task_info = next(item for item in data["task"] if item["prefix"] == "/admin/task/info")
        task_type = next(item for item in task_info["columns"] if item["source"] == "task_type")
        self.assertEqual(task_type["prop"], "taskType")
        self.assertEqual(task_type["propertyName"], "taskType")
        self.assertIn("taskType", task_info["pageQueryOp"]["fieldEq"])

        sys_param = next(item for item in data["base"] if item["prefix"] == "/admin/base/sys/param")
        key_name = next(item for item in sys_param["columns"] if item["source"] == "key_name")
        self.assertEqual(key_name["prop"], "keyName")
        self.assertEqual(key_name["propertyName"], "keyName")

        dict_info = next(item for item in data["dict"] if item["prefix"] == "/admin/dict/info")
        type_id = next(item for item in dict_info["columns"] if item["source"] == "type_id")
        self.assertEqual(type_id["prop"], "typeId")


if __name__ == "__main__":
    unittest.main()
