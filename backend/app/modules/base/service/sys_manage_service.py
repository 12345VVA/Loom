"""
系统日志、登录日志、参数配置服务
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import Session, select

from app.framework.controller_meta import CrudQuery
from app.modules.base.model.auth import PageResult
from app.modules.base.model.auth import User
from app.modules.base.model.sys import (
    SysLog,
    SysLogRead,
    SysLoginLog,
    SysLoginLogCreateRequest,
    SysLoginLogRead,
    SysLoginLogUpdateRequest,
    SysParam,
    SysParamCreateRequest,
    SysParamRead,
    SysParamUpdateRequest,
    SysSecurityLog,
    SysSecurityLogRead,
    SysSecurityLogCreateRequest,
)
from app.modules.base.service.admin_service import BaseAdminCrudService


LOG_KEEP_PARAM_KEY = "logKeep"
LOG_KEEP_PARAM_NAME = "日志保存天数"
DEFAULT_LOG_KEEP_DAYS = "7"


class SysParamService(BaseAdminCrudService):
    """参数配置服务"""

    def __init__(self, session: Session):
        super().__init__(session, SysParam)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[SysParamRead]:
        statement = select(SysParam)
        statement = self._apply_query(statement, SysParam, query, current_user=current_user, fallback_field="created_at")
        rows = list(self.session.exec(statement).all())
        return [self._build_read(row) for row in rows]

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[SysParamRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(SysParam)
        statement = self._apply_query(statement, SysParam, query, current_user=current_user, fallback_field="created_at")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_read(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> SysParamRead:
        row = self.session.get(SysParam, id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参数不存在")
        return self._build_read(row)

    def add(self, payload: SysParamCreateRequest) -> SysParamRead:
        exists = self.session.exec(select(SysParam).where(SysParam.key_name == payload.key_name)).first()
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="参数键已存在")
        row = SysParam(
            name=payload.name,
            key_name=payload.key_name,
            data=payload.data,
            data_type=payload.data_type,
            remark=payload.remark,
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def update(self, payload: SysParamUpdateRequest) -> SysParamRead:
        row = self.session.get(SysParam, payload.id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="参数不存在")
        duplicate = self.session.exec(
            select(SysParam).where((SysParam.id != payload.id) & (SysParam.key_name == payload.key_name))
        ).first()
        if duplicate:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="参数键已存在")
        row.name = payload.name
        row.key_name = payload.key_name
        row.data = payload.data
        row.data_type = payload.data_type
        row.remark = payload.remark
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def html_by_key(self, key: str) -> str:
        row = self.session.exec(select(SysParam).where(SysParam.key_name == key)).first()
        return row.data or "" if row else ""

    def get_value(self, key: str, default: str | None = None) -> str | None:
        row = self.session.exec(select(SysParam).where(SysParam.key_name == key)).first()
        if row is None:
            return default
        return row.data if row.data is not None else default

    def set_value(self, key: str, value: str, *, name: str | None = None, data_type: int = 0) -> SysParam:
        row = self.session.exec(select(SysParam).where(SysParam.key_name == key)).first()
        if row is None:
            row = SysParam(
                name=name or key,
                key_name=key,
                data=value,
                data_type=data_type,
                updated_at=datetime.utcnow(),
            )
        else:
            row.name = name or row.name
            row.data = value
            row.data_type = data_type
            row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    @staticmethod
    def _build_read(row: SysParam) -> SysParamRead:
        return SysParamRead.model_validate(row)


class SysLogService(BaseAdminCrudService):
    """系统日志服务"""

    def __init__(self, session: Session):
        super().__init__(session, SysLog)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[SysLogRead]:
        statement = select(SysLog)
        statement = self._apply_query(statement, SysLog, query, current_user=current_user, fallback_field="created_at")
        rows = list(self.session.exec(statement).all())
        return self._build_reads(rows)

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[SysLogRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(SysLog)
        statement = self._apply_query(statement, SysLog, query, current_user=current_user, fallback_field="created_at")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=self._build_reads(rows),
            total=total,
            page=page,
            page_size=page_size,
        )

    def clear(self) -> dict[str, Any]:
        for row in list(self.session.exec(select(SysLog)).all()):
            self.session.delete(row)
        self.session.commit()
        return {"success": True}

    def set_keep(self, payload: dict[str, Any]) -> dict[str, Any]:
        value = int(payload.get("value", DEFAULT_LOG_KEEP_DAYS))
        SysParamService(self.session).set_value(LOG_KEEP_PARAM_KEY, str(value), name=LOG_KEEP_PARAM_NAME)
        return {"success": True, "value": value}

    def get_keep(self) -> str:
        return SysParamService(self.session).get_value(LOG_KEEP_PARAM_KEY, DEFAULT_LOG_KEEP_DAYS) or DEFAULT_LOG_KEEP_DAYS

    def _build_reads(self, rows: list[SysLog]) -> list[SysLogRead]:
        user_ids = [row.user_id for row in rows if row.user_id]
        users = {}
        if user_ids:
            users = {
                user.id: user
                for user in self.session.exec(select(User).where(User.id.in_(user_ids))).all()
                if user.id is not None
            }
        return [
            SysLogRead(
                id=row.id,
                user_id=row.user_id,
                name=users.get(row.user_id).full_name if row.user_id in users else None,
                action=row.action,
                method=row.method,
                params=row.params,
                ip=row.ip,
                status=row.status,
                message=row.message,
                created_at=row.created_at,
            )
            for row in rows
        ]


class SysLoginLogService(BaseAdminCrudService):
    """登录日志服务"""

    def __init__(self, session: Session):
        super().__init__(session, SysLoginLog)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[SysLoginLogRead]:
        statement = select(SysLoginLog)
        statement = self._apply_query(statement, SysLoginLog, query, current_user=current_user, fallback_field="created_at")
        rows = list(self.session.exec(statement).all())
        return [self._build_read(row) for row in rows]

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[SysLoginLogRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(SysLoginLog)
        statement = self._apply_query(statement, SysLoginLog, query, current_user=current_user, fallback_field="created_at")
        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_read(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> SysLoginLogRead:
        row = self.session.get(SysLoginLog, id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="登录日志不存在")
        return self._build_read(row)

    def add(self, payload: SysLoginLogCreateRequest | dict[str, Any]) -> SysLoginLogRead:
        data = payload if isinstance(payload, SysLoginLogCreateRequest) else SysLoginLogCreateRequest(**payload)
        row = SysLoginLog(
            user_id=data.user_id,
            name=data.name,
            account=data.account,
            login_type=data.login_type,
            status=data.status,
            ip=data.ip,
            risk_hit=data.risk_hit,
            reason=data.reason,
            client_type=data.client_type,
            device_id=data.device_id,
            source_system=data.source_system,
            user_agent=data.user_agent,
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    def update(self, payload: SysLoginLogUpdateRequest | dict[str, Any]) -> SysLoginLogRead:
        data = payload if isinstance(payload, SysLoginLogUpdateRequest) else SysLoginLogUpdateRequest(**payload)
        row = self.session.get(SysLoginLog, data.id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="登录日志不存在")
        row.user_id = data.user_id
        row.name = data.name
        row.account = data.account
        row.login_type = data.login_type
        row.status = data.status
        row.ip = data.ip
        row.risk_hit = data.risk_hit
        row.reason = data.reason
        row.client_type = data.client_type
        row.device_id = data.device_id
        row.source_system = data.source_system
        row.user_agent = data.user_agent
        row.updated_at = datetime.utcnow()
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return self._build_read(row)

    @staticmethod
    def _build_read(row: SysLoginLog) -> SysLoginLogRead:
        return SysLoginLogRead.model_validate(row)

    def create_entry(
        self,
        *,
        user_id: int | None = None,
        name: str | None = None,
        account: str | None = None,
        login_type: str = "password",
        status: int = 1,
        ip: str | None = None,
        reason: str | None = None,
        risk_hit: int = 0,
        client_type: str | None = None,
        device_id: str | None = None,
        source_system: str | None = "管理后台",
        user_agent: str | None = None,
    ) -> None:
        row = SysLoginLog(
            user_id=user_id,
            name=name,
            account=account,
            login_type=login_type,
            status=status,
            ip=ip,
            risk_hit=risk_hit,
            reason=reason,
            client_type=client_type,
            device_id=device_id,
            source_system=source_system,
            user_agent=user_agent,
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()


class SysSecurityLogService(BaseAdminCrudService):
    """安全审计日志服务"""

    def __init__(self, session: Session):
        super().__init__(session, SysSecurityLog)

    def list(self, query: CrudQuery | None = None, current_user: User | None = None) -> list[SysSecurityLogRead]:
        statement = select(SysSecurityLog)
        statement = self._apply_query(statement, SysSecurityLog, query, current_user=current_user, fallback_field="created_at")
        # 按时间倒序排列（最新的在前）
        statement = statement.order_by(SysSecurityLog.created_at.desc())
        rows = list(self.session.exec(statement).all())
        return [self._build_read(row) for row in rows]

    def page(self, query: CrudQuery, current_user: User | None = None) -> PageResult[SysSecurityLogRead]:
        page = query.page or 1
        page_size = query.size or 10
        statement = select(SysSecurityLog)
        statement = self._apply_query(statement, SysSecurityLog, query, current_user=current_user, fallback_field="created_at")
        # 按时间倒序排列（最新的在前）
        statement = statement.order_by(SysSecurityLog.created_at.desc())

        count_statement = select(func.count()).select_from(statement.subquery())
        total = int(self.session.exec(count_statement).one())
        rows = list(self.session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all())
        return PageResult(
            items=[self._build_read(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    def info(self, id: int) -> SysSecurityLogRead:
        row = self.session.get(SysSecurityLog, id)
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="安全审计日志不存在")
        return self._build_read(row)

    @staticmethod
    def _build_read(row: SysSecurityLog) -> SysSecurityLogRead:
        return SysSecurityLogRead.model_validate(row)

    def create_entry(
        self,
        *,
        operator_id: int,
        operator_name: str,
        operator_ip: str | None = None,
        target_type: str,
        target_id: int | None = None,
        target_name: str | None = None,
        operation: str,
        module: str,
        resource_path: str | None = None,
        old_value: str | None = None,
        new_value: str | None = None,
        diff_data: str | None = None,
        business_type: str | None = None,
        request_id: str | None = None,
        status: int = 1,
        error_message: str | None = None,
        remark: str | None = None,
    ) -> SysSecurityLog:
        """
        创建安全审计日志记录

        Args:
            operator_id: 操作者用户ID
            operator_name: 操作者用户名
            operator_ip: 操作者IP地址
            target_type: 操作对象类型 (user/role/menu/department)
            target_id: 操作对象ID
            target_name: 操作对象名称
            operation: 操作类型 (create/update/delete/reset_password/assign_role/grant_permission)
            module: 所属模块 (user/role/menu/department)
            resource_path: 资源路径
            old_value: 变更前的数据（脱敏后）
            new_value: 变更后的数据（脱敏后）
            diff_data: 变更差异（JSON格式）
            business_type: 业务类型（用于分类查询）
            request_id: 关联请求ID
            status: 操作状态 (0=失败, 1=成功)
            error_message: 失败时的错误信息
            remark: 审计备注
        """
        row = SysSecurityLog(
            operator_id=operator_id,
            operator_name=operator_name,
            operator_ip=operator_ip,
            target_type=target_type,
            target_id=target_id,
            target_name=target_name,
            operation=operation,
            module=module,
            resource_path=resource_path,
            old_value=old_value,
            new_value=new_value,
            diff_data=diff_data,
            business_type=business_type,
            request_id=request_id,
            status=status,
            error_message=error_message,
            remark=remark,
            updated_at=datetime.utcnow(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row
