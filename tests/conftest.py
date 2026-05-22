from __future__ import annotations
# -*- coding: utf-8 -*-
"""
pytest fixtures

测试数据库、mock 连接等共享测试工具。
"""

import os
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from data.models import Base
from data.database import Database
from utils.crypto import CryptoUtils


@pytest.fixture
def db_path():
    """创建临时数据库文件"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


@pytest.fixture
def db_session(db_path):
    """创建测试数据库会话"""
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    session = session_factory()
    yield session

    session.rollback()
    session.close()
    engine.dispose()


@pytest.fixture
def crypto():
    """创建加密工具实例"""
    return CryptoUtils()


@pytest.fixture
def sample_host_dict():
    """示例主机配置"""
    return {
        "name": "测试服务器",
        "host": "192.168.1.100",
        "port": 22,
        "username": "root",
        "password": "test_password",
        "auth_type": "password",
        "group": "测试组",
        "remark": "用于测试",
    }


@pytest.fixture
def sample_task_dict():
    """示例任务配置"""
    return {
        "name": "重启服务",
        "description": "重启 Nginx 服务",
        "steps": [
            {
                "step_type": "ssh_command",
                "name": "停止 Nginx",
                "command": "systemctl stop nginx",
                "timeout": 30,
                "workdir": "~",
                "target_host_ids": [],
            },
            {
                "step_type": "ssh_command",
                "name": "启动 Nginx",
                "command": "systemctl start nginx",
                "timeout": 30,
                "workdir": "~",
                "target_host_ids": [],
            },
        ],
    }
