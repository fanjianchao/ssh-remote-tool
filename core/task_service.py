from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务编排业务逻辑

创建/编辑/删除任务流、步骤排序、校验。
"""

from typing import Optional

from data.models import Host, Task, ValidationResult, ServiceError
from data.task_repository import TaskRepository
from data.host_repository import HostRepository
from data.database import get_db
from utils.logger import setup_logger

logger = setup_logger("task_service")


class TaskService:
    """任务编排服务"""

    def __init__(self):
        pass

    def _generate_unique_name(self, base: str = "新建任务", suffix: str = "") -> str:
        """
        生成不重复的任务名称。

        - 无 suffix 时：'新建任务1', '新建任务2' ...
        - 有 suffix 时：'原名 导入', '原名 导入1', '原名 导入2' ...
        """
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            existing = {t.name for t in repo.get_all()}
        if suffix:
            # 带后缀模式：优先尝试 base + " " + suffix
            candidate = f"{base} {suffix}"
            if candidate not in existing:
                return candidate
            n = 1
            while f"{candidate}{n}" in existing:
                n += 1
            return f"{candidate}{n}"
        else:
            # 数字后缀模式（原有行为）
            n = 1
            while f"{base}{n}" in existing:
                n += 1
            return f"{base}{n}"

    def create_task(self, task_info: dict) -> Task:
        """
        创建任务。自动为 steps 分配 order_index。

        Args:
            task_info: 任务信息，包含 "name", "description", "steps"

        Returns:
            Task ORM 对象
        """
        if not task_info.get("name"):
            raise ServiceError("VALIDATION_ERROR", "任务名称不能为空")

        # 分配 order_index
        steps = task_info.get("steps", [])
        for idx, step in enumerate(steps):
            step["order_index"] = idx

        # 校验 target_host_ids 有效性
        self._validate_target_hosts(steps)

        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            task = repo.create(task_info)
            # 在 session 内触发 steps 加载，确保数据在 session 外可用
            list(task.steps)
            return task

    def get_task(self, task_id: int) -> Task:
        """查询任务（含步骤）"""
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            task = repo.get_by_id(task_id)
            if not task:
                raise ServiceError("TASK_NOT_FOUND", f"任务 ID {task_id} 不存在")
            # 显式预加载 steps，确保 session 外可用
            list(task.steps)
            return task

    def list_tasks(self) -> list[Task]:
        """列出所有任务"""
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            return repo.get_all()

    def update_task(self, task_id: int, task_info: dict) -> Task:
        """更新任务（steps 全量替换）"""
        # 分配 order_index
        steps = task_info.get("steps", [])
        for idx, step in enumerate(steps):
            step["order_index"] = idx

        self._validate_target_hosts(steps)

        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            task = repo.update(task_id, task_info)
            # 刷新 task 并在 session 内触发 steps 加载
            session.refresh(task)
            list(task.steps)
            return task

    def delete_task(self, task_id: int) -> bool:
        """删除任务"""
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            return repo.delete(task_id)

    def duplicate_task(self, task_id: int) -> Task:
        """复制任务"""
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            new_task = repo.duplicate(task_id)
            # 在 session 内预加载 steps，避免 DetachedInstanceError
            _ = new_task.steps
            return new_task

    def validate_task(self, task_id: int) -> ValidationResult:
        """校验任务配置完整性"""
        task = self.get_task(task_id)
        result = ValidationResult(valid=True)

        if not task.steps:
            result.valid = False
            result.errors.append("任务没有配置任何步骤")

        for idx, step in enumerate(task.steps):
            step_errors = self._validate_step(step, idx)
            result.errors.extend(step_errors)

        result.valid = len(result.errors) == 0
        return result

    def export_task(self, task_id: int) -> dict:
        """导出单个任务为字典（可序列化为 JSON）"""
        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            task_dict = repo.export_task(task_id)
            return task_dict

    def import_task(self, task_data: dict) -> Task:
        """
        从字典导入任务（含完整校验）。

        Args:
            task_data: 任务字典，含 name, description, steps 等字段

        Returns:
            导入后的 Task ORM 对象

        Raises:
            ServiceError: 校验失败或数据格式错误
        """
        # 1. 基础字段校验
        if not task_data.get("name"):
            raise ServiceError("VALIDATION_ERROR", "任务名称不能为空")

        steps = task_data.get("steps", [])
        if not steps:
            raise ServiceError("VALIDATION_ERROR", "任务没有配置任何步骤")

        # 2. 校验每个步骤
        for idx, step in enumerate(steps):
            errors = self._validate_step_dict(step, idx)
            if errors:
                raise ServiceError("VALIDATION_ERROR", "\n".join(errors))

        # 3. 校验目标主机 ID 有效性
        self._validate_target_hosts(steps)

        # 4. 调用 repository 导入（清除 id 和 task_id，重新生成）
        task_data.pop("id", None)
        for step in steps:
            step.pop("id", None)
            step.pop("task_id", None)

        with get_db().session_scope() as session:
            repo = TaskRepository(session)
            task = repo.import_task(task_data)
            list(task.steps)
            return task

    def _validate_step_dict(self, step: dict, index: int) -> list[str]:
        """校验步骤字典（与 _validate_step 类似，但接收 dict 而非 ORM 对象）"""
        errors = []
        step_type = step.get("step_type", "")

        if not step.get("name"):
            errors.append(f"步骤 {index + 1}: 名称不能为空")

        if step_type == "ssh_command":
            if not step.get("command"):
                errors.append(f"步骤 '{step.get('name') or index + 1}': 命令不能为空")
        elif step_type in ("sftp_upload", "sftp_download"):
            if not step.get("local_path"):
                errors.append(f"步骤 '{step.get('name') or index + 1}': 本地路径不能为空")
            if not step.get("remote_path"):
                errors.append(f"步骤 '{step.get('name') or index + 1}': 远程路径不能为空")

        return errors

    def get_available_hosts(self) -> list[Host]:
        """获取所有可用主机（供任务编辑时选择）"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.get_all()

    def _validate_target_hosts(self, steps: list[dict]) -> None:
        """校验所有步骤的 target_host_ids 有效性"""
        all_host_ids = set()
        for step in steps:
            for hid in step.get("target_host_ids", []):
                all_host_ids.add(hid)

        if not all_host_ids:
            return

        with get_db().session_scope() as session:
            repo = HostRepository(session)
            existing_ids = {h.id for h in repo.get_all()}
            invalid = all_host_ids - existing_ids
            if invalid:
                raise ServiceError(
                    "VALIDATION_ERROR",
                    f"以下目标主机 ID 不存在: {invalid}",
                )

    def _validate_step(self, step, index: int) -> list[str]:
        """校验单个步骤"""
        errors = []
        step_type = step.step_type

        if not step.name:
            errors.append(f"步骤 {index + 1}: 名称不能为空")

        if step_type == "ssh_command":
            if not step.command:
                errors.append(f"步骤 '{step.name or index + 1}': 命令不能为空")
        elif step_type in ("sftp_upload", "sftp_download"):
            if not step.local_path:
                errors.append(f"步骤 '{step.name or index + 1}': 本地路径不能为空")
            if not step.remote_path:
                errors.append(f"步骤 '{step.name or index + 1}': 远程路径不能为空")

        return errors
