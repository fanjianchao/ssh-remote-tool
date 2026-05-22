from __future__ import annotations
# -*- coding: utf-8 -*-
"""
执行器基类

定义 execute() 接口、进度回调、取消机制。
所有执行器（SSH、SFTP）的抽象基类。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from utils.ssh_helpers import HostCredentials
from data.models import ExecutorResult, ProgressInfo


class BaseExecutor(ABC):
    """
    所有执行器的基类，定义统一的接口协议。

    生命周期: connect() → execute() → close()
    """

    def __init__(self, credentials: HostCredentials):
        self._credentials = credentials
        self._cancelled = False
        self._progress_callbacks: list[Callable[[ProgressInfo], None]] = []

    @abstractmethod
    def connect(self) -> None:
        """
        建立 SSH/SFTP 连接。

        Raises:
            ConnectionError: 连接失败
        """
        ...

    @abstractmethod
    def execute(self, **kwargs) -> ExecutorResult:
        """
        执行具体操作。子类实现不同的执行逻辑。

        Args:
            **kwargs: 操作参数（由 step_dict 中的专有字段传入）

        Returns:
            ExecutorResult: 执行结果
        """
        ...

    def cancel(self) -> None:
        """
        设置取消标志。
        子类 execute() 中需定期检查此标志并提前退出。
        同时应关闭底层 SSH 通道强制中断。
        """
        self._cancelled = True

    def close(self) -> None:
        """关闭连接，释放资源"""
        pass

    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._cancelled

    # ============ 进度回调 ============

    def on_progress(self, callback: Callable[[ProgressInfo], None]) -> None:
        """
        注册进度回调函数。

        Args:
            callback: 接收 ProgressInfo 的回调函数
        """
        self._progress_callbacks.append(callback)

    def _emit_progress(self, progress: ProgressInfo) -> None:
        """触发所有进度回调"""
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception:
                pass  # 回调异常不影响执行流程
