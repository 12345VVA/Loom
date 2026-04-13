"""
通用查询构造器，用于解析 CrudQuery 并生成 SQLAlchemy 查询语句
"""
from __future__ import annotations

from typing import Any, Type, Iterable
from sqlalchemy import asc, desc, or_
from sqlmodel import select, Session

from app.framework.controller_meta import CrudQuery
from app.modules.base.service.data_scope_service import DataScopeContext


class QueryBuilder:
    def __init__(self, model: Type[Any], query: CrudQuery | None = None):
        self.model = model
        self.query = query

    def apply_all(self, statement, data_scope: DataScopeContext | None = None, current_user_id: int | None = None):
        """链式应用所有查询规则"""
        statement = self.apply_data_scope(statement, data_scope, current_user_id)
        statement = self.apply_filters(statement)
        statement = self.apply_keyword(statement)
        statement = self.apply_ranges(statement)
        statement = self.apply_where(statement)
        statement = self.apply_select(statement)
        statement = self.apply_sort(statement)
        return statement

    def apply_filters(self, statement):
        if not self.query:
            return statement

        # 处理等值过滤 (支持 IN)
        for field, value in self.query.eq_filters.items():
            if not hasattr(self.model, field):
                continue
            column = getattr(self.model, field)
            
            # 自动转换布尔值和数字 (适配 query_params 原始字符串)
            coerced_value = self._coerce_value(column, value)
            
            if isinstance(coerced_value, (list, tuple, set)):
                statement = statement.where(column.in_(list(coerced_value)))
            else:
                statement = statement.where(column == coerced_value)

        # 处理模糊过滤
        for field, value in self.query.like_filters.items():
            if not hasattr(self.model, field) or not value:
                continue
            statement = statement.where(getattr(self.model, field).contains(value))

        return statement

    def apply_keyword(self, statement):
        if not self.query or not self.query.keyword:
            return statement
        
        # 优先使用 query.keyword_fields，没有则不处理关键词搜索
        if not self.query.keyword_fields:
            return statement
        
        expressions = []
        for field in self.query.keyword_fields:
            if hasattr(self.model, field):
                expressions.append(getattr(self.model, field).contains(self.query.keyword))
        
        if expressions:
            statement = statement.where(or_(*expressions))
        return statement

    def apply_ranges(self, statement):
        if not self.query:
            return statement
            
        params = self.query.raw_params
        # 常见范围参数后缀
        for key, value in params.items():
            if not value: continue
            
            # 处理开始时间/结束时间 (适配前端日期范围选择器)
            field_name = None
            op = None
            
            if key.endswith("StartTime"):
                field_name, op = key[:-9], ">="
            elif key.endswith("EndTime"):
                field_name, op = key[:-7], "<="
                
            if field_name and hasattr(self.model, field_name):
                col = getattr(self.model, field_name)
                statement = statement.where(col >= value if op == ">=" else col <= value)
        
        return statement

    def apply_where(self, statement):
        if not self.query or not self.query.where_handler:
            return statement
        # 兼容原本的 where_handler(statement, model, query) 签名
        return self.query.where_handler(statement, self.model, self.query)

    def apply_select(self, statement):
        if not self.query or not self.query.select_fields:
            return statement
        from sqlalchemy.orm import load_only
        columns = [getattr(self.model, field) for field in self.query.select_fields if hasattr(self.model, field)]
        if columns:
            return statement.options(load_only(*columns))
        return statement

    def apply_sort(self, statement, fallback_field: str = "created_at"):
        if not self.query:
            if hasattr(self.model, fallback_field):
                column = getattr(self.model, fallback_field)
                return statement.order_by(desc(column))
            return statement

        # 1. 显式排序 (order & sort)
        if self.query.order:
            allowed_fields = set(self.query.order_fields) if self.query.order_fields else set()
            if hasattr(self.model, self.query.order) and (not allowed_fields or self.query.order in allowed_fields):
                column = getattr(self.model, self.query.order)
                return statement.order_by(asc(column) if self.query.sort == "asc" else desc(column))

        # 2. 附加排序 (add_order_by)
        if self.query.add_order_by:
            for item in self.query.add_order_by:
                if hasattr(self.model, item.column):
                    column = getattr(self.model, item.column)
                    statement = statement.order_by(asc(column) if item.direction.lower() == "asc" else desc(column))
            return statement

        # 3. 兜底排序
        if hasattr(self.model, fallback_field):
            column = getattr(self.model, fallback_field)
            statement = statement.order_by(desc(column))
            
        return statement

    def apply_data_scope(self, statement, data_scope: DataScopeContext | None, current_user_id: int | None):
        """应用数据权限隔离"""
        if not data_scope or data_scope.allow_all:
            return statement

        # 检测模型是否具备权限相关字段
        user_id_col = getattr(self.model, "user_id", None)
        dept_id_col = getattr(self.model, "department_id", None)

        if user_id_col is None and dept_id_col is None:
            return statement

        filters = []
        
        # 1. 如果仅限本人 (或者 data_scope 没有任何其它部门权限)
        if user_id_col is not None and current_user_id is not None:
            # 基础过滤：允许访问本人创建的数据
            filters.append(user_id_col == current_user_id)
            
        # 2. 如果允许特定部门
        if dept_id_col is not None and data_scope.allowed_department_ids:
            # 扩展过滤：允许访问这些部门下的数据
            filters.append(dept_id_col.in_(list(data_scope.allowed_department_ids)))

        if filters:
            # 使用 OR 连接：既能看自己的，也能看拥有权限的部门的
            return statement.where(or_(*filters))
            
        # 兜底：如果没有任何确定的过滤条件但模型有字段，可能需要返回空集或默认隔离到本人
        if current_user_id is not None and user_id_col is not None:
             return statement.where(user_id_col == current_user_id)

        return statement

    def _coerce_value(self, column, value):
        """尝试将字符串值转换为列对应的 Python 类型"""
        if isinstance(value, list):
            return [self._coerce_single_value(column, v) for v in value]
        return self._coerce_single_value(column, value)

    def _coerce_single_value(self, column, value):
        if not isinstance(value, str):
            return value
        
        # 简单转换逻辑，可根据需要扩展
        lowered = value.strip().lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if value.isdigit():
            return int(value)
        return value
