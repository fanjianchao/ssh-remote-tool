from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机管理业务逻辑

连接测试、密码加密存储、CRUD 透传。
"""

import io
import json
import time
from typing import Optional

from data.models import Host, ConnTestResult, ImportResult, ServiceError
from data.host_repository import HostRepository
from data.database import get_db
from utils.crypto import CryptoUtils
from utils.logger import setup_logger
from utils.ssh_helpers import HostCredentials, SSHConnectionPool
from utils.validators import Validators

logger = setup_logger("host_service")


class HostService:
    """主机管理服务"""

    def __init__(self, crypto: CryptoUtils | None = None, connection_pool: SSHConnectionPool | None = None):
        """
        Args:
            crypto: 加密工具实例
            connection_pool: SSH 连接池实例
        """
        self._crypto = crypto or CryptoUtils()
        self._connection_pool = connection_pool

    # ---- CRUD ----

    def add_host(self, host_info: dict) -> Host:
        """
        添加主机。

        Args:
            host_info: 主机信息（password 字段为明文）

        Returns:
            Host ORM 对象

        Raises:
            ServiceError: 校验失败或名称重复
        """
        # 校验
        # 如果主机名为空，默认使用 host（IP/域名）
        if not host_info.get("name"):
            host_info["name"] = host_info.get("host", "")

        errors = Validators.validate_host_info(host_info)
        if errors:
            raise ServiceError("VALIDATION_ERROR", "主机信息校验失败", "; ".join(errors))

        # 加密密码
        password = host_info.get("password", "")
        if password:
            host_info["password_encrypted"] = self._crypto.encrypt(password)
        else:
            host_info["password_encrypted"] = ""

        # 清除明文密码（不应存入数据库）
        host_info.pop("password", None)

        with get_db().session_scope() as session:
            repo = HostRepository(session)
            host = repo.create(host_info)
            session.commit()
            # 重新查询以获取完整的对象
            host = session.merge(host)
            return host

    def get_host(self, host_id: int) -> Host:
        """查询单台主机"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            host = repo.get_by_id(host_id)
            if not host:
                raise ServiceError("HOST_NOT_FOUND", f"主机 ID {host_id} 不存在")
            return host

    def list_hosts(self) -> list[Host]:
        """列出全部主机"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.get_all()

    def update_host(self, host_id: int, host_info: dict) -> Host:
        """更新主机"""
        # 校验（如果提供了名称/地址等字段）
        if any(k in host_info for k in ["name", "host", "port", "username", "auth_type"]):
            full_info = self.get_host(host_id).to_dict()
            full_info.update(host_info)
            errors = Validators.validate_host_info(full_info)
            if errors:
                raise ServiceError("VALIDATION_ERROR", "主机信息校验失败", "; ".join(errors))

        # 加密密码（如果提供了新密码）
        password = host_info.get("password")
        if password:
            host_info["password_encrypted"] = self._crypto.encrypt(password)
            host_info.pop("password", None)

        with get_db().session_scope() as session:
            repo = HostRepository(session)
            host = repo.update(host_id, host_info)
            return host

    def delete_host(self, host_id: int) -> bool:
        """删除单台主机"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.delete(host_id)

    def delete_hosts(self, host_ids: list[int]) -> int:
        """批量删除"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.delete_batch(host_ids)

    def search_hosts(self, keyword: str) -> list[Host]:
        """搜索主机"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.search(keyword)

    def get_groups(self) -> list[str]:
        """获取分组列表"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.get_groups()

    # ---- 业务操作 ----

    def test_connection(self, host_id: int) -> ConnTestResult:
        """
        测试主机 SSH 连接。

        Returns:
            ConnTestResult
        """
        host = self.get_host(host_id)
        credentials = self.get_credentials(host_id)

        start_time = time.time()
        try:
            client = SSHConnectionPool()
            try:
                conn = client._create_connection(credentials)
                latency_ms = int((time.time() - start_time) * 1000)
                conn.close()
                return ConnTestResult(success=True, latency_ms=latency_ms)
            finally:
                client.close_all()
        except ConnectionError as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            code = "CONN_FAILED"
            if "Authentication" in error_msg:
                code = "AUTH_FAILED"
            elif "timed out" in error_msg.lower():
                code = "CONN_TIMEOUT"
            return ConnTestResult(success=False, latency_ms=latency_ms, error=f"[{code}] {error_msg}")
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            return ConnTestResult(success=False, latency_ms=latency_ms, error=str(e))

    @staticmethod
    def _read_file_text(file_path: str) -> str:
        """读取文件文本，自动尝试 UTF-8 / UTF-8-SIG / GBK 编码"""
        import os
        if not os.path.isfile(file_path):
            raise ServiceError("FILE_NOT_FOUND", f"文件不存在: {file_path}")
        for enc in ("utf-8-sig", "utf-8", "gbk", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        raise ServiceError("IMPORT_ERROR", "无法识别文件编码，请确保文件为 UTF-8 或 GBK 编码")

    def import_hosts(self, file_path: str) -> ImportResult:
        """从 CSV 或 JSON 文件批量导入主机"""
        content = self._read_file_text(file_path)

        # 根据文件扩展名或内容自动判断格式
        file_lower = file_path.lower()
        if file_lower.endswith(".json"):
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ServiceError("IMPORT_ERROR", f"JSON 解析失败: {e}")
            if not isinstance(data, list):
                raise ValueError("Import file must contain a JSON array")
        else:
            # 默认按 CSV 格式解析
            data = self._parse_csv_import(content)

        # 统一处理密码：明文密码 → 加密后存入 password_encrypted
        for host_dict in data:
            password = host_dict.pop("password", None)
            if password and password != "********":
                host_dict["password_encrypted"] = self._crypto.encrypt(password)
            # password 为空或 ******** → 不设置 password_encrypted，保留原值

        with get_db().session_scope() as session:
            repo = HostRepository(session)
            return repo.import_hosts(data)

    @staticmethod
    def _parse_csv_import(content: str) -> list[dict]:
        """解析 CSV 格式的导入内容，转为字典列表"""
        import csv as csv_mod
        from data.host_repository import EXPORT_COLUMNS

        reader = csv_mod.reader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            raise ServiceError("IMPORT_ERROR", "文件为空")

        # 第一行是表头，找到各字段对应的列索引
        header = rows[0]
        col_map: dict[str, int] = {}
        for field_name, cn_header in EXPORT_COLUMNS:
            # 尝试匹配中文表头或英文字段名
            for idx, h in enumerate(header):
                if h.strip() == cn_header or h.strip().lower() == field_name.lower():
                    col_map[field_name] = idx
                    break

        if not col_map:
            raise ServiceError("IMPORT_ERROR", "CSV 表头无法识别，请检查文件格式")

        result = []
        for row_idx, row in enumerate(rows[1:], start=2):
            if not any(cell.strip() for cell in row):
                continue  # 跳过空行
            host_dict: dict = {}
            for field_name, col_idx in col_map.items():
                if col_idx < len(row):
                    value = row[col_idx].strip()
                    if field_name == "port" and value:
                        try:
                            value = int(value)
                        except ValueError:
                            value = 22
                    host_dict[field_name] = value
            # 至少需要有 IP 地址
            if host_dict.get("host"):
                result.append(host_dict)

        if not result:
            raise ServiceError("IMPORT_ERROR", "未找到有效的主机数据（至少需要 IP 地址列）")
        return result

    def export_hosts(self, file_path: str, host_ids: list[int] | None = None) -> str:
        """导出主机配置到 CSV 文件"""
        with get_db().session_scope() as session:
            repo = HostRepository(session)
            if host_ids:
                # 导出选中的主机：构造临时 CSV
                from data.host_repository import EXPORT_COLUMNS
                hosts = [repo.get_by_id(hid) for hid in host_ids]
                hosts = [h for h in hosts if h is not None]
                import csv as csv_mod
                with open(file_path, "w", encoding="utf-8-sig", newline="") as f:
                    f.write("\ufeff")
                    writer = csv_mod.writer(f)
                    writer.writerow([header for _, header in EXPORT_COLUMNS])
                    for host in hosts:
                        row = []
                        for field_name, _ in EXPORT_COLUMNS:
                            if field_name == "port":
                                row.append(host.port)
                            elif field_name == "password":
                                row.append("********" if host.password_encrypted else "")
                            elif field_name == "group":
                                row.append(host.group_name or "默认")
                            elif field_name == "auth_type":
                                row.append(host.auth_type or "password")
                            elif field_name == "key_path":
                                row.append(host.key_path or "")
                            elif field_name == "remark":
                                row.append(host.remark or "")
                            elif field_name == "name":
                                row.append(host.name or "")
                            elif field_name == "host":
                                row.append(host.host or "")
                            elif field_name == "username":
                                row.append(host.username or "")
                            else:
                                row.append("")
                        writer.writerow(row)
            else:
                csv_content = repo.export_all_csv()
                with open(file_path, "w", encoding="utf-8", newline="") as f:
                    f.write(csv_content)

        logger.info(f"Exported hosts to {file_path}")
        return file_path

    # ---- 凭证解密 ----

    def get_credentials(self, host_id: int) -> HostCredentials:
        """获取已解密的主机连接凭证"""
        host = self.get_host(host_id)
        password = None
        if host.password_encrypted and self._crypto.is_encrypted(host.password_encrypted):
            try:
                password = self._crypto.decrypt(host.password_encrypted)
            except ValueError as e:
                raise ServiceError("ENCRYPTION_ERROR", f"密码解密失败: {e}")

        return HostCredentials(
            host=host.host,
            port=host.port,
            username=host.username,
            password=password,
            key_path=host.key_path or None,
        )
