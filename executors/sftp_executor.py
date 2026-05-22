from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SFTP 文件传输器

上传/下载文件、目录递归传输、进度上报。
"""

import os
import time

import paramiko

from executors.base_executor import BaseExecutor
from data.models import ExecutorResult, ProgressInfo
from utils.logger import setup_logger
from utils.ssh_helpers import HostCredentials

logger = setup_logger("sftp_executor")


class SFTPExecutor(BaseExecutor):
    """SFTP 文件传输执行器"""

    def __init__(self, credentials: HostCredentials, connection_pool=None):
        super().__init__(credentials)
        self._client: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None
        self._connection_pool = connection_pool
        self._pooled = False

    def connect(self) -> None:
        """建立 SSH 连接并打开 SFTP 通道"""
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

        self._sftp = self._client.open_sftp()
        self._emit_progress(ProgressInfo(current=0, total=1, message="SFTP 已连接"))
        logger.info(f"SFTP connected: {self._credentials.host}:{self._credentials.port}")

    def execute(self, **kwargs) -> ExecutorResult:
        """
        文件上传或下载。

        Args:
            local_path: 本地文件/目录路径
            remote_path: 远程路径
            direction: "upload" | "download"

        Returns:
            ExecutorResult
        """
        if self._sftp is None:
            self.connect()

        direction = kwargs.get("direction", "upload")
        local_path = kwargs.get("local_path", "")
        remote_path = kwargs.get("remote_path", "")

        if not local_path or not remote_path:
            return ExecutorResult(success=False, error="local_path and remote_path are required")

        # 规范化路径：确保远程路径使用正斜杠（Windows 环境下用户可能输入反斜杠）
        remote_path = remote_path.replace("\\", "/")
        local_path = local_path.replace("/", os.sep)

        logger.info(f"SFTP {direction}: local={local_path}, remote={remote_path}")

        result = ExecutorResult()
        start_time = time.time()

        try:
            if direction == "upload":
                self._upload(local_path, remote_path, result)
            elif direction == "download":
                self._download(local_path, remote_path, result)
            else:
                return ExecutorResult(success=False, error=f"Unknown direction: {direction}")

            result.success = True
        except Exception as e:
            import traceback
            result.success = False
            error_detail = f"{type(e).__name__}: {e}"
            result.error = f"SFTP {direction} error: {error_detail}"
            logger.error(f"SFTP {direction} error on {self._credentials.host}: {error_detail}\n{traceback.format_exc()}")

        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    def _upload(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """上传文件或目录"""
        if os.path.isdir(local_path):
            self._upload_dir(local_path, remote_path, result)
        else:
            self._upload_file(local_path, remote_path, result)

    def _upload_file(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """上传单个文件"""
        file_size = os.path.getsize(local_path)

        # 如果 remote_path 是远程已存在的目录，自动拼接本地文件名
        try:
            import stat as stat_module
            sftp_stat = self._sftp.stat(remote_path)
            if stat_module.S_ISDIR(sftp_stat.st_mode):
                filename = os.path.basename(local_path)
                remote_path = f"{remote_path.rstrip('/')}/{filename}"
                logger.info(f"Remote path is a directory, auto-appended filename: {remote_path}")
        except IOError:
            pass  # remote_path 不存在或不是目录，直接使用原路径

        # 确保远程目录存在（使用 rsplit 而非 os.path.dirname，避免 Windows 路径混用问题）
        remote_dir = remote_path.rsplit("/", 1)[0] if "/" in remote_path else ""
        if remote_dir:
            self._mkdir_p(remote_dir)

        def progress_callback(sent: int, total: int):
            if self.is_cancelled():
                raise InterruptedError("Transfer cancelled")
            speed = int(sent / max(time.time() - (self._transfer_start_time or time.time()), 0.001))
            self._emit_progress(ProgressInfo(
                current=sent, total=total,
                message=f"上传: {os.path.basename(local_path)}",
                speed=speed,
            ))

        self._transfer_start_time = time.time()
        logger.info(f"Uploading {local_path} -> {remote_path} (size={file_size})")
        self._sftp.put(local_path, remote_path, callback=progress_callback, confirm=False)
        result.files_transferred += 1
        result.bytes_transferred += file_size

    def _upload_dir(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """递归上传目录"""
        self._mkdir_p(remote_path)

        for item in os.listdir(local_path):
            local_item = os.path.join(local_path, item)
            remote_item = f"{remote_path}/{item}"

            if self.is_cancelled():
                raise InterruptedError("Transfer cancelled")

            if os.path.isdir(local_item):
                self._upload_dir(local_item, remote_item, result)
            else:
                self._upload_file(local_item, remote_item, result)

    def _download(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """下载文件或目录"""
        try:
            sftp_stat = self._sftp.stat(remote_path)
            import stat as stat_module
            if stat_module.S_ISDIR(sftp_stat.st_mode):
                self._download_dir(local_path, remote_path, result)
            else:
                self._download_file(local_path, remote_path, result)
        except IOError:
            # 可能是文件
            self._download_file(local_path, remote_path, result)

    def _download_file(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """下载单个文件"""
        # 如果 local_path 是已存在的本地目录，自动拼接远程文件名
        if os.path.isdir(local_path):
            remote_filename = remote_path.rsplit("/", 1)[-1] if "/" in remote_path else remote_path
            local_path = os.path.join(local_path, remote_filename)
            logger.info(f"Local path is a directory, auto-appended filename: {local_path}")

        # 确保本地目录存在
        local_dir = os.path.dirname(local_path)
        if local_dir:
            os.makedirs(local_dir, exist_ok=True)

        def progress_callback(sent: int, total: int):
            if self.is_cancelled():
                raise InterruptedError("Transfer cancelled")
            speed = int(sent / max(time.time() - (self._transfer_start_time or time.time()), 0.001))
            self._emit_progress(ProgressInfo(
                current=sent, total=total,
                message=f"下载: {os.path.basename(local_path)}",
                speed=speed,
            ))

        self._transfer_start_time = time.time()
        self._sftp.get(remote_path, local_path, callback=progress_callback)
        result.files_transferred += 1
        result.bytes_transferred += os.path.getsize(local_path)

    def _download_dir(self, local_path: str, remote_path: str, result: ExecutorResult) -> None:
        """递归下载目录"""
        os.makedirs(local_path, exist_ok=True)

        for item in self._sftp.listdir(remote_path):
            remote_item = f"{remote_path}/{item}"
            local_item = os.path.join(local_path, item)

            if self.is_cancelled():
                raise InterruptedError("Transfer cancelled")

            try:
                sftp_stat = self._sftp.stat(remote_item)
                import stat as stat_module
                if stat_module.S_ISDIR(sftp_stat.st_mode):
                    self._download_dir(local_item, remote_item, result)
                else:
                    self._download_file(local_item, remote_item, result)
            except IOError:
                result.skipped_files.append(remote_item)

    def _mkdir_p(self, remote_path: str) -> None:
        """递归创建远程目录（类似 mkdir -p）"""
        dirs = remote_path.split("/")
        current = ""
        for d in dirs:
            if not d:
                current = "/"
                continue
            current = f"{current}/{d}" if current != "/" else f"/{d}"
            try:
                self._sftp.stat(current)
            except IOError:
                try:
                    self._sftp.mkdir(current)
                    logger.debug(f"Created remote directory: {current}")
                except Exception as e:
                    logger.warning(f"Failed to create remote directory {current}: {e}")

    def cancel(self) -> None:
        """取消传输"""
        super().cancel()
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
        if self._client and not self._pooled:
            try:
                transport = self._client.get_transport()
                if transport and transport.is_active():
                    transport.close()
            except Exception:
                pass

    def close(self) -> None:
        """关闭连接"""
        if self._sftp:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None

        if self._client:
            if self._pooled and self._connection_pool:
                self._connection_pool.return_connection(self._credentials, self._client)
            else:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None

        logger.debug(f"SFTP closed: {self._credentials.host}:{self._credentials.port}")
