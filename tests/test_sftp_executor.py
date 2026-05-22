from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SFTP 传输器单元测试（mock SFTP 通道）
"""

import pytest
from unittest.mock import MagicMock, patch

from executors.sftp_executor import SFTPExecutor
from utils.ssh_helpers import HostCredentials


class TestSFTPExecutor:
    """SFTPExecutor 测试"""

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
        executor = SFTPExecutor(credentials)
        assert executor._credentials.host == "192.168.1.100"

    def test_cancel(self, credentials):
        """测试取消"""
        executor = SFTPExecutor(credentials)
        executor.cancel()
        assert executor.is_cancelled() is True
