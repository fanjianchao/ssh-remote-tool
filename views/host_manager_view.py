from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机管理页

主机列表、添加/编辑/删除/导入导出/连接测试。
"""

from typing import Optional

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QToolBar, QPushButton,
    QMessageBox, QFileDialog, QLabel,
)
from PySide6.QtCore import Qt, QThread, Signal, QEvent, QPoint

from config.constants import DEFAULT_GROUP
from core.host_service import HostService
from data.models import ServiceError, ConnTestResult
from signals.host_signals import HostSignals
from signals.app_signals import AppSignals
from views.components.host_table import HostTable
from views.host_edit_dialog import HostEditDialog
from utils.logger import setup_logger

logger = setup_logger("host_manager_view")


class ConnectionTestThread(QThread):
    """连接测试工作线程"""

    result = Signal(str, bool, object)  # host_id, success, ConnTestResult

    def __init__(self, host_service: HostService, host_id: int):
        super().__init__()
        self._host_service = host_service
        self._host_id = host_id

    def run(self):
        try:
            test_result = self._host_service.test_connection(self._host_id)
            self.result.emit(str(self._host_id), test_result.success, test_result)
        except Exception as e:
            self.result.emit(str(self._host_id), False, str(e))


class HostManagerView(QWidget):
    """主机管理页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_service = HostService()
        self._host_signals = HostSignals()
        self._app_signals: Optional[AppSignals] = None
        self._test_threads: list[ConnectionTestThread] = []

        self._setup_ui()
        self._init_tooltip_manager()
        self._connect_signals()
        self.refresh_hosts()

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- 工具栏 ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._btn_add = self._create_tool_button("➕ 添加主机", self._on_add_host)
        toolbar.addWidget(self._btn_add)

        self._btn_import = self._create_tool_button("📥 批量导入", self._on_import)
        toolbar.addWidget(self._btn_import)

        self._btn_export = self._create_tool_button("📤 导出配置", self._on_export)
        toolbar.addWidget(self._btn_export)

        toolbar.addStretch()

        self._btn_test_all = self._create_tool_button("🔌 批量测试", self._on_test_all)
        toolbar.addWidget(self._btn_test_all)

        self._btn_delete_selected = self._create_tool_button("🗑️ 删除选中", self._on_delete_selected)
        self._btn_delete_selected.setEnabled(False)
        toolbar.addWidget(self._btn_delete_selected)

        layout.addLayout(toolbar)

        # --- 主机表格 ---
        self._host_table = HostTable()
        layout.addWidget(self._host_table)

        # 页面样式
        self.setStyleSheet("background-color: #FFFFFF;")

    def _create_tool_button(self, text: str, callback) -> QPushButton:
        """创建工具栏按钮"""
        btn = QPushButton(text)
        btn.setFixedHeight(34)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        btn.setStyleSheet("""
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
                border-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #BDBDBD;
            }
            QPushButton:disabled {
                color: #BDBDBD;
                border-color: #E0E0E0;
            }
        """)
        return btn

    def _connect_signals(self):
        """连接信号"""
        self._host_table.edit_requested.connect(self._on_edit_host)
        self._host_table.delete_requested.connect(self._on_delete_host)
        self._host_table.test_requested.connect(self._on_test_connection)
        self._host_table.selection_changed.connect(self._on_selection_changed)
        self._host_table.batch_delete_requested.connect(self._on_batch_delete)
        self._host_table.inline_save_requested.connect(self._on_inline_save)

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

    @property
    def host_signals(self) -> HostSignals:
        return self._host_signals

    def trigger_import(self):
        """触发导入主机（由主窗口菜单调用）"""
        self._on_import()

    def trigger_export(self):
        """触发导出主机（由主窗口菜单调用）"""
        self._on_export()

    def refresh_hosts(self):
        """刷新主机列表"""
        try:
            hosts = self._host_service.list_hosts()
            groups = self._host_service.get_groups()
            self._host_table.load_data(hosts, groups)
            logger.debug(f"Loaded {len(hosts)} hosts")
        except Exception as e:
            logger.error(f"Failed to load hosts: {e}")
            if self._app_signals:
                self._app_signals.global_error.emit(f"加载主机列表失败: {e}")

    # ============ 事件处理 ============

    def _on_add_host(self):
        """添加主机"""
        dlg = HostEditDialog(self)
        if dlg.exec() == HostEditDialog.DialogCode.Accepted:
            data = dlg.get_result()
            if data:
                try:
                    host = self._host_service.add_host(data)
                    self._host_signals.host_added.emit(host.to_dict())
                    self.refresh_hosts()
                    if self._app_signals:
                        self._app_signals.status_message.emit(f"主机 '{host.name}' 添加成功")
                except ServiceError as e:
                    QMessageBox.warning(self, "添加失败", e.message)
                    logger.warning(f"Add host failed: {e.message}")

    def _on_edit_host(self, host_id: int):
        """编辑主机"""
        try:
            host = self._host_service.get_host(host_id)
            host_dict = host.to_dict()
        except ServiceError as e:
            QMessageBox.warning(self, "错误", e.message)
            return

        dlg = HostEditDialog(self, host_data=host_dict)
        if dlg.exec() == HostEditDialog.DialogCode.Accepted:
            data = dlg.get_result()
            if data:
                try:
                    host = self._host_service.update_host(host_id, data)
                    self._host_signals.host_updated.emit(host.to_dict())
                    self.refresh_hosts()
                    if self._app_signals:
                        self._app_signals.status_message.emit(f"主机 '{host.name}' 更新成功")
                except ServiceError as e:
                    QMessageBox.warning(self, "更新失败", e.message)

    def _on_delete_host(self, host_id: int):
        """删除单台主机"""
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除该主机吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._host_service.delete_host(host_id)
                self._host_signals.host_deleted.emit(host_id)
                self._host_table.remove_rows([host_id])
                self.refresh_hosts()
                if self._app_signals:
                    self._app_signals.status_message.emit("主机已删除")
            except Exception as e:
                QMessageBox.warning(self, "删除失败", str(e))

    def _on_delete_selected(self):
        """删除选中主机"""
        selected_ids = self._host_table.get_selected_host_ids()
        if not selected_ids:
            return
        self._on_batch_delete(selected_ids)

    def _on_batch_delete(self, host_ids: list[int]):
        """批量删除"""
        reply = QMessageBox.question(
            self, "确认批量删除",
            f"确定要删除选中的 {len(host_ids)} 台主机吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                count = self._host_service.delete_hosts(host_ids)
                self._host_signals.batch_deleted.emit(count)
                self._host_table.remove_rows(host_ids)
                self.refresh_hosts()
                if self._app_signals:
                    self._app_signals.status_message.emit(f"已删除 {count} 台主机")
            except Exception as e:
                QMessageBox.warning(self, "删除失败", str(e))

    def _on_test_connection(self, host_id: int):
        """测试单台主机连接"""
        self._host_table.set_connection_status(host_id, "testing")

        thread = ConnectionTestThread(self._host_service, host_id)
        thread.result.connect(self._on_test_result)
        thread.finished.connect(thread.deleteLater)
        self._test_threads.append(thread)
        thread.start()

    def _on_test_all(self):
        """批量测试所有主机连接"""
        host_ids = self._host_table.get_selected_host_ids()
        if not host_ids:
            # 没有选中时测试全部（从表格每行读取 host_id）
            for row in range(self._host_table._table.rowCount()):
                hid = self._host_table._get_host_id_from_row(row)
                if hid is not None:
                    host_ids.append(hid)

        if not host_ids:
            QMessageBox.information(self, "批量测试", "当前没有可测试的主机，请先添加主机。")
            return

        if self._app_signals:
            self._app_signals.status_message.emit(f"正在测试 {len(host_ids)} 台主机，请稍候...")

        for hid in host_ids:
            self._host_table.set_connection_status(hid, "testing")
            thread = ConnectionTestThread(self._host_service, hid)
            thread.result.connect(self._on_test_result)
            thread.finished.connect(thread.deleteLater)
            self._test_threads.append(thread)
            thread.start()

    def _on_test_result(self, host_id: str, success: bool, result):
        """连接测试结果回调"""
        hid = int(host_id)
        if success:
            self._host_table.set_connection_status(hid, "connected")
            latency = result.latency_ms if isinstance(result, ConnTestResult) else "?"
            if self._app_signals:
                self._app_signals.status_message.emit(f"主机 {host_id} 连接成功 (延迟: {latency}ms)")
        else:
            self._host_table.set_connection_status(hid, "error")
            error = result.error if isinstance(result, ConnTestResult) else str(result)
            if self._app_signals:
                self._app_signals.status_message.emit(f"主机 {host_id} 连接失败: {error}")

        self._host_signals.connection_tested.emit(host_id, success, result)

    def _on_selection_changed(self, selected_ids: list[int]):
        """选择变化"""
        self._btn_delete_selected.setEnabled(len(selected_ids) > 0)

    def _on_import(self):
        """批量导入"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入主机配置", "",
            "CSV 文件 (*.csv) ;; JSON 文件 (*.json) ;; 所有文件 (*.*)",
        )
        if not path:
            return

        try:
            result = self._host_service.import_hosts(path)
            self._host_signals.import_done.emit(result)
            self.refresh_hosts()

            msg = f"导入完成: 成功 {result.success_count} 台"
            if result.fail_count > 0:
                msg += f", 失败 {result.fail_count} 台"
                if result.errors:
                    msg += "\n\n失败原因:\n" + "\n".join(result.errors[:5])
                    if len(result.errors) > 5:
                        msg += f"\n... 还有 {len(result.errors) - 5} 条"

            QMessageBox.information(self, "导入结果", msg)
            if self._app_signals:
                self._app_signals.status_message.emit(f"导入完成: {result.success_count} 成功")

        except ServiceError as e:
            QMessageBox.warning(self, "导入失败", e.message)

    def _on_export(self):
        """导出配置"""
        path, _ = QFileDialog.getSaveFileName(
            self, "导出主机配置", "hosts.csv",
            "CSV 文件 (*.csv) ;; JSON 文件 (*.json)",
        )
        if not path:
            return

        try:
            selected = self._host_table.get_selected_host_ids()
            self._host_service.export_hosts(path, selected if selected else None)
            if self._app_signals:
                self._app_signals.status_message.emit(f"配置已导出到: {path}")
            QMessageBox.information(self, "导出成功", f"主机配置已导出到:\n{path}")
        except ServiceError as e:
            QMessageBox.warning(self, "导出失败", e.message)

    def _on_inline_save(self, host_id: int, changes: dict):
        """行内编辑保存回调：将变更持久化到数据库"""
        try:
            host = self._host_service.update_host(host_id, changes)
            self._host_signals.host_updated.emit(host.to_dict())
            self.refresh_hosts()
            if self._app_signals:
                self._app_signals.status_message.emit(f"主机 '{host.name}' 已保存")
        except ServiceError as e:
            QMessageBox.warning(self, "保存失败", e.message)
            logger.warning(f"Inline save failed for host {host_id}: {e.message}")
            # 保存失败时刷新表格恢复原始值
            self.refresh_hosts()
