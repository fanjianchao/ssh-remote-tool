from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主窗口

菜单栏、工具栏、状态栏、子页面切换。
集成主机管理、任务编排、执行监控三个页面。
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QStatusBar, QLabel, QMenuBar, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction

from config.settings import get_settings
from config.constants import PAGE_HOST_MANAGER, PAGE_TASK_EDITOR, PAGE_EXECUTION
from signals.app_signals import AppSignals
from views.host_manager_view import HostManagerView
from views.task_editor_view import TaskEditorView
from views.execution_view import ExecutionView
from utils.logger import setup_logger

logger = setup_logger("main_window")


class MainWindow(QMainWindow):
    """应用主窗口"""

    def __init__(self):
        super().__init__()
        self._settings = get_settings()
        self._app_signals = AppSignals()
        self._current_page = PAGE_HOST_MANAGER

        self._setup_ui()
        self._setup_status_bar()
        self._connect_signals()
        self._setup_menu()   # 必须在 _setup_pages 之前，否则 addTab 触发 currentChanged 时 _action_* 还未创建
        self._setup_pages()

        logger.info("Main window initialized")

    def _setup_ui(self):
        """初始化 UI 布局"""
        self.setWindowTitle(f"{self._settings.APP_NAME} v{self._settings.APP_VERSION}")
        self.setMinimumSize(self._settings.WINDOW_MIN_WIDTH, self._settings.WINDOW_MIN_HEIGHT)
        self.resize(self._settings.WINDOW_WIDTH, self._settings.WINDOW_HEIGHT)

        # 中央容器
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 页面切换 TabWidget
        self._tab_widget = QTabWidget()
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.setMovable(False)
        self._tab_widget.currentChanged.connect(self._on_page_changed)

        layout.addWidget(self._tab_widget)

        # 加载主题样式
        self._apply_theme()

    def _setup_pages(self):
        """初始化三个页面并添加到 TabWidget"""
        # 主机管理页
        self._page_host = HostManagerView()
        self._page_host.set_app_signals(self._app_signals)

        # 任务编排页
        self._page_task = TaskEditorView()
        self._page_task.set_app_signals(self._app_signals)

        # 执行监控页
        self._page_execution = ExecutionView()
        self._page_execution.set_app_signals(self._app_signals)

        # 连接任务编排 → 执行监控
        self._page_task.execute_task_requested.connect(self._on_execute_task)
        self._page_task.task_selected.connect(self._on_task_selected)

        # 添加到 TabWidget
        self._tab_widget.addTab(self._page_host, "🖥  主机管理")
        self._tab_widget.addTab(self._page_task, "📋  任务编排")
        self._tab_widget.addTab(self._page_execution, "📊  执行监控")

    def _setup_menu(self):
        """初始化菜单栏"""
        menu_bar = self.menuBar()

        # 文件菜单
        file_menu = menu_bar.addMenu("文件(&F)")

        # 主机导入导出
        self._action_import_hosts = QAction("导入主机信息(&I)", self)
        self._action_import_hosts.setShortcut("Ctrl+Shift+I")
        self._action_import_hosts.triggered.connect(self._on_import_hosts)
        file_menu.addAction(self._action_import_hosts)

        self._action_export_hosts = QAction("导出主机信息(&E)", self)
        self._action_export_hosts.setShortcut("Ctrl+Shift+E")
        self._action_export_hosts.triggered.connect(self._on_export_hosts)
        file_menu.addAction(self._action_export_hosts)

        file_menu.addSeparator()

        # 任务导入导出
        self._action_import_task = QAction("导入任务(&M)", self)
        self._action_import_task.setShortcut("Ctrl+I")
        self._action_import_task.triggered.connect(self._on_import_task)
        file_menu.addAction(self._action_import_task)

        self._action_export_task = QAction("导出任务(&X)", self)
        self._action_export_task.setShortcut("Ctrl+E")
        self._action_export_task.triggered.connect(self._on_export_task)
        file_menu.addAction(self._action_export_task)

        file_menu.addSeparator()

        exit_action = QAction("退出(&Q)", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # 初始状态：全部禁用，等待页面切换后更新
        self._update_file_menu_state(PAGE_HOST_MANAGER, has_task_selected=False)

        # 工具菜单
        tools_menu = menu_bar.addMenu("工具(&T)")
        settings_action = QAction("设置(&S)", self)
        settings_action.triggered.connect(lambda: self.statusBar().showMessage("设置面板开发中...", 3000))
        tools_menu.addAction(settings_action)

        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助(&H)")
        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_status_bar(self):
        """初始化状态栏"""
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        # 左侧：任务名称 + 耗时（默认隐藏）
        self._task_status_label = QLabel("")
        self._task_status_label.setStyleSheet("color: #1976D2; font-size: 12px; font-weight: bold; padding-left: 8px;")
        self._task_status_label.setVisible(False)
        self._status_bar.addWidget(self._task_status_label)
        # 右侧：状态信息
        self._status_label = QLabel("就绪")
        self._status_bar.addPermanentWidget(self._status_label)

    def _connect_signals(self):
        """连接信号"""
        self._app_signals.switch_page.connect(self._switch_to_page)
        self._app_signals.status_message.connect(self._show_status_message)
        self._app_signals.global_error.connect(self._show_global_error)
        self._app_signals.elapsed_updated.connect(self._on_elapsed_updated)

    def _apply_theme(self):
        """应用主题样式"""
        if self._settings.THEME == "dark":
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #1e1e2e;
                    color: #cdd6f4;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                    font-size: 14px;
                }
                QMenuBar {
                    background-color: #181825;
                    border-bottom: 1px solid #313244;
                }
                QMenuBar::item:selected {
                    background-color: #313244;
                }
                QMenu {
                    background-color: #1e1e2e;
                    border: 1px solid #313244;
                }
                QMenu::item {
                    padding: 6px 24px 6px 8px;
                }
                QMenu::item:selected {
                    background-color: #313244;
                }
                QMenu::item:disabled {
                    color: #666666;
                }
                QTabWidget::pane {
                    border: none;
                    background-color: #1e1e2e;
                }
                QToolTip {
                    background-color: #FFFFFF;
                    color: #D32F2F;
                    border: 1px solid #E0E0E0;
                    padding: 6px;
                }
                QTabBar::tab {
                    background-color: #181825;
                    color: #a6adc8;
                    padding: 10px 24px;
                    margin-right: 2px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    font-size: 14px;
                }
                QTabBar::tab:selected {
                    background-color: #1e1e2e;
                    color: #cdd6f4;
                    border-bottom: 2px solid #89b4fa;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #313244;
                }
                QStatusBar {
                    background-color: #181825;
                    color: #a6adc8;
                    border-top: 1px solid #313244;
                }
                QPushButton {
                    background-color: #313244;
                    color: #cdd6f4;
                    border: 1px solid #45475a;
                    padding: 6px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #45475a;
                }
                QPushButton:pressed {
                    background-color: #585b70;
                }
            """)
        else:
            # Light 主题
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #FFFFFF;
                    color: #333333;
                    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                    font-size: 14px;
                }
                QMenuBar {
                    background-color: #F5F5F5;
                    border-bottom: 1px solid #E0E0E0;
                }
                QMenuBar::item:selected {
                    background-color: #E0E0E0;
                }
                QMenu {
                    background-color: #FFFFFF;
                    border: 1px solid #E0E0E0;
                }
                QMenu::item {
                    padding: 6px 24px 6px 8px;
                }
                QMenu::item:selected {
                    background-color: #E0E0E0;
                }
                QMenu::item:disabled {
                    color: #999999;
                }
                QTabWidget::pane {
                    border: none;
                    background-color: #FFFFFF;
                }
                QToolTip {
                    background-color: #FFFFFF;
                    color: #D32F2F;
                    border: 1px solid #E0E0E0;
                    padding: 6px;
                }
                QTabBar::tab {
                    background-color: #F5F5F5;
                    color: #666666;
                    padding: 10px 24px;
                    margin-right: 2px;
                    border-top-left-radius: 6px;
                    border-top-right-radius: 6px;
                    font-size: 14px;
                }
                QTabBar::tab:selected {
                    background-color: #FFFFFF;
                    color: #333333;
                    border-bottom: 2px solid #1976D2;
                }
                QTabBar::tab:hover:!selected {
                    background-color: #E0E0E0;
                }
                QStatusBar {
                    background-color: #F5F5F5;
                    color: #666666;
                    border-top: 1px solid #E0E0E0;
                }
                QPushButton {
                    background-color: #E0E0E0;
                    color: #333333;
                    border: 1px solid #D0D0D0;
                    padding: 6px 16px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #D0D0D0;
                }
                QPushButton:pressed {
                    background-color: #BDBDBD;
                }
            """)

    # ============ 页面切换 ============

    def _switch_to_page(self, index: int):
        """切换页面"""
        if 0 <= index < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(index)
            self._current_page = index

    def _on_page_changed(self, index: int):
        """页面切换事件"""
        self._current_page = index
        page_names = ["主机管理", "任务编排", "执行监控"]
        self._status_label.setText(f"当前页面: {page_names[index]}")

        # 切换到任务编排页时刷新任务列表
        if index == PAGE_TASK_EDITOR and hasattr(self, '_page_task'):
            self._page_task.refresh_tasks()
        # 切换到主机管理页时刷新主机列表
        if index == PAGE_HOST_MANAGER and hasattr(self, '_page_host'):
            self._page_host.refresh_hosts()

        # 更新文件菜单 enable/disable 状态
        has_task = False
        if hasattr(self, '_page_task'):
            has_task = self._page_task.has_task_selected()
        self._update_file_menu_state(index, has_task_selected=has_task)

    def _update_file_menu_state(self, page_index: int, has_task_selected: bool = False):
        """根据当前页面更新文件菜单各项的启用状态"""
        on_host = (page_index == PAGE_HOST_MANAGER)
        on_task = (page_index == PAGE_TASK_EDITOR)

        self._action_import_hosts.setEnabled(on_host)
        self._action_export_hosts.setEnabled(on_host)
        # 导入任务/导出任务：在任务编排页始终可用（无选中时 export 会弹提示拒绝）
        self._action_import_task.setEnabled(on_task)
        self._action_export_task.setEnabled(on_task)

    # ============ 任务执行流程 ============

    def _on_execute_task(self, task: object, host_ids: list[int]):
        """
        从任务编排页接收到执行请求。

        1. 切换到执行监控页
        2. 启动任务执行
        """
        # 在状态栏左侧显示任务名称 + 耗时
        task_name = getattr(task, 'name', str(task))
        self._task_name_text = task_name
        self._task_status_label.setText(f"📋 任务名称：{task_name}    总耗时： 0.0秒")
        self._task_status_label.setVisible(True)

        self._switch_to_page(PAGE_EXECUTION)
        self._page_execution.execute_task(task, host_ids)
        self._show_status_message("任务开始执行...")

    def _on_task_selected(self, task: object):
        """任务选中事件（由执行监控页需要时使用）"""
        pass

    # ============ 菜单动作处理 ============

    def _on_import_hosts(self):
        """菜单：导入主机信息 → 转发给主机管理页"""
        self._page_host.trigger_import()

    def _on_export_hosts(self):
        """菜单：导出主机信息 → 转发给主机管理页"""
        self._page_host.trigger_export()

    def _on_import_task(self):
        """菜单：导入任务 → 转发给任务编排页"""
        self._page_task.trigger_import()

    def _on_export_task(self):
        """菜单：导出任务 → 转发给任务编排页"""
        self._page_task.trigger_export()

    # ============ 状态栏和消息 ============

    def _on_elapsed_updated(self, elapsed_text: str):
        """更新状态栏耗时显示"""
        task_name = getattr(self, '_task_name_text', '')
        if task_name:
            self._task_status_label.setText(f"📋 任务名称：{task_name}    总耗时： {elapsed_text}")

    def _show_status_message(self, message: str, duration: int = 3000):
        """显示状态栏消息"""
        self._status_bar.showMessage(message, duration)

    def _show_global_error(self, error: str):
        """显示全局错误"""
        QMessageBox.critical(self, "错误", error)

    def _show_about(self):
        """显示关于对话框"""
        QMessageBox.about(
            self,
            "关于",
            f"{self._settings.APP_NAME} v{self._settings.APP_VERSION}\n\n"
            "SSH 远程运维工具\n"
            "支持批量主机管理、文件传输和命令执行\n\n"
            "作者：fan JC\n"
            "邮箱：1071295829@qq.com",
        )

    # ============ 属性 ============

    @property
    def app_signals(self) -> AppSignals:
        """暴露全局信号实例"""
        return self._app_signals

    def closeEvent(self, event):
        """窗口关闭事件"""
        self._app_signals.app_closing.emit()
        logger.info("Main window closing")
        event.accept()
