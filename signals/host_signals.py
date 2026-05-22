from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机相关 Qt 信号定义

用于 UI 层与 Core 层之间的主机管理事件通信。
"""

from PySide6.QtCore import QObject, Signal


class HostSignals(QObject):
    """主机管理相关信号"""

    # ---- CRUD 操作结果通知 ----
    host_added = Signal(dict)         # Host ORM 对象转字典
    host_updated = Signal(dict)       # Host ORM 对象转字典
    host_deleted = Signal(int)        # host_id
    hosts_refreshed = Signal(list)    # Host 对象列表

    # ---- 连接测试结果 ----
    connection_tested = Signal(str, bool, object)
    # 参数: host_id, success, ConnTestResult | error_msg

    # ---- 批量操作结果 ----
    batch_deleted = Signal(int)       # 实际删除数量
    import_done = Signal(object)      # ImportResult
