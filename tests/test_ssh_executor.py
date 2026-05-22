from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SSH 执行器单元测试（mock SSH 连接）
"""

import pytest
from unittest.mock import MagicMock, patch

from data.models import ExecutorResult, ProgressInfo
from executors.ssh_executor import SSHExecutor
from utils.ssh_helpers import HostCredentials


class TestSSHExecutor:
    """SSHExecutor 测试"""

    @pytest.fixture
    def credentials(self):
        return HostCredentials(
            host="192.168.1.100",
            port=22,
            username="root",
            password="test_pass",
        )

    def test_create_executor(self, credentials):
        """测试创建执行器"""
        executor = SSHExecutor(credentials)
        assert executor._credentials.host == "192.168.1.100"
        assert executor.is_cancelled() is False

    def test_cancel(self, credentials):
        """测试取消"""
        executor = SSHExecutor(credentials)
        executor.cancel()
        assert executor.is_cancelled() is True

    def test_progress_callback(self, credentials):
        """测试进度回调"""
        executor = SSHExecutor(credentials)
        received = []

        executor.on_progress(lambda p: received.append(p))
        executor._emit_progress(ProgressInfo(current=50, total=100, message="test"))

        assert len(received) == 1
        assert received[0].current == 50

    @patch("executors.ssh_executor.paramiko.SSHClient")
    def test_execute_command(self, mock_client_cls, credentials):
        """测试执行命令（mock）"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # Mock exec_command 返回
        mock_stdout = MagicMock()
        mock_stdout.channel.recv_exit_status.return_value = 0
        mock_stdout.read.return_value = b"hello world\n"
        mock_stderr = MagicMock()
        mock_stderr.read.return_value = b""

        mock_client.exec_command.return_value = (MagicMock(), mock_stdout, mock_stderr)

        executor = SSHExecutor(credentials)
        executor.connect()
        result = executor.execute(command="echo hello", timeout=30)

        assert result.success is True
        assert result.exit_code == 0
        assert "hello world" in result.stdout

        executor.close()
