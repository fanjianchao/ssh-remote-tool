from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机配置数据访问层

主机 CRUD 操作、批量操作、导入导出。
"""

import csv
import io
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from data.models import Host, ImportResult, ServiceError

# CSV 导出的列定义：(字段名, 中文表头)
EXPORT_COLUMNS = [
    ("name", "主机名"),
    ("host", "IP地址"),
    ("port", "端口"),
    ("username", "用户名"),
    ("auth_type", "认证方式"),
    ("password", "密码"),
    ("key_path", "密钥路径"),
    ("group", "分组"),
    ("remark", "备注"),
]


class HostRepository:
    """主机配置 Repository"""

    def __init__(self, session: Session):
        self._session = session

    def create(self, host_dict: dict) -> Host:
        """
        创建主机配置。

        Args:
            host_dict: 主机信息字典

        Returns:
            创建的 Host ORM 对象

        Raises:
            ServiceError: 名称重复
        """
        # 检查名称唯一性
        existing = self._session.execute(
            select(Host).where(Host.name == host_dict["name"])
        ).scalar_one_or_none()
        if existing:
            raise ServiceError("DUPLICATE_NAME", f"主机名称 '{host_dict['name']}' 已存在")

        host = Host(
            name=host_dict["name"],
            host=host_dict["host"],
            port=host_dict.get("port", 22),
            username=host_dict["username"],
            auth_type=host_dict.get("auth_type", "password"),
            password_encrypted=host_dict.get("password_encrypted", ""),
            key_path=host_dict.get("key_path", ""),
            group_name=host_dict.get("group", "默认"),
            remark=host_dict.get("remark", ""),
        )
        self._session.add(host)
        self._session.flush()
        return host

    def get_by_id(self, host_id: int) -> Optional[Host]:
        """按 ID 查询"""
        return self._session.execute(
            select(Host).where(Host.id == host_id)
        ).scalar_one_or_none()

    def get_all(self) -> list[Host]:
        """返回全部主机列表，按 group → name 排序"""
        stmt = select(Host).order_by(Host.group_name, Host.name)
        return list(self._session.execute(stmt).scalars().all())

    def get_by_group(self, group: str) -> list[Host]:
        """按分组筛选"""
        stmt = select(Host).where(Host.group_name == group).order_by(Host.name)
        return list(self._session.execute(stmt).scalars().all())

    def get_groups(self) -> list[str]:
        """返回所有不重复的分组名列表"""
        stmt = select(Host.group_name).distinct().order_by(Host.group_name)
        return list(self._session.execute(stmt).scalars().all())

    def update(self, host_id: int, host_dict: dict) -> Host:
        """
        更新主机配置。

        Raises:
            ServiceError: 主机不存在
        """
        host = self.get_by_id(host_id)
        if not host:
            raise ServiceError("HOST_NOT_FOUND", f"主机 ID {host_id} 不存在")

        # 检查名称唯一性（如果修改了名称）
        new_name = host_dict.get("name")
        if new_name and new_name != host.name:
            existing = self._session.execute(
                select(Host).where(Host.name == new_name)
            ).scalar_one_or_none()
            if existing:
                raise ServiceError("DUPLICATE_NAME", f"主机名称 '{new_name}' 已存在")

        # 更新字段
        update_fields = {
            "name", "host", "port", "username", "auth_type",
            "password_encrypted", "key_path", "group", "remark",
        }
        field_mapping = {"group": "group_name"}
        for key, value in host_dict.items():
            if key in update_fields and value is not None:
                db_field = field_mapping.get(key, key)
                setattr(host, db_field, value)

        self._session.flush()
        return host

    def delete(self, host_id: int) -> bool:
        """删除主机配置，返回是否成功"""
        host = self.get_by_id(host_id)
        if not host:
            return False
        self._session.delete(host)
        self._session.flush()
        return True

    def delete_batch(self, host_ids: list[int]) -> int:
        """批量删除，返回实际删除的行数"""
        count = self._session.execute(
            select(Host).where(Host.id.in_(host_ids))
        ).scalars().all()
        deleted = len(count)
        for host in count:
            self._session.delete(host)
        self._session.flush()
        return deleted

    def search(self, keyword: str) -> list[Host]:
        """模糊搜索（匹配 name / host / username / group）"""
        pattern = f"%{keyword}%"
        stmt = select(Host).where(
            or_(
                Host.name.ilike(pattern),
                Host.host.ilike(pattern),
                Host.username.ilike(pattern),
                Host.group_name.ilike(pattern),
            )
        ).order_by(Host.group_name, Host.name)
        return list(self._session.execute(stmt).scalars().all())

    def import_hosts(self, hosts_data: list[dict]) -> ImportResult:
        """批量导入主机配置（已存在的主机按名称做更新）"""
        result = ImportResult()
        for host_dict in hosts_data:
            try:
                existing = self._session.execute(
                    select(Host).where(Host.name == host_dict.get("name", ""))
                ).scalar_one_or_none()
                if existing:
                    # 已存在 → 更新（service 层已将密码转为 password_encrypted）
                    self.update(existing.id, host_dict)
                    result.success_count += 1
                else:
                    self.create(host_dict)
                    result.success_count += 1
            except Exception as e:
                result.fail_count += 1
                result.errors.append(f"导入 '{host_dict.get('name', '?')}' 失败: {str(e)}")
        self._session.flush()
        return result

    def export_all_csv(self) -> str:
        """导出全部主机配置为 CSV 格式字符串"""
        hosts = self.get_all()
        output = io.StringIO()
        # 写入 BOM，确保 Excel 打开时中文不乱码
        output.write("\ufeff")
        writer = csv.writer(output)
        writer.writerow([header for _, header in EXPORT_COLUMNS])

        for host in hosts:
            row = []
            for field_name, _ in EXPORT_COLUMNS:
                if field_name == "port":
                    row.append(host.port)
                elif field_name == "password":
                    # 密码导出时用占位符，避免明文泄露
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

        return output.getvalue()
