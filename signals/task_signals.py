from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务相关 Qt 信号定义

用于 UI 层与 Core 层之间的任务管理和执行状态通信。
"""

from PySide6.QtCore import QObject, Signal


class TaskSignals(QObject):
    """任务管理和执行相关信号"""

    # ---- 任务 CRUD 通知 ----
    task_saved = Signal(dict)         # Task 对象转字典
    task_deleted = Signal(int)        # task_id
    tasks_refreshed = Signal(list)    # Task 对象列表

    # ---- 执行状态（由 TaskEngine 发出，UI 层监听）----

    # 某台主机某个步骤开始执行
    step_started = Signal(str, int, str, str)
    # 参数: host_id, step_index, step_type, step_name

    # 某台主机某个步骤执行完成
    step_completed = Signal(str, int, bool, str)
    # 参数: host_id, step_index, success, error_message

    # 命令执行实时输出（逐行）
    command_output = Signal(str, str, str)
    # 参数: host_id, line_text, output_type ("stdout" | "stderr")

    # 文件传输进度
    transfer_progress = Signal(str, int, int, int, int)
    # 参数: host_id, step_index, bytes_transferred, bytes_total, speed_bps

    # 单台主机全部步骤完成
    host_finished = Signal(str, bool)
    # 参数: host_id, all_success

    # 整个任务执行完成
    task_finished = Signal(bool, dict)
    # 参数: all_success, result_summary

    # 任务执行出错（不可恢复）
    task_error = Signal(str)
    # 参数: error_message
