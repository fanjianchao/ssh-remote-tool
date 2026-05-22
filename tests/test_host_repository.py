from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机数据层单元测试
"""

import pytest

from data.models import Host, ServiceError
from data.host_repository import HostRepository


class TestHostRepository:
    """HostRepository 测试"""

    def test_create_host(self, db_session, crypto, sample_host_dict):
        """测试创建主机"""
        # 加密密码
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        host = repo.create(sample_host_dict)

        assert host.id is not None
        assert host.name == "测试服务器"
        assert host.host == "192.168.1.100"
        assert host.port == 22
        assert host.username == "root"
        assert host.group_name == "测试组"

    def test_create_duplicate_name(self, db_session, crypto, sample_host_dict):
        """测试重复名称"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        repo.create(sample_host_dict)

        with pytest.raises(ServiceError) as exc_info:
            repo.create(sample_host_dict)
        assert exc_info.value.code == "DUPLICATE_NAME"

    def test_get_by_id(self, db_session, crypto, sample_host_dict):
        """测试按 ID 查询"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        created = repo.create(sample_host_dict)

        host = repo.get_by_id(created.id)
        assert host is not None
        assert host.name == "测试服务器"

    def test_get_by_id_not_found(self, db_session):
        """测试查询不存在的主机"""
        repo = HostRepository(db_session)
        host = repo.get_by_id(99999)
        assert host is None

    def test_get_all(self, db_session, crypto, sample_host_dict):
        """测试获取全部主机"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        repo.create(sample_host_dict)

        hosts = repo.get_all()
        assert len(hosts) == 1

    def test_update_host(self, db_session, crypto, sample_host_dict):
        """测试更新主机"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        host = repo.create(sample_host_dict)

        updated = repo.update(host.id, {"port": 2222, "remark": "更新备注"})
        assert updated.port == 2222
        assert updated.remark == "更新备注"

    def test_update_host_not_found(self, db_session):
        """测试更新不存在的主机"""
        repo = HostRepository(db_session)
        with pytest.raises(ServiceError) as exc_info:
            repo.update(99999, {"name": "test"})
        assert exc_info.value.code == "HOST_NOT_FOUND"

    def test_delete_host(self, db_session, crypto, sample_host_dict):
        """测试删除主机"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        host = repo.create(sample_host_dict)

        assert repo.delete(host.id) is True
        assert repo.get_by_id(host.id) is None

    def test_delete_host_not_found(self, db_session):
        """测试删除不存在的主机"""
        repo = HostRepository(db_session)
        assert repo.delete(99999) is False

    def test_delete_batch(self, db_session, crypto, sample_host_dict):
        """测试批量删除"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        h1 = repo.create(sample_host_dict)
        sample_host_dict["name"] = "测试服务器2"
        sample_host_dict["host"] = "192.168.1.101"
        h2 = repo.create(sample_host_dict)

        count = repo.delete_batch([h1.id, h2.id])
        assert count == 2

    def test_search(self, db_session, crypto, sample_host_dict):
        """测试搜索"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        repo.create(sample_host_dict)

        results = repo.search("192.168")
        assert len(results) == 1

    def test_get_groups(self, db_session, crypto, sample_host_dict):
        """测试获取分组"""
        sample_host_dict["password_encrypted"] = crypto.encrypt(sample_host_dict.pop("password"))

        repo = HostRepository(db_session)
        repo.create(sample_host_dict)

        groups = repo.get_groups()
        assert "测试组" in groups
