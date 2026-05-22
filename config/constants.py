from __future__ import annotations
# -*- coding: utf-8 -*-
"""
常量定义

状态枚举、UI 样式常量、默认值等。
"""

from enum import Enum


# ============ 主机相关常量 ============

class AuthType(str, Enum):
    """认证方式"""
    PASSWORD = "password"
    KEY = "key"


class HostStatus(str, Enum):
    """主机连接状态"""
    UNKNOWN = "unknown"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


# ============ 任务相关常量 ============

class StepType(str, Enum):
    """步骤类型"""
    SSH_COMMAND = "ssh_command"
    SFTP_UPLOAD = "sftp_upload"
    SFTP_DOWNLOAD = "sftp_download"


class StepStatus(str, Enum):
    """步骤执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """任务整体状态"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============ 默认值 ============

DEFAULT_SSH_PORT = 22
DEFAULT_SSH_TIMEOUT = 30
DEFAULT_WORKDIR = "~"
DEFAULT_GROUP = "默认"
DEFAULT_SFTP_BUFFER_SIZE = 64 * 1024  # 64KB

# ============ UI 常量 ============

PAGE_HOST_MANAGER = 0
PAGE_TASK_EDITOR = 1
PAGE_EXECUTION = 2

# 状态颜色 (QSS)
COLOR_SUCCESS = "#4CAF50"
COLOR_ERROR = "#F44336"
COLOR_WARNING = "#FF9800"
COLOR_INFO = "#2196F3"
COLOR_RUNNING = "#FFEB3B"
COLOR_PENDING = "#9E9E9E"

# ============ 错误码 ============

class ErrorCode(str, Enum):
    """统一错误码"""
    # 主机相关
    HOST_NOT_FOUND = "HOST_NOT_FOUND"
    DUPLICATE_NAME = "DUPLICATE_NAME"
    CONN_FAILED = "CONN_FAILED"
    CONN_TIMEOUT = "CONN_TIMEOUT"
    AUTH_FAILED = "AUTH_FAILED"

    # 任务相关
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_VALIDATION_ERROR = "TASK_VALIDATION_ERROR"
    TASK_ALREADY_RUNNING = "TASK_ALREADY_RUNNING"
    TASK_NOT_RUNNING = "TASK_NOT_RUNNING"

    # 执行相关
    EXEC_TIMEOUT = "EXEC_TIMEOUT"
    EXEC_CANCELLED = "EXEC_CANCELLED"
    SFTP_ERROR = "SFTP_ERROR"
    SSH_ERROR = "SSH_ERROR"

    # 通用
    VALIDATION_ERROR = "VALIDATION_ERROR"
    ENCRYPTION_ERROR = "ENCRYPTION_ERROR"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    IMPORT_ERROR = "IMPORT_ERROR"
    EXPORT_ERROR = "EXPORT_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
