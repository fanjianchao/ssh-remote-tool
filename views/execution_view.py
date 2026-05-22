from __future__ import annotations
# -*- coding: utf-8 -*-
"""
执行监控页

实时日志输出、进度条、主机状态矩阵、操作按钮。
监听 TaskEngine 信号，实时更新 UI。
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSplitter,
)
from PySide6.QtCore import Qt, QEvent, QPoint

from core.task_engine import TaskEngine
from core.host_service import HostService
from data.models import Task
from signals.task_signals import TaskSignals
from signals.app_signals import AppSignals
from views.components.log_viewer import LogViewer
from views.components.progress_panel import ProgressPanel
from utils.logger import setup_logger

logger = setup_logger("execution_view")


class ExecutionView(QWidget):
    """执行监控页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_engine = TaskEngine()
        self._host_service = HostService()
        self._task_signals = TaskSignals()
        self._app_signals: AppSignals | None = None
        self._current_task: Task | None = None
        self._host_names: dict[str, str] = {}  # host_id_str → host_name
        self._host_info: dict[str, str] = {}  # host_id_str → "ip:port@user"
        self._is_executing: bool = False  # 是否正在执行任务

        self._setup_ui()
        self._init_tooltip_manager()
        self._connect_engine_signals()

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 0)
        layout.setSpacing(8)

        # --- 进度面板 ---
        self._progress_panel = ProgressPanel()
        layout.addWidget(self._progress_panel)

        # 将操作按钮插入进度面板统计行右侧
        self._btn_pause = QPushButton("⏸️ 暂停")
        self._btn_pause.setFixedHeight(28)
        self._btn_pause.setFixedWidth(80)
        self._btn_pause.setEnabled(False)
        self._btn_pause.clicked.connect(self._on_pause)
        self._progress_panel.stats_layout.addWidget(self._btn_pause)

        self._btn_cancel = QPushButton("⏹️ 取消")
        self._btn_cancel.setFixedHeight(28)
        self._btn_cancel.setFixedWidth(80)
        self._btn_cancel.setEnabled(False)
        self._btn_cancel.clicked.connect(self._on_cancel)
        self._progress_panel.stats_layout.addWidget(self._btn_cancel)

        self._btn_back = QPushButton("🔙 返回编辑")
        self._btn_back.setFixedHeight(28)
        self._btn_back.clicked.connect(self._on_back)
        self._progress_panel.stats_layout.addWidget(self._btn_back)

        # 双击主机卡片 → 筛选对应主机日志
        self._progress_panel.host_double_clicked.connect(self._on_host_card_dblclicked)

        # 右键菜单 → 重试
        self._progress_panel.retry_host_requested.connect(self._on_retry_host)
        self._progress_panel.retry_step_requested.connect(self._on_retry_step)
        self._progress_panel.retry_all_hosts_requested.connect(self._on_retry_all_hosts)

        # --- 日志区域 ---
        self._log_viewer = LogViewer()
        layout.addWidget(self._log_viewer)

        # 页面样式
        self.setStyleSheet("""
            ExecutionView {
                background-color: #FFFFFF;
            }
            QPushButton {
                background-color: #E0E0E0;
                color: #333333;
                border: 1px solid #D0D0D0;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #D0D0D0;
            }
            QPushButton:pressed {
                background-color: #BDBDBD;
            }
            QPushButton:disabled {
                color: #BDBDBD;
                border-color: #E0E0E0;
            }
        """)

    def _connect_engine_signals(self):
        """连接 TaskEngine 信号到 UI 更新方法"""
        self._task_engine.step_started.connect(self._on_step_started)
        self._task_engine.step_completed.connect(self._on_step_completed)
        self._task_engine.command_output.connect(self._on_command_output)
        self._task_engine.transfer_progress.connect(self._on_transfer_progress)
        self._task_engine.host_finished.connect(self._on_host_finished)
        self._task_engine.task_finished.connect(self._on_task_finished)
        self._task_engine.task_error.connect(self._on_task_error)

    def _init_tooltip_manager(self):
        """初始化自定义 tooltip 管理器"""
        self._global_tooltip = QLabel(self)
        self._global_tooltip.setWindowFlag(Qt.ToolTip, True)
        self._global_tooltip.setTextFormat(Qt.TextFormat.RichText)
        self._global_tooltip.setWordWrap(True)
        self._global_tooltip.setStyleSheet(
            "background-color: #FFFFFF; color: #333333; border: 1px solid #E0E0E0; padding: 6px;"
        )
        self._global_tooltip.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._global_tooltip.hide()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and isinstance(obj, QWidget) and self.isAncestorOf(obj):
            tooltip_text = obj.toolTip()
            if tooltip_text:
                self._show_global_tooltip(obj, tooltip_text, event)
                return True
            self._global_tooltip.hide()
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Leave and isinstance(obj, QWidget) and self.isAncestorOf(obj):
            self._global_tooltip.hide()
            return super().eventFilter(obj, event)

        return super().eventFilter(obj, event)

    def _show_global_tooltip(self, source: QWidget, tooltip_text: str, event):
        text = tooltip_text.replace("\n", "<br>")
        self._global_tooltip.setText(text)
        self._global_tooltip.adjustSize()
        pos = source.mapToGlobal(event.pos()) + QPoint(10, 18)
        screen_rect = source.screen().availableGeometry()
        tooltip_rect = self._global_tooltip.frameGeometry()
        if pos.x() + tooltip_rect.width() > screen_rect.right() - 8:
            pos.setX(screen_rect.right() - tooltip_rect.width() - 8)
        if pos.y() + tooltip_rect.height() > screen_rect.bottom() - 8:
            pos.setY(source.mapToGlobal(QPoint(0, 0)).y() - tooltip_rect.height() - 8)
        self._global_tooltip.move(pos)
        self._global_tooltip.show()

    # ============ 公共方法 ============

    def set_app_signals(self, signals: AppSignals):
        """设置全局信号"""
        self._app_signals = signals
        self._progress_panel.set_app_signals(signals)

    @property
    def task_engine(self) -> TaskEngine:
        """暴露 TaskEngine 实例"""
        return self._task_engine

    @property
    def task_signals(self) -> TaskSignals:
        return self._task_signals

    def execute_task(self, task: Task, host_ids: list[int]):
        """
        执行任务。

        Args:
            task: Task 对象（含步骤）
            host_ids: 目标主机 ID 列表
        """
        self._current_task = task
        self._log_viewer.clear_logs()

        # 解析主机名称和连接信息
        self._host_names = {}
        self._host_info = {}
        try:
            all_hosts = self._host_service.list_hosts()
            for h in all_hosts:
                hid = str(h.id)
                self._host_names[hid] = h.name
                self._host_info[hid] = f"{h.host}:{h.port}@{h.username}"
        except Exception:
            pass

        # 为每台主机分配日志颜色
        for hid in host_ids:
            self._log_viewer.assign_host_color(str(hid), self._host_names.get(str(hid), ""))

        # 初始化进度面板
        host_name_map = {str(hid): self._host_names.get(str(hid), str(hid)) for hid in host_ids}
        host_info_map = {str(hid): self._host_info.get(str(hid), "") for hid in host_ids}
        step_names = [s.name for s in task.steps] if task.steps else []
        self._progress_panel.start_execution(
            host_ids=[str(hid) for hid in host_ids],
            host_names=host_name_map,
            total_steps=len(task.steps),
            step_name=task.steps[0].name if task.steps else "",
            host_info=host_info_map,
            step_names=step_names,
        )

        # 启用控制按钮
        self._btn_pause.setEnabled(True)
        self._btn_cancel.setEnabled(True)
        self._btn_pause.setText("⏸️ 暂停")

        # 写入系统日志
        self._log_viewer.append_system_log(f"{'='*60}", "info")
        self._log_viewer.append_system_log(f"开始执行任务: {task.name}", "info")
        self._log_viewer.append_system_log(f"目标主机: {len(host_ids)} 台", "info")
        # 显示每台主机的名称和连接信息
        for hid in host_ids:
            hid_str = str(hid)
            name = self._host_names.get(hid_str, hid_str)
            info = self._host_info.get(hid_str, "")
            self._log_viewer.append_system_log(f"  • {name} ({info})", "info")
        self._log_viewer.append_system_log(f"执行步骤: {len(task.steps)} 个", "info")
        if task.steps:
            for i, step in enumerate(task.steps):
                type_map = {"ssh_command": "命令执行", "sftp_upload": "上传文件", "sftp_download": "下载文件"}
                self._log_viewer.append_system_log(
                    f"  {i+1}. [{type_map.get(step.step_type, step.step_type)}] {step.name}",
                    "info",
                )
        self._log_viewer.append_system_log(f"{'='*60}", "info")

        # 启动执行
        self._task_engine.execute_task(task, host_ids)

    # ============ 信号回调 ============

    def _on_step_started(self, host_id: str, step_index: int, step_type: str, step_name: str):
        """步骤开始"""
        self._progress_panel.update_step(step_index, step_name)
        self._progress_panel.update_host_status(host_id, "running")
        self._progress_panel.update_host_step_running(host_id, step_index)

        host_name = self._host_names.get(host_id, host_id)
        type_map = {"ssh_command": "命令执行", "sftp_upload": "上传文件", "sftp_download": "下载文件"}
        type_text = type_map.get(step_type, step_type)
        self._log_viewer.append_log(
            host_id,
            f"开始执行步骤 {step_index + 1}: {step_name} ({type_text})",
            "info",
        )

        # 如果是传输步骤，初始化传输进度条
        if step_type in ("sftp_upload", "sftp_download"):
            self._progress_panel.init_transfer(host_id)

    def _on_step_completed(self, host_id: str, step_index: int, success: bool, error: str):
        """步骤完成"""
        host_name = self._host_names.get(host_id, host_id)
        # 传输步骤完成时，在日志中输出最终传输摘要
        if self._progress_panel._transfer_data.get(host_id):
            td = self._progress_panel._transfer_data[host_id]
            total_mb = td["total"] / (1024 * 1024) if td["total"] > 0 else 0
            self._log_viewer.append_log(
                host_id,
                f"传输完成: {total_mb:.1f} MB",
                "info",
            )
        # 更新步骤进度（无论成功失败，已完成步骤数 +1）
        if success:
            self._progress_panel.update_host_step_progress(host_id, step_index + 1)
            self._progress_panel.update_host_step_status(host_id, step_index, True)
            self._log_viewer.append_log(
                host_id,
                f"步骤 {step_index + 1} 执行成功 ✓",
                "success",
            )
        else:
            self._progress_panel.update_host_step_progress(host_id, step_index + 1)
            self._progress_panel.update_host_step_status(host_id, step_index, False)
            self._log_viewer.append_log(
                host_id,
                f"步骤 {step_index + 1} 执行失败 ✗: {error}",
                "error",
            )

    def _on_command_output(self, host_id: str, line_text: str, output_type: str):
        """命令实时输出"""
        if host_id == "__system__":
            self._log_viewer.append_system_log(line_text, "info")
        else:
            self._log_viewer.append_log(host_id, line_text, output_type)

    def _on_transfer_progress(self, host_id: str, step_index: int,
                               transferred: int, total: int, speed: int):
        """文件传输进度 → 更新进度面板卡片（不再写日志刷屏）"""
        self._progress_panel.update_transfer_progress(host_id, transferred, total, speed)

    def _on_host_finished(self, host_id: str, all_success: bool):
        """单台主机全部步骤完成"""
        status = "success" if all_success else "failed"
        self._progress_panel.update_host_status(host_id, status)

        host_name = self._host_names.get(host_id, host_id)
        if all_success:
            self._log_viewer.append_log(
                host_id,
                f"全部步骤完成 ✓",
                "success",
            )
        else:
            self._log_viewer.append_log(
                host_id,
                f"执行中断 ✗（后续步骤已跳过）",
                "warning",
            )

        # 单台主机执行完毕，触发排序刷新
        self._progress_panel.sort_and_refresh()

    def _on_task_finished(self, all_success: bool, summary: dict):
        """整个任务执行完成"""
        is_retry = summary.get("is_retry", False)

        if is_retry:
            # 重试完成：更新进度面板状态，不弹窗
            host_id = summary.get("retry_host_id", "")
            is_single_step = summary.get("is_single_step", False)
            step_index = summary.get("retry_step_index", 0)

            if is_single_step:
                # 单步骤重试：只更新该步骤的状态，不改变主机整体状态
                host_result = summary.get("host_results", {}).get(host_id, {})
                step_success = host_result.get("success", False)
                self._progress_panel.update_host_step_status(host_id, step_index, step_success)
                self._log_viewer.append_system_log(
                    f"🔄 重试完成 - 步骤 {step_index + 1}: {'成功 ✓' if step_success else '失败 ✗'}",
                    "success" if step_success else "error",
                )
            else:
                # 主机重试：步骤状态已在执行过程中由 _on_step_completed 实时更新，
                # 这里只需根据引擎返回结果更新主机整体状态，并刷新 UI
                host_result = summary.get("host_results", {}).get(host_id, {})
                host_success = host_result.get("success", False)

                # 计算已完成步骤数（已完成的步骤 = success 或 failed）
                step_statuses = self._progress_panel._host_step_statuses.get(host_id, [])
                completed = sum(1 for s in step_statuses if s in ("success", "failed"))
                self._progress_panel._host_step_progress[host_id] = completed
                self._progress_panel._host_status[host_id] = "success" if host_success else "failed"
                self._progress_panel._refresh_host_list()
                self._progress_panel._update_stats()

                # 更新总进度条到 100%
                self._progress_panel._progress_bar.setValue(100)
                if host_success:
                    self._progress_panel._step_label.setText(
                        f"🔄 重试完成 - 主机 {self._host_names.get(host_id, host_id)}: 成功 ✓"
                    )
                    self._progress_panel._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #43A047;")
                    self._progress_panel._progress_bar.setStyleSheet("""
                        QProgressBar { background-color: #E0E0E0; border: none; border-radius: 4px; color: #fff; text-align: center; font-size: 11px; }
                        QProgressBar::chunk { background-color: #43A047; border-radius: 4px; }
                    """)
                else:
                    self._progress_panel._step_label.setText(
                        f"🔄 重试完成 - 主机 {self._host_names.get(host_id, host_id)}: 失败 ✗"
                    )
                    self._progress_panel._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E53935;")
                    self._progress_panel._progress_bar.setStyleSheet("""
                        QProgressBar { background-color: #E0E0E0; border: none; border-radius: 4px; color: #fff; text-align: center; font-size: 11px; }
                        QProgressBar::chunk { background-color: #E53935; border-radius: 4px; }
                    """)

                self._log_viewer.append_system_log(
                    f"🔄 重试完成 - 主机 {self._host_names.get(host_id, host_id)}: "
                    f"{'成功 ✓' if host_success else '失败 ✗'}",
                    "success" if host_success else "error",
                )
            return

        # 正常任务完成
        self._progress_panel.finish_execution(all_success, summary)
        self._btn_pause.setEnabled(False)
        self._btn_cancel.setEnabled(False)

        duration = summary.get("duration_seconds", 0)
        total = summary.get("total_hosts", 0)
        success = summary.get("success_hosts", 0)
        failed = summary.get("failed_hosts", 0)

        self._log_viewer.append_system_log(f"{'='*60}", "info")
        if all_success:
            self._log_viewer.append_system_log(
                f"🎉 任务执行完成 - 全部成功 ({total}/{total})",
                "success",
            )
        else:
            self._log_viewer.append_system_log(
                f"⚠️ 任务执行完成 - 成功 {success}, 失败 {failed}",
                "warning",
            )
        self._log_viewer.append_system_log(
            f"总耗时: {self._progress_panel._format_duration(duration)}",
            "info",
        )


    def _on_task_error(self, error_message: str):
        """任务执行出错"""
        self._log_viewer.append_system_log(f"❌ 执行错误: {error_message}", "error")
        self._btn_pause.setEnabled(False)
        self._btn_cancel.setEnabled(False)
        self._progress_panel.reset()
        QMessageBox.critical(self, "执行错误", error_message)

    # ============ 操作按钮 ============

    def _on_host_card_dblclicked(self, host_id: str):
        """双击主机状态行 → 筛选对应主机日志 + 高亮该行"""
        self._log_viewer.filter_host(host_id)
        self._progress_panel.highlight_host(host_id)

    def _on_retry_host(self, host_id: str, from_step_index: int = 0):
        """右键菜单 → 重试任务（该主机从头执行所有步骤）"""
        if not self._current_task:
            return
        if self._task_engine.is_running:
            QMessageBox.warning(self, "提示", "已有任务正在执行中，请等待完成后再重试")
            return

        host_name = self._host_names.get(host_id, host_id)
        reply = QMessageBox.question(
            self, "确认重试",
            f"确定要重试主机「{host_name}」的任务吗？\n将从头开始重新执行所有步骤。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 重置该主机所有步骤状态为 pending
        step_statuses = self._progress_panel._host_step_statuses.get(host_id, [])
        for i in range(len(step_statuses)):
            step_statuses[i] = "pending"
        self._progress_panel._host_step_statuses[host_id] = step_statuses

        # 重置主机状态为 pending，更新进度
        self._progress_panel._host_status[host_id] = "pending"
        self._progress_panel._host_step_progress[host_id] = 0
        self._progress_panel._refresh_host_list()
        self._progress_panel._update_stats()

        # 重置总进度条样式（清除上次执行完成的绿色/红色样式）
        self._progress_panel._progress_bar.setValue(0)
        self._progress_panel._progress_bar.setStyleSheet("")
        self._progress_panel._step_label.setText("🔄 正在重试...")
        self._progress_panel._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1976D2;")

        # 启用控制按钮
        self._btn_pause.setEnabled(True)
        self._btn_cancel.setEnabled(True)
        self._btn_pause.setText("⏸️ 暂停")

        # 启动重试
        self._task_engine.retry_host(self._current_task, int(host_id), from_step_index)

    def _on_retry_step(self, host_id: str, step_index: int):
        """右键菜单 → 重试指定步骤"""
        if not self._current_task:
            return
        if self._task_engine.is_running:
            QMessageBox.warning(self, "提示", "已有任务正在执行中，请等待完成后再重试")
            return

        step_name = ""
        if step_index < len(self._current_task.steps):
            step_name = self._current_task.steps[step_index].name
        host_name = self._host_names.get(host_id, host_id)
        reply = QMessageBox.question(
            self, "确认重试",
            f"确定要重试主机「{host_name}」的步骤「{step_name}」吗？\n仅重新执行该步骤，不会影响其他步骤。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 重置该步骤状态为 pending
        step_statuses = self._progress_panel._host_step_statuses.get(host_id, [])
        if step_index < len(step_statuses):
            step_statuses[step_index] = "pending"
            self._progress_panel._host_step_statuses[host_id] = step_statuses
            self._progress_panel._refresh_host_list()

        # 启用控制按钮
        self._btn_pause.setEnabled(True)
        self._btn_cancel.setEnabled(True)
        self._btn_pause.setText("⏸️ 暂停")

        # 启动单步骤重试
        self._task_engine.retry_step(self._current_task, int(host_id), step_index)

    def _on_retry_all_hosts(self):
        """总进度条右键菜单 → 重试所有主机的任务（全部从头执行）"""
        if not self._current_task:
            return
        if self._task_engine.is_running:
            QMessageBox.warning(self, "提示", "已有任务正在执行中，请等待完成后再重试")
            return

        host_ids = list(self._progress_panel._host_status.keys())
        if not host_ids:
            return

        total = len(host_ids)
        reply = QMessageBox.question(
            self, "确认重试",
            f"确定要重试所有主机的任务吗？\n将对全部 {total} 台主机从头开始重新执行所有步骤。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 重置所有主机的步骤状态为 pending
        for host_id in host_ids:
            step_statuses = self._progress_panel._host_step_statuses.get(host_id, [])
            for i in range(len(step_statuses)):
                step_statuses[i] = "pending"
            self._progress_panel._host_step_statuses[host_id] = step_statuses
            self._progress_panel._host_status[host_id] = "pending"
            self._progress_panel._host_step_progress[host_id] = 0

        # 刷新 UI
        self._progress_panel._refresh_host_list()
        self._progress_panel._update_stats()

        # 重置总进度条
        self._progress_panel._progress_bar.setValue(0)
        self._progress_panel._progress_bar.setStyleSheet("")
        self._progress_panel._step_label.setText("🔄 正在重试所有主机...")
        self._progress_panel._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #1976D2;")

        # 启用控制按钮
        self._btn_pause.setEnabled(True)
        self._btn_cancel.setEnabled(True)
        self._btn_pause.setText("⏸️ 暂停")

        # 写入系统日志
        self._log_viewer.append_system_log(f"{'='*60}", "info")
        self._log_viewer.append_system_log(f"🔄 开始重试所有主机任务（共 {total} 台）", "info")

        # 重置已有日志颜色分配（复用已有颜色）
        int_host_ids = [int(hid) for hid in host_ids]

        # 重新初始化进度面板的计时器（重置开始时间）
        self._progress_panel._start_time = datetime.now()
        self._progress_panel._elapsed_timer.start()

        # 启动执行（复用 execute_task 中的引擎入口）
        self._task_engine.execute_task(self._current_task, int_host_ids)

    def keyPressEvent(self, event):
        """ESC 退出日志筛选"""
        if event.key() == Qt.Key.Key_Escape:
            if self._log_viewer._filter_host_id is not None:
                self._log_viewer.filter_host(None)
                self._progress_panel.highlight_host(None)
                return
        super().keyPressEvent(event)

    def _on_pause(self):
        """暂停/继续"""
        if self._task_engine.is_running:
            self._task_engine.pause()
            self._btn_pause.setText("▶️ 继续")
            self._log_viewer.append_system_log("任务已暂停", "warning")
        else:
            # 可能是暂停状态
            self._task_engine.resume()
            self._btn_pause.setText("⏸️ 暂停")
            self._log_viewer.append_system_log("任务已恢复", "info")

    def _on_cancel(self):
        """取消执行"""
        reply = QMessageBox.question(
            self, "确认取消", "确定要取消当前任务执行吗？\n已完成的步骤结果将保留。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._task_engine.cancel()
            self._btn_pause.setEnabled(False)
            self._btn_cancel.setEnabled(False)
            self._log_viewer.append_system_log("用户取消了任务执行", "warning")

    def _on_back(self):
        """返回编辑页面"""
        if self._task_engine.is_running:
            reply = QMessageBox.question(
                self, "确认返回", "任务正在执行中，确定要返回编辑页面吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._task_engine.cancel()

        if self._app_signals:
            self._app_signals.switch_page.emit(1)  # 切换到任务编排页
