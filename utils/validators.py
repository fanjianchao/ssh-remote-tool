from __future__ import annotations
# -*- coding: utf-8 -*-
"""
输入验证工具

IP/端口/路径格式校验、参数合法性检查。
"""

import re
from typing import Optional


class Validators:
    """输入验证器集合"""

    # IPv4 正则
    _IPV4_PATTERN = re.compile(
        r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
    )
    # 主机名正则
    _HOSTNAME_PATTERN = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$"
    )
    # 简单路径校验（不含非法字符）
    _INVALID_PATH_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')

    @staticmethod
    def validate_ip(value: str) -> tuple[bool, str]:
        """
        校验 IPv4 地址或主机名。

        Returns:
            (is_valid, error_msg)
        """
        if not value or not value.strip():
            return False, "IP 地址不能为空"

        value = value.strip()
        if Validators._IPV4_PATTERN.match(value):
            return True, ""

        if Validators._HOSTNAME_PATTERN.match(value):
            return True, ""

        return False, f"无效的 IP 地址或主机名: {value}"

    @staticmethod
    def validate_port(value: int) -> tuple[bool, str]:
        """
        校验端口号。

        Returns:
            (is_valid, error_msg)
        """
        if not isinstance(value, int):
            return False, "端口必须是整数"
        if value < 1 or value > 65535:
            return False, f"端口范围应在 1-65535 之间，当前值: {value}"
        return True, ""

    @staticmethod
    def validate_path(value: str) -> tuple[bool, str]:
        """
        校验路径合法性（不含非法字符）。

        Returns:
            (is_valid, error_msg)
        """
        if not value or not value.strip():
            return False, "路径不能为空"

        if Validators._INVALID_PATH_CHARS.search(value):
            return False, f"路径包含非法字符: {value}"

        return True, ""

    @staticmethod
    def validate_username(value: str) -> tuple[bool, str]:
        """
        校验用户名。

        Returns:
            (is_valid, error_msg)
        """
        if not value or not value.strip():
            return False, "用户名不能为空"
        if len(value) > 128:
            return False, "用户名长度不能超过 128 个字符"
        return True, ""

    @staticmethod
    def validate_host_name(value: str) -> tuple[bool, str]:
        """
        校验主机别名。

        Returns:
            (is_valid, error_msg)
        """
        if not value or not value.strip():
            return False, "主机名称不能为空"
        value = value.strip()
        if len(value) > 64:
            return False, "主机名称长度不能超过 64 个字符"
        if not re.match(r'^[\w\u4e00-\u9fff\-]+$', value):
            return False, "主机名称只能包含字母、数字、下划线、中文和连字符"
        return True, ""

    @staticmethod
    def validate_host_info(host_info: dict) -> list[str]:
        """
        校验完整的主机信息。

        Args:
            host_info: 主机信息字典

        Returns:
            错误列表（空=全部合法）
        """
        errors = []

        # 主机名称
        name = host_info.get("name", "")
        valid, msg = Validators.validate_host_name(name)
        if not valid:
            errors.append(f"主机名称: {msg}")

        # IP/主机名
        host = host_info.get("host", "")
        valid, msg = Validators.validate_ip(host)
        if not valid:
            errors.append(f"地址: {msg}")

        # 端口
        port = host_info.get("port", 22)
        try:
            port = int(port)
            valid, msg = Validators.validate_port(port)
            if not valid:
                errors.append(f"端口: {msg}")
        except (ValueError, TypeError):
            errors.append(f"端口: 必须是整数，当前值: {port}")

        # 用户名
        username = host_info.get("username", "")
        valid, msg = Validators.validate_username(username)
        if not valid:
            errors.append(f"用户名: {msg}")

        # 认证方式
        auth_type = host_info.get("auth_type", "password")
        if auth_type == "password":
            # 既没有明文密码，也没有已存储的加密密码 → 才报错
            if not host_info.get("password") and not host_info.get("password_encrypted"):
                errors.append("密码: 使用密码认证时密码不能为空")
        elif auth_type == "key":
            key_path = host_info.get("key_path", "")
            if not key_path:
                errors.append("密钥路径: 使用密钥认证时密钥路径不能为空")
            valid, msg = Validators.validate_path(key_path)
            if not valid:
                errors.append(f"密钥路径: {msg}")
        else:
            errors.append(f"认证方式: 不支持的类型 '{auth_type}'，应为 'password' 或 'key'")

        return errors
