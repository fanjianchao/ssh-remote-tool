from __future__ import annotations
# -*- coding: utf-8 -*-
"""
步骤模板数据访问层

步骤模板 CRUD 操作。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from data.models import StepTemplate, ServiceError


class StepTemplateRepository:
    """步骤模板 Repository"""

    def __init__(self, session: Session):
        self._session = session

    def create(self, template_dict: dict) -> StepTemplate:
        """
        创建步骤模板。

        Args:
            template_dict: 模板信息字典

        Returns:
            创建的 StepTemplate ORM 对象
        """
        template = StepTemplate(
            name=template_dict["name"],
            step_type=template_dict["step_type"],
            command=template_dict.get("command", ""),
            timeout=template_dict.get("timeout", 30),
            workdir=template_dict.get("workdir", "~"),
            local_path=template_dict.get("local_path", ""),
            remote_path=template_dict.get("remote_path", ""),
            continue_on_error=template_dict.get("continue_on_error", False),
        )
        self._session.add(template)
        self._session.flush()
        return template

    def get_by_id(self, template_id: int) -> StepTemplate | None:
        """按 ID 查询"""
        return self._session.execute(
            select(StepTemplate).where(StepTemplate.id == template_id)
        ).scalar_one_or_none()

    def get_all(self) -> list[StepTemplate]:
        """返回全部模板列表，按创建时间倒序"""
        stmt = select(StepTemplate).order_by(StepTemplate.created_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def delete(self, template_id: int) -> bool:
        """删除模板，返回是否成功"""
        template = self.get_by_id(template_id)
        if not template:
            return False
        self._session.delete(template)
        self._session.flush()
        return True
