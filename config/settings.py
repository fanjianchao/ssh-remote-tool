from __future__ import annotations
# -*- coding: utf-8 -*-
"""
全局配置管理

所有可配置项集中管理，支持从环境变量和配置文件覆盖默认值。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    """应用全局配置"""

    # === 应用信息 ===
    APP_NAME: str = "SSH Remote Tool"
    APP_VERSION: str = "0.1.0"

    # === 数据库配置 ===
    DB_DIR: str = str(Path.home() / ".ssh-remote-tool")
    DB_NAME: str = "ssh_manager.db"

    # === 日志配置 ===
    LOG_DIR: str = ""
    LOG_LEVEL: str = "INFO"
    LOG_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT: int = 30
    LOG_FORMAT: str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # === SSH 默认配置 ===
    SSH_DEFAULT_PORT: int = 22
    SSH_CONNECT_TIMEOUT: int = 10
    SSH_EXEC_TIMEOUT: int = 30
    SSH_KEEPALIVE_INTERVAL: int = 30
    SSH_MAX_POOL_SIZE: int = 10

    # === SFTP 配置 ===
    SFTP_BUFFER_SIZE: int = 64 * 1024  # 64KB

    # === 加密配置 ===
    ENCRYPTION_KEY_SOURCE: str = "machine"  # "machine" | "password"

    # === UI 配置 ===
    WINDOW_WIDTH: int = 1200
    WINDOW_HEIGHT: int = 800
    WINDOW_MIN_WIDTH: int = 900
    WINDOW_MIN_HEIGHT: int = 600
    THEME: str = "light"  # "dark" | "light"

    # === 线程池配置 ===
    MAX_WORKERS: int = 8

    @property
    def db_path(self) -> str:
        """获取数据库完整路径"""
        Path(self.DB_DIR).mkdir(parents=True, exist_ok=True)
        return str(Path(self.DB_DIR) / self.DB_NAME)

    @property
    def log_dir(self) -> str:
        """获取日志目录路径"""
        if not self.LOG_DIR:
            self.LOG_DIR = str(Path(self.DB_DIR) / "logs")
        Path(self.LOG_DIR).mkdir(parents=True, exist_ok=True)
        return self.LOG_DIR

    @classmethod
    def from_env(cls) -> "Settings":
        """从环境变量创建配置（环境变量覆盖默认值）"""
        settings = cls()
        env_mapping = {
            "SRT_DB_DIR": "DB_DIR",
            "SRT_LOG_LEVEL": "LOG_LEVEL",
            "SRT_LOG_DIR": "LOG_DIR",
            "SRT_SSH_TIMEOUT": "SSH_CONNECT_TIMEOUT",
            "SRT_SSH_MAX_POOL": "SSH_MAX_POOL_SIZE",
            "SRT_THEME": "THEME",
            "SRT_MAX_WORKERS": "MAX_WORKERS",
        }
        for env_key, attr_name in env_mapping.items():
            value = os.environ.get(env_key)
            if value is not None:
                current_type = type(getattr(settings, attr_name))
                try:
                    setattr(settings, attr_name, current_type(value))
                except (ValueError, TypeError):
                    pass
        return settings


# 全局单例
_settings: Settings | None = None


def get_settings() -> Settings:
    """获取全局配置单例"""
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings
