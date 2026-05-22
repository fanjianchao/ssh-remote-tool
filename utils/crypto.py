from __future__ import annotations
# -*- coding: utf-8 -*-
"""
加密工具

基于 Fernet 对称加密，用于敏感信息（密码、密钥）的加密存储与解密读取。
密钥派生自机器标识，确保同一机器上加密的数据可被解密。
"""

import base64
import hashlib
import platform
import uuid
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class CryptoUtils:
    """基于 Fernet 的对称加密工具"""

    # 加密数据的前缀标识，用于判断值是否已加密
    _ENCRYPTION_PREFIX = "ENC:"
    # PBKDF2 盐值（固定，确保同一机器上密钥一致）
    _SALT = b"ssh_remote_tool_v1"
    # KDF 迭代次数
    _KDF_ITERATIONS = 480000

    def __init__(self, key_source: str = "machine", user_password: Optional[str] = None):
        """
        初始化加密工具。

        Args:
            key_source: 密钥来源
                - "machine": 基于机器标识自动生成密钥
                - "password": 基于用户密码生成密钥
            user_password: 当 key_source="password" 时必须提供
        """
        self._fernet = self._create_fernet(key_source, user_password)

    def _create_fernet(self, key_source: str, user_password: Optional[str]) -> Fernet:
        """根据密钥来源创建 Fernet 实例"""
        if key_source == "machine":
            # 基于机器标识生成密钥种子
            machine_id = self._get_machine_id()
            password = machine_id.encode("utf-8")
        elif key_source == "password":
            if not user_password:
                raise ValueError("user_password is required when key_source is 'password'")
            password = user_password.encode("utf-8")
        else:
            raise ValueError(f"Unsupported key_source: {key_source}")

        # 使用 PBKDF2 派生 32 字节密钥
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._SALT,
            iterations=self._KDF_ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return Fernet(key)

    @staticmethod
    def _get_machine_id() -> str:
        """
        获取机器唯一标识。
        优先使用 Windows 的 MachineGuid，回退到 MAC 地址。
        """
        system = platform.system()
        if system == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SOFTWARE\Microsoft\Cryptography",
                )
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
                winreg.CloseKey(key)
                return str(guid)
            except Exception:
                pass

        # 回退：基于 MAC 地址和主机名
        mac = uuid.getnode()
        hostname = platform.node()
        return hashlib.sha256(f"{mac}-{hostname}".encode()).hexdigest()

    def encrypt(self, plaintext: str) -> str:
        """
        加密明文字符串。

        Args:
            plaintext: 要加密的明文

        Returns:
            格式为 "ENC:<base64密文>" 的字符串
        """
        if not plaintext:
            return ""
        encrypted = self._fernet.encrypt(plaintext.encode("utf-8"))
        return self._ENCRYPTION_PREFIX + encrypted.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        """
        解密密文字符串。

        Args:
            ciphertext: 格式为 "ENC:<base64密文>" 的字符串

        Returns:
            解密后的明文

        Raises:
            ValueError: 密文格式错误或解密失败
        """
        if not ciphertext:
            return ""
        if not ciphertext.startswith(self._ENCRYPTION_PREFIX):
            raise ValueError("Invalid encrypted format: missing prefix")
        try:
            token = ciphertext[len(self._ENCRYPTION_PREFIX):]
            decrypted = self._fernet.decrypt(token.encode("ascii"))
            return decrypted.decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as e:
            raise ValueError(f"Decryption failed: {e}") from e

    def is_encrypted(self, value: str) -> bool:
        """判断值是否为已加密格式"""
        return isinstance(value, str) and value.startswith(self._ENCRYPTION_PREFIX)
