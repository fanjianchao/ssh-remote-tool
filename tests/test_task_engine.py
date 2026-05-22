from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务引擎单元测试（编排逻辑、状态流转）
"""

import pytest

from data.models import ServiceError
from data.task_repository import TaskRepository


class TestTaskRepository:
    """TaskRepository 测试"""

    def test_create_task(self, db_session, sample_task_dict):
        """测试创建任务"""
        repo = TaskRepository(db_session)
        task = repo.create(sample_task_dict)

        assert task.id is not None
        assert task.name == "重启服务"
        assert len(task.steps) == 2

    def test_get_by_id(self, db_session, sample_task_dict):
        """测试按 ID 查询"""
        repo = TaskRepository(db_session)
        created = repo.create(sample_task_dict)

        task = repo.get_by_id(created.id)
        assert task is not None
        assert len(task.steps) == 2

    def test_get_all(self, db_session, sample_task_dict):
        """测试获取全部任务"""
        repo = TaskRepository(db_session)
        repo.create(sample_task_dict)

        tasks = repo.get_all()
        assert len(tasks) == 1

    def test_update_task(self, db_session, sample_task_dict):
        """测试更新任务"""
        repo = TaskRepository(db_session)
        task = repo.create(sample_task_dict)

        updated = repo.update(task.id, {"name": "更新后的任务"})
        assert updated.name == "更新后的任务"

    def test_delete_task(self, db_session, sample_task_dict):
        """测试删除任务"""
        repo = TaskRepository(db_session)
        task = repo.create(sample_task_dict)

        assert repo.delete(task.id) is True
        assert repo.get_by_id(task.id) is None

    def test_duplicate_task(self, db_session, sample_task_dict):
        """测试复制任务"""
        repo = TaskRepository(db_session)
        task = repo.create(sample_task_dict)

        dup = repo.duplicate(task.id)
        assert dup.id != task.id
        assert "副本" in dup.name
        assert len(dup.steps) == 2

    def test_duplicate_task_not_found(self, db_session):
        """测试复制不存在的任务"""
        repo = TaskRepository(db_session)
        with pytest.raises(ServiceError):
            repo.duplicate(99999)

    def test_export_import_task(self, db_session, sample_task_dict):
        """测试导出导入任务"""
        repo = TaskRepository(db_session)
        task = repo.create(sample_task_dict)

        exported = repo.export_task(task.id)
        assert exported["name"] == "重启服务"
        assert len(exported["steps"]) == 2

        imported = repo.import_task(exported)
        assert imported.id != task.id
        assert imported.name == "重启服务"
