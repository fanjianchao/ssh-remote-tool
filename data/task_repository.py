from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务配置数据访问层

任务 CRUD 操作、复制、导入导出。
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from data.models import Task, TaskStep, ServiceError


class TaskRepository:
    """任务配置 Repository"""

    def __init__(self, session: Session):
        self._session = session

    def create(self, task_dict: dict) -> Task:
        """
        创建任务（含步骤）。

        Args:
            task_dict: 任务信息字典，包含 "name", "description", "steps"

        Returns:
            创建的 Task ORM 对象
        """
        task = Task(
            name=task_dict["name"],
            description=task_dict.get("description", ""),
        )
        self._session.add(task)
        self._session.flush()  # 获取 task.id

        # 创建步骤
        for idx, step_dict in enumerate(task_dict.get("steps", [])):
            step = TaskStep(
                task_id=task.id,
                order_index=step_dict.get("order_index", idx),
                step_type=step_dict["step_type"],
                name=step_dict.get("name", ""),
                command=step_dict.get("command", ""),
                timeout=step_dict.get("timeout", 30),
                workdir=step_dict.get("workdir", "~"),
                local_path=step_dict.get("local_path", ""),
                remote_path=step_dict.get("remote_path", ""),
                target_host_ids=step_dict.get("target_host_ids", []),
                continue_on_error=step_dict.get("continue_on_error", False),
            )
            self._session.add(step)

        self._session.flush()
        return task

    def get_by_id(self, task_id: int) -> Task | None:
        """按 ID 查询，同时加载关联的 steps"""
        task = self._session.execute(
            select(Task)
            .options(selectinload(Task.steps))
            .where(Task.id == task_id)
        ).scalar_one_or_none()
        return task

    def get_all(self) -> list[Task]:
        """返回全部任务列表（不加载 steps，仅列表摘要）"""
        stmt = select(Task).order_by(Task.updated_at.desc())
        return list(self._session.execute(stmt).scalars().all())

    def update(self, task_id: int, task_dict: dict) -> Task:
        """
        更新任务及其步骤（steps 为全量替换）。

        Raises:
            ServiceError: 任务不存在
        """
        task = self.get_by_id(task_id)
        if not task:
            raise ServiceError("TASK_NOT_FOUND", f"任务 ID {task_id} 不存在")

        # 更新基本信息
        if "name" in task_dict:
            task.name = task_dict["name"]
        if "description" in task_dict:
            task.description = task_dict["description"]

        # 全量替换步骤
        if "steps" in task_dict:
            # 删除旧步骤
            self._session.execute(
                select(TaskStep).where(TaskStep.task_id == task_id)
            ).scalars().all()
            for old_step in task.steps:
                self._session.delete(old_step)

            # 创建新步骤
            for idx, step_dict in enumerate(task_dict["steps"]):
                step = TaskStep(
                    task_id=task.id,
                    order_index=step_dict.get("order_index", idx),
                    step_type=step_dict["step_type"],
                    name=step_dict.get("name", ""),
                    command=step_dict.get("command", ""),
                    timeout=step_dict.get("timeout", 30),
                    workdir=step_dict.get("workdir", "~"),
                    local_path=step_dict.get("local_path", ""),
                    remote_path=step_dict.get("remote_path", ""),
                    target_host_ids=step_dict.get("target_host_ids", []),
                    continue_on_error=step_dict.get("continue_on_error", False),
                )
                self._session.add(step)

        self._session.flush()
        return task

    def delete(self, task_id: int) -> bool:
        """删除任务（级联删除步骤）"""
        task = self.get_by_id(task_id)
        if not task:
            return False
        self._session.delete(task)
        self._session.flush()
        return True

    def duplicate(self, task_id: int) -> Task:
        """复制任务，返回新创建的 Task"""
        original = self.get_by_id(task_id)
        if not original:
            raise ServiceError("TASK_NOT_FOUND", f"任务 ID {task_id} 不存在")

        task_dict = {
            "name": f"{original.name} (副本)",
            "description": original.description,
            "steps": [s.to_dict() for s in original.steps],
        }
        # 清除步骤中的 id 和 task_id，让 create 重新分配
        for step in task_dict["steps"]:
            step.pop("id", None)
            step.pop("task_id", None)

        return self.create(task_dict)

    def export_task(self, task_id: int) -> dict:
        """导出单个任务为 JSON 友好的字典"""
        task = self.get_by_id(task_id)
        if not task:
            raise ServiceError("TASK_NOT_FOUND", f"任务 ID {task_id} 不存在")
        return task.to_dict()

    def import_task(self, task_data: dict) -> Task:
        """从字典导入任务"""
        # 清除可能存在的 id
        task_data.pop("id", None)
        for step in task_data.get("steps", []):
            step.pop("id", None)
            step.pop("task_id", None)
        return self.create(task_data)
