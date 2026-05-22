from __future__ import annotations
# -*- coding: utf-8 -*-
"""
步骤模板业务逻辑

保存/列表/删除步骤模板，将模板转为可插入任务的步骤字典。
"""

from data.models import StepTemplate, ServiceError
from data.step_template_repository import StepTemplateRepository
from data.database import get_db
from utils.logger import setup_logger

logger = setup_logger("step_template_service")


class StepTemplateService:
    """步骤模板服务"""

    def __init__(self):
        pass

    def save_template(self, step_dict: dict, template_name: str) -> dict:
        """
        从步骤字典创建模板。

        Args:
            step_dict: 步骤数据字典（来自 _steps 列表）
            template_name: 模板名称

        Returns:
            创建的模板字典（通过 to_dict()）
        """
        if not template_name.strip():
            raise ServiceError("VALIDATION_ERROR", "模板名称不能为空")

        template_info = {
            "name": template_name.strip(),
            "step_type": step_dict.get("step_type", "ssh_command"),
            "command": step_dict.get("command", ""),
            "timeout": step_dict.get("timeout", 30),
            "workdir": step_dict.get("workdir", "~"),
            "local_path": step_dict.get("local_path", ""),
            "remote_path": step_dict.get("remote_path", ""),
            "continue_on_error": step_dict.get("continue_on_error", False),
        }

        template_id = None
        with get_db().session_scope() as session:
            repo = StepTemplateRepository(session)
            template = repo.create(template_info)
            template_id = template.id

        logger.info(f"Saved template: id={template_id}, name={template_name.strip()}")

        # 重新查询并返回字典，避免 session 关闭后 ORM 对象的潜在问题
        with get_db().session_scope() as session:
            repo = StepTemplateRepository(session)
            template = repo.get_by_id(template_id)
            if template:
                return template.to_dict()
            return {"id": template_id, "name": template_name.strip()}

    def list_templates(self) -> list[dict]:
        """列出所有模板，返回字典列表"""
        with get_db().session_scope() as session:
            repo = StepTemplateRepository(session)
            templates = repo.get_all()
            result = [t.to_dict() for t in templates]
            logger.debug(f"Listed {len(result)} templates")
            return result

    def delete_template(self, template_id: int) -> bool:
        """删除模板"""
        with get_db().session_scope() as session:
            repo = StepTemplateRepository(session)
            return repo.delete(template_id)

    def get_as_step_dict(self, template_id: int) -> dict:
        """
        将模板转为可插入 _steps 的步骤字典。

        Returns:
            包含 id=None, task_id=None, order_index=0, target_host_ids=[] 的步骤字典
        """
        with get_db().session_scope() as session:
            repo = StepTemplateRepository(session)
            template = repo.get_by_id(template_id)
            if not template:
                raise ServiceError("TEMPLATE_NOT_FOUND", f"模板 ID {template_id} 不存在")

            return {
                "id": None,
                "task_id": None,
                "order_index": 0,
                "step_type": template.step_type,
                "name": template.name,
                "command": template.command,
                "timeout": template.timeout,
                "workdir": template.workdir,
                "local_path": template.local_path,
                "remote_path": template.remote_path,
                "continue_on_error": template.continue_on_error if template.continue_on_error is not None else False,
                "target_host_ids": [],
            }
