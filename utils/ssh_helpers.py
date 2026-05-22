from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SSH 辅助函数

连接池管理、连接复用、异常封装。
"""

import threading
from dataclasses import dataclass
from typing import Optional

import paramiko

from utils.logger import setup_logger

logger = setup_logger("ssh_helpers")


@dataclass
class HostCredentials:
    """已解密的主机连接凭证"""
    host: str
    port: int
    username: str
    password: Optional[str] = None
    key_path: Optional[str] = None
    key_password: Optional[str] = None


class SSHConnectionPool:
    """
    SSH 连接池，按 (host, port, username) 复用连接。

    线程安全，使用 threading.Lock 保护内部状态。
    """

    def __init__(
        self,
        max_pool_size: int = 10,
        connect_timeout: int = 10,
        keepalive_interval: int = 30,
    ):
        """
        Args:
            max_pool_size: 每个主机最大连接数
            connect_timeout: 连接超时（秒）
            keepalive_interval: 心跳间隔（秒）
        """
        self._max_pool_size = max_pool_size
        self._connect_timeout = connect_timeout
        self._keepalive_interval = keepalive_interval
        self._pool: dict[str, list[paramiko.SSHClient]] = {}
        self._lock = threading.Lock()

    def _make_key(self, credentials: HostCredentials) -> str:
        """生成连接池键"""
        return f"{credentials.host}:{credentials.port}:{credentials.username}"

    def get_connection(self, credentials: HostCredentials) -> paramiko.SSHClient:
        """
        获取连接。池中有可用连接则复用，否则新建。

        Args:
            credentials: 主机连接凭证

        Returns:
            已连接的 SSHClient 实例

        Raises:
            ConnectionError: 连接失败
        """
        pool_key = self._make_key(credentials)

        with self._lock:
            if pool_key in self._pool and self._pool[pool_key]:
                # 尝试从池中取出连接，检查是否存活
                client = self._pool[pool_key].pop()
                if self._is_alive(client):
                    logger.debug(f"Reused connection: {pool_key}")
                    return client
                else:
                    try:
                        client.close()
                    except Exception:
                        pass

        # 新建连接（在锁外执行，避免阻塞）
        client = self._create_connection(credentials)
        logger.debug(f"New connection created: {pool_key}")
        return client

    def _create_connection(self, credentials: HostCredentials) -> paramiko.SSHClient:
        """创建新的 SSH 连接"""
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            if credentials.key_path:
                # 密钥认证
                key_kwargs = {"key_filename": credentials.key_path}
                if credentials.key_password:
                    key_kwargs["password"] = credentials.key_password
                client.connect(
                    hostname=credentials.host,
                    port=credentials.port,
                    username=credentials.username,
                    timeout=self._connect_timeout,
                    banner_timeout=self._connect_timeout,
                    auth_timeout=self._connect_timeout,
                    look_for_keys=False,
                    **key_kwargs,
                )
            else:
                # 密码认证
                client.connect(
                    hostname=credentials.host,
                    port=credentials.port,
                    username=credentials.username,
                    password=credentials.password,
                    timeout=self._connect_timeout,
                    banner_timeout=self._connect_timeout,
                    auth_timeout=self._connect_timeout,
                    look_for_keys=False,
                )

            # 启用 keepalive
            transport = client.get_transport()
            if transport:
                transport.set_keepalive(self._keepalive_interval)

            return client

        except paramiko.AuthenticationException as e:
            client.close()
            raise ConnectionError(f"Authentication failed: {e}") from e
        except paramiko.SSHException as e:
            client.close()
            raise ConnectionError(f"SSH connection error: {e}") from e
        except Exception as e:
            client.close()
            raise ConnectionError(f"Connection failed: {e}") from e

    def _is_alive(self, client: paramiko.SSHClient) -> bool:
        """检查连接是否存活"""
        try:
            transport = client.get_transport()
            return transport is not None and transport.is_active()
        except Exception:
            return False

    def return_connection(self, credentials: HostCredentials, client: paramiko.SSHClient) -> None:
        """将连接归还到池中"""
        if not self._is_alive(client):
            try:
                client.close()
            except Exception:
                pass
            return

        pool_key = self._make_key(credentials)
        with self._lock:
            if pool_key not in self._pool:
                self._pool[pool_key] = []
            # 如果池未满，归还连接；否则关闭
            if len(self._pool[pool_key]) < self._max_pool_size:
                self._pool[pool_key].append(client)
                logger.debug(f"Connection returned to pool: {pool_key}")
            else:
                client.close()
                logger.debug(f"Pool full, connection closed: {pool_key}")

    def close_connection(self, credentials: HostCredentials) -> None:
        """主动关闭指定主机的所有连接"""
        pool_key = self._make_key(credentials)
        with self._lock:
            if pool_key in self._pool:
                for client in self._pool.pop(pool_key):
                    try:
                        client.close()
                    except Exception:
                        pass
                logger.debug(f"All connections closed for: {pool_key}")

    def close_all(self) -> None:
        """关闭池中所有连接"""
        with self._lock:
            for pool_key, clients in self._pool.items():
                for client in clients:
                    try:
                        client.close()
                    except Exception:
                        pass
                logger.debug(f"All connections closed for: {pool_key}")
            self._pool.clear()
            logger.info("All SSH connections closed")

    def __del__(self):
        """析构时关闭所有连接"""
        try:
            self.close_all()
        except Exception:
            pass
