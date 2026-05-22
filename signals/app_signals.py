from __future__ import annotations
# -*- coding: utf-8 -*-
"""
全局应用信号

跨模块的通用信号，如页面切换、状态栏消息、全局错误等。
"""

from PySide6.QtCore import QObject, Signal


class AppSignals(QObject):
    """全局应用级信号"""

    # ---- UI 控制 ----
    switch_page = Signal(int)         # 页面索引 (0=主机管理, 1=任务编排, 2=执行监控)
    status_message = Signal(str)       # 消息文本（显示时长由接收端决定）
    global_error = Signal(str)        # 不可恢复的全局错误信息
    elapsed_updated = Signal(str)     # 耗时文本（如 "01:30"）

    # ---- 应用生命周期 ----
    app_closing = Signal()            # 应用即将关闭
    db_initialized = Signal()         # 数据库初始化完成
