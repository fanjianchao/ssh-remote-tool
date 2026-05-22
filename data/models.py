from __future__ import annotations
# -*- coding: utf-8 -*-
"""
数据模型定义

Host、Task、TaskStep、ExecutionResult 等 ORM 模型，
以及 OperationResult、ServiceError 等通用数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Generic, Optional, TypeVar

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Boolean,
    ForeignKey, JSON, Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ============ SQLAlchemy 基类 ============

class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass


# ============ 通用数据结构 ============

T = TypeVar("T")


class ServiceError(Exception):
    """统一业务层错误"""

    def __init__(self, code: str, message: str, detail: str = ""):
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(f"[{code}] {message}")


@dataclass
class OperationResult(Generic[T]):
    """统一操作结果"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

    @staticmethod
    def ok(data: T) -> "OperationResult[T]":
        return OperationResult(success=True, data=data)

    @staticmethod
    def fail(error: str) -> "OperationResult[T]":
        return OperationResult(success=False, error=error)


@dataclass
class ConnTestResult:
    """连接测试结果"""
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class ImportResult:
    """批量导入结果"""
    success_count: int = 0
    fail_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """校验结果"""
    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ExecutorResult:
    """执行器执行结果"""
    success: bool = False
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: Optional[str] = None
    timed_out: bool = False
    # SFTP 专有字段
    files_transferred: int = 0
    bytes_transferred: int = 0
    skipped_files: list[str] = field(default_factory=list)


@dataclass
class ProgressInfo:
    """进度信息"""
    current: int = 0
    total: int = 0
    message: str = ""
    speed: Optional[int] = None  # 传输速度 Bps


# ============ ORM 模型 ============

class Host(Base):
    """主机配置表"""
    __tablename__ = "hosts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, comment="主机别名")
    host = Column(String(255), nullable=False, comment="IP 或域名")
    port = Column(Integer, nullable=False, default=22, comment="SSH 端口")
    username = Column(String(128), nullable=False, comment="登录用户名")
    auth_type = Column(String(16), nullable=False, default="password", comment="认证方式")
    password_encrypted = Column(Text, default="", comment="加密后的密码")
    key_path = Column(String(512), default="", comment="私钥文件路径")
    group_name = Column(String(64), nullable=False, default="默认", comment="分组名")
    remark = Column(Text, default="", comment="备注")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    def to_dict(self) -> dict:
        """转换为字典（密码字段保留加密格式）"""
        return {
            "id": self.id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "auth_type": self.auth_type,
            "password_encrypted": self.password_encrypted,
            "key_path": self.key_path,
            "group": self.group_name,
            "remark": self.remark,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Task(Base):
    """任务配置表"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment="任务名称")
    description = Column(Text, default="", comment="任务描述")
    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关系
    steps = relationship(
        "TaskStep",
        back_populates="task",
        order_by="TaskStep.order_index",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskStep(Base):
    """任务步骤表"""
    __tablename__ = "task_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    order_index = Column(Integer, nullable=False, default=0, comment="执行顺序")
    step_type = Column(String(32), nullable=False, comment="步骤类型")
    name = Column(String(256), nullable=False, default="", comment="步骤名称")

    # SSH 命令执行字段
    command = Column(Text, default="", comment="Shell 命令")
    timeout = Column(Integer, default=30, comment="超时秒数")
    workdir = Column(String(512), default="~", comment="远程工作目录")

    # SFTP 传输字段
    local_path = Column(String(1024), default="", comment="本地路径")
    remote_path = Column(String(1024), default="", comment="远程路径")

    # 目标主机
    target_host_ids = Column(JSON, default=list, comment="目标主机 ID 列表")

    # 执行策略
    continue_on_error = Column(Boolean, default=False, comment="步骤失败后是否继续执行下一步")

    # 关系
    task = relationship("Task", back_populates="steps")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "order_index": self.order_index,
            "step_type": self.step_type,
            "name": self.name,
            "command": self.command,
            "timeout": self.timeout,
            "workdir": self.workdir,
            "local_path": self.local_path,
            "remote_path": self.remote_path,
            "target_host_ids": self.target_host_ids or [],
            "continue_on_error": self.continue_on_error if self.continue_on_error is not None else False,
        }


class StepTemplate(Base):
    """步骤模板表"""
    __tablename__ = "step_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(256), nullable=False, comment="模板名称")
    step_type = Column(String(32), nullable=False, comment="步骤类型")

    # SSH 命令执行字段
    command = Column(Text, default="", comment="Shell 命令")
    timeout = Column(Integer, default=30, comment="超时秒数")
    workdir = Column(String(512), default="~", comment="远程工作目录")

    # SFTP 传输字段
    local_path = Column(String(1024), default="", comment="本地路径")
    remote_path = Column(String(1024), default="", comment="远程路径")

    # 执行策略
    continue_on_error = Column(Boolean, default=False, comment="步骤失败后是否继续执行下一步")

    created_at = Column(DateTime, nullable=False, default=datetime.now, comment="创建时间")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "step_type": self.step_type,
            "command": self.command,
            "timeout": self.timeout,
            "workdir": self.workdir,
            "local_path": self.local_path,
            "remote_path": self.remote_path,
            "continue_on_error": self.continue_on_error if self.continue_on_error is not None else False,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ExecutionResult(Base):
    """执行结果记录表"""
    __tablename__ = "execution_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    host_id = Column(Integer, ForeignKey("hosts.id", ondelete="SET NULL"), nullable=True)
    step_index = Column(Integer, nullable=False, comment="步骤索引")
    step_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="pending", comment="执行状态")
    exit_code = Column(Integer, default=-1)
    stdout = Column(Text, default="")
    stderr = Column(Text, default="")
    error = Column(Text, default="")
    duration_ms = Column(Integer, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.now)
