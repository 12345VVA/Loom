"""CRUD page size 钳制测试。

验证前端通过 body 传入超大/非法 size 时，_build_crud_query 会将其钳制到 [1, 100]，
防止 DoS。模拟 page 端点的实际流程：body 中的 size 被 pop 出来后传给 _build_crud_query。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.framework.controller_meta import _build_crud_query, QueryConfig  # noqa: E402


def _build_page_query(body: dict) -> "object":
    """模拟 page 端点的 body 覆盖流程。

    page 端点会先 `size = body_params.pop("size")`，再把 size 作为参数传入
    _build_crud_query。这里复刻该流程，使测试直接对应 `{"size": X}` 语义。
    """
    body_params = dict(body)
    size = body_params.pop("size", None)
    page = body_params.pop("page", None)
    return _build_crud_query(
        request=None,
        config=QueryConfig(),
        page=page,
        size=size,
        body_params=body_params,
    )


def _build_list_query(body: dict) -> "object":
    """模拟 list 端点 / CrudQuery.from_request 路径：size 留在 body_params 中。"""
    return _build_crud_query(
        request=None,
        config=QueryConfig(),
        body_params=dict(body),
    )


class PageSizeClampViaParamTests(unittest.TestCase):
    """page 端点 body 覆盖路径（size 作为参数传入）。"""

    def test_size_huge_clamped_to_100(self):
        self.assertEqual(_build_page_query({"size": 1000000}).size, 100)

    def test_size_zero_clamped_to_1(self):
        self.assertEqual(_build_page_query({"size": 0}).size, 1)

    def test_size_negative_clamped_to_1(self):
        self.assertEqual(_build_page_query({"size": -5}).size, 1)

    def test_size_50_kept(self):
        self.assertEqual(_build_page_query({"size": 50}).size, 50)

    def test_size_100_kept(self):
        self.assertEqual(_build_page_query({"size": 100}).size, 100)

    def test_size_101_clamped_to_100(self):
        self.assertEqual(_build_page_query({"size": 101}).size, 100)

    def test_size_string_huge_clamped(self):
        self.assertEqual(_build_page_query({"size": "1000000"}).size, 100)

    def test_size_invalid_string_becomes_none(self):
        self.assertIsNone(_build_page_query({"size": "abc"}).size)

    def test_size_none_remains_none(self):
        self.assertIsNone(_build_page_query({"size": None}).size)

    def test_size_missing_remains_none(self):
        self.assertIsNone(_build_page_query({}).size)


class PageSizeClampViaBodyTests(unittest.TestCase):
    """list 端点 / from_request 路径（size 在 body_params 中，经 isdigit 校验）。"""

    def test_size_body_huge_clamped_to_100(self):
        self.assertEqual(_build_list_query({"size": 1000000}).size, 100)

    def test_size_body_50_kept(self):
        self.assertEqual(_build_list_query({"size": 50}).size, 50)

    def test_size_body_100_kept(self):
        self.assertEqual(_build_list_query({"size": 100}).size, 100)

    def test_size_body_101_clamped_to_100(self):
        self.assertEqual(_build_list_query({"size": 101}).size, 100)

    def test_size_body_string_huge_clamped(self):
        self.assertEqual(_build_list_query({"size": "1000000"}).size, 100)

    def test_page_size_alias_clamped(self):
        self.assertEqual(_build_list_query({"pageSize": 1000000}).size, 100)

    def test_page_size_snake_alias_clamped(self):
        self.assertEqual(_build_list_query({"page_size": 1000000}).size, 100)


if __name__ == "__main__":
    unittest.main()
