from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SSH 命令执行器

连接远程主机、执行命令、捕获输出、超时控制。
"""

import time

import paramiko

from executors.base_executor import BaseExecutor
from data.models import ExecutorResult, ProgressInfo
from utils.logger import setup_logger
from utils.ssh_helpers import HostCredentials

logger = setup_logger("ssh_executor")


class SSHExecutor(BaseExecutor):
    """SSH 命令执行器"""

    def __init__(self, credentials: HostCredentials, connection_pool=None):
        """
        Args:
            credentials: 主机连接凭证
            connection_pool: 可选的连接池（用于连接复用）
        """
        super().__init__(credentials)
        self._client: paramiko.SSHClient | None = None
        self._connection_pool = connection_pool
        self._pooled = False  # 标记是否从连接池获取的连接

    def connect(self) -> None:
        """建立 SSH 连接"""
        if self._connection_pool:
            self._client = self._connection_pool.get_connection(self._credentials)
            self._pooled = True
        else:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs = {
                "hostname": self._credentials.host,
                "port": self._credentials.port,
                "username": self._credentials.username,
                "timeout": 10,
                "banner_timeout": 10,
                "auth_timeout": 10,
                "look_for_keys": False,
            }

            if self._credentials.key_path:
                connect_kwargs["key_filename"] = self._credentials.key_path
                if self._credentials.key_password:
                    connect_kwargs["password"] = self._credentials.key_password
            else:
                connect_kwargs["password"] = self._credentials.password

            self._client.connect(**connect_kwargs)

        self._emit_progress(ProgressInfo(current=0, total=1, message="已连接"))
        logger.info(f"SSH connected: {self._credentials.host}:{self._credentials.port}")

    def execute(self, **kwargs) -> ExecutorResult:
        """
        执行远程命令。

        Args:
            command: Shell 命令
            timeout: 超时秒数（0=无限等待）
            workdir: 远程工作目录

        Returns:
            ExecutorResult
        """
        if self._client is None:
            self.connect()

        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 30) or 0
        workdir = kwargs.get("workdir", "~")

        if not command:
            return ExecutorResult(
                success=False,
                error="Empty command",
            )

        # 切换工作目录并执行命令
        full_command = f"cd {workdir} && {command}" if workdir != "~" else command

        self._emit_progress(ProgressInfo(current=0, total=1, message="执行中..."))
        logger.debug(f"Executing on {self._credentials.host}: {command}")

        result = ExecutorResult()
        start_time = time.time()

        try:
            stdin, stdout, stderr = self._client.exec_command(
                full_command,
                timeout=timeout if timeout > 0 else None,
                get_pty=True,
            )

            # 读取输出（实时逐行读取，支持取消）
            exit_code = stdout.channel.recv_exit_status()

            stdout_text = stdout.read().decode("utf-8", errors="replace")
            stderr_text = stderr.read().decode("utf-8", errors="replace")

            duration_ms = int((time.time() - start_time) * 1000)

            result.success = exit_code == 0
            result.exit_code = exit_code
            result.stdout = stdout_text
            result.stderr = stderr_text
            result.duration_ms = duration_ms

            if not result.success:
                result.error = f"Command exited with code {exit_code}"

        except paramiko.SSHException as e:
            result.success = False
            result.error = f"SSH error: {e}"
            result.duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"SSH execute error on {self._credentials.host}: {e}")
        except Exception as e:
            error_str = str(e)
            result.success = False
            result.duration_ms = int((time.time() - start_time) * 1000)

            if "timed out" in error_str.lower():
                result.timed_out = True
                result.error = f"Command timed out after {timeout}s"
            else:
                result.error = f"Execution error: {e}"
                logger.error(f"Execute error on {self._credentials.host}: {e}")

        self._emit_progress(ProgressInfo(
            current=1, total=1,
            message="完成" if result.success else result.error or "失败",
        ))
        return result

    def cancel(self) -> None:
        """取消执行并关闭连接"""
        super().cancel()
        if self._client:
            try:
                transport = self._client.get_transport()
                if transport and transport.is_active():
                    transport.close()
            except Exception:
                pass

    def close(self) -> None:
        """关闭连接"""
        if self._client:
            if self._pooled and self._connection_pool:
                self._connection_pool.return_connection(self._credentials, self._client)
            else:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None
            logger.debug(f"SSH closed: {self._credentials.host}:{self._credentials.port}")
