from __future__ import annotations
# -*- coding: utf-8 -*-
"""
任务编排页

任务列表侧栏 + 步骤画布区，步骤编辑通过弹窗完成。
支持创建/编辑/删除/复制任务，可视化编排步骤。
"""

import json
import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QListWidget, QListWidgetItem, QLineEdit,
    QMessageBox, QMenu, QScrollArea, QCheckBox, QInputDialog,
    QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer, QEvent, QPoint
from PySide6.QtGui import QAction

from config.constants import StepType, DEFAULT_SSH_TIMEOUT, DEFAULT_WORKDIR
from core.task_service import TaskService
from core.task_engine import TaskEngine
from core.step_template_service import StepTemplateService
from data.models import Task, TaskStep, ServiceError, ValidationResult
from signals.task_signals import TaskSignals
from signals.app_signals import AppSignals
from views.step_edit_dialog import StepEditDialog
from views.step_template_dialog import StepTemplateDialog
from utils.logger import setup_logger

logger = setup_logger("task_editor_view")


class StepCard(QWidget):
    """步骤卡片（画布中的单个步骤）"""

    remove_requested = Signal(int)  # step_index
    move_up_requested = Signal(int)
    move_down_requested = Signal(int)
    edit_requested = Signal(int)
    copy_requested = Signal(int)
    save_template_requested = Signal(int)

    STEP_ICONS = {
        "ssh_command": "⌨️",
        "sftp_upload": "📤",
        "sftp_download": "📥",
    }

    STEP_TYPE_LABELS = {
        "ssh_command": "命令执行",
        "sftp_upload": "文件上传",
        "sftp_download": "文件下载",
    }

    def __init__(self, index: int, step_data: dict, parent=None):
        super().__init__(parent)
        self._index = index
        self._step_data = step_data
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # 序号
        self._index_label = QLabel(f"{self._index + 1}")
        self._index_label.setFixedWidth(24)
        self._index_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._index_label.setStyleSheet("color: #666666; font-size: 14px; font-weight: bold;")
        layout.addWidget(self._index_label)

        # 连接线
        self._line_label = QLabel("│")
        self._line_label.setFixedWidth(12)
        self._line_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._line_label.setStyleSheet("color: #D0D0D0; font-size: 18px;")
        layout.addWidget(self._line_label)

        # 类型图标 + 步骤名称
        step_type = self._step_data.get("step_type", "ssh_command")
        icon = self.STEP_ICONS.get(step_type, "📋")
        type_label = self.STEP_TYPE_LABELS.get(step_type, step_type)
        step_name = self._step_data.get("name", "未命名步骤")

        self._icon_label = QLabel(icon)
        self._icon_label.setFixedWidth(24)
        layout.addWidget(self._icon_label)

        self._name_label = QLabel(f"<b>{step_name}</b>")
        self._name_label.setStyleSheet("color: #333333; font-size: 13px;")
        layout.addWidget(self._name_label)

        self._type_label = QLabel(type_label)
        self._type_label.setStyleSheet("color: #666666; font-size: 11px;")
        layout.addWidget(self._type_label)

        layout.addStretch()

        # 目标主机标签
        target_ids = self._step_data.get("target_host_ids", [])
        if target_ids:
            host_label = QLabel(f"🎯 {len(target_ids)} 台主机")
            host_label.setStyleSheet("color: #1976D2; font-size: 11px;")
            layout.addWidget(host_label)

        # 步骤详情 tooltip：使用页面全局自定义 tooltip，避免默认 Tooltip 黑底问题
        self.setToolTip(self._build_tooltip().replace("\n", "<br>"))

        # 图标按钮通用样式（纯图标，正方形）
        icon_btn_style = """
            QPushButton {
                background-color: #E8E8E8;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                font-size: 14px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #D0D0D0;
                border-color: #1976D2;
            }
        """
        icon_btn_size = 28

        # 编辑按钮
        self._btn_edit = QPushButton("✏️")
        self._btn_edit.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_edit.setToolTip("编辑步骤")
        self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_edit.setStyleSheet(icon_btn_style)
        self._btn_edit.clicked.connect(lambda: self.edit_requested.emit(self._index))
        layout.addWidget(self._btn_edit)

        # 复制按钮
        self._btn_copy = QPushButton("📋")
        self._btn_copy.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_copy.setToolTip("复制步骤（在当前步骤下方插入副本）")
        self._btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy.setStyleSheet(icon_btn_style)
        self._btn_copy.clicked.connect(lambda: self.copy_requested.emit(self._index))
        layout.addWidget(self._btn_copy)

        # 保存为模板按钮
        self._btn_save_tpl = QPushButton("📌")
        self._btn_save_tpl.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_save_tpl.setToolTip("保存为模板（可在其他任务中复用）")
        self._btn_save_tpl.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save_tpl.setStyleSheet(icon_btn_style)
        self._btn_save_tpl.clicked.connect(lambda: self.save_template_requested.emit(self._index))
        layout.addWidget(self._btn_save_tpl)

        # 分隔
        sep = QLabel("|")
        sep.setFixedWidth(8)
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sep.setStyleSheet("color: #D0D0D0; font-size: 14px; font-weight: bold;")
        layout.addWidget(sep)

        # 上移按钮
        self._btn_up = QPushButton("▲")
        self._btn_up.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_up.setToolTip("上移步骤")
        self._btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_up.setStyleSheet(icon_btn_style)
        self._btn_up.clicked.connect(lambda: self.move_up_requested.emit(self._index))
        layout.addWidget(self._btn_up)

        # 下移按钮
        self._btn_down = QPushButton("▼")
        self._btn_down.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_down.setToolTip("下移步骤")
        self._btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_down.setStyleSheet(icon_btn_style)
        self._btn_down.clicked.connect(lambda: self.move_down_requested.emit(self._index))
        layout.addWidget(self._btn_down)

        # 删除按钮（红色风格）
        self._btn_remove = QPushButton("✕")
        self._btn_remove.setFixedSize(icon_btn_size, icon_btn_size)
        self._btn_remove.setToolTip("删除步骤")
        self._btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_remove.setStyleSheet("""
            QPushButton {
                background-color: #FFEBEE;
                border: 1px solid #EF9A9A;
                border-radius: 4px;
                color: #E53935;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #FFCDD2;
                border-color: #E53935;
                color: #C62828;
            }
        """)
        self._btn_remove.clicked.connect(lambda: self.remove_requested.emit(self._index))
        layout.addWidget(self._btn_remove)

        # 卡片样式
        self.setStyleSheet("""
            StepCard {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
            }
        """)

        # 双击卡片打开编辑
        self.mouseDoubleClickEvent = self._on_double_click

    def _build_tooltip(self) -> str:
        """构建步骤详情 tooltip"""
        d = self._step_data
        lines = [f"类型: {d.get('step_type', '')}"]
        if d.get("command"):
            lines.append(f"命令: {d['command'][:100]}")
        if d.get("local_path"):
            lines.append(f"本地路径: {d['local_path']}")
        if d.get("remote_path"):
            lines.append(f"远程路径: {d['remote_path']}")
        if d.get("timeout"):
            lines.append(f"超时: {d['timeout']}s")
        tooltip_text = "<br>".join(lines)
        return tooltip_text

    def _on_double_click(self, event):
        """双击卡片打开编辑弹窗"""
        self.edit_requested.emit(self._index)

    def update_index(self, new_index: int):
        """更新序号"""
        self._index = new_index
        self._index_label.setText(str(new_index + 1))


class TaskEditorView(QWidget):
    """任务编排页面"""

    # 信号
    execute_task_requested = Signal(object, list)  # Task, host_ids
    task_selected = Signal(object)  # Task 对象（供 ExecutionView 获取）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_service = TaskService()
        self._template_service = StepTemplateService()
        self._task_signals = TaskSignals()
        self._app_signals: AppSignals | None = None
        self._current_task: Task | None = None
        self._steps: list[dict] = []  # 当前编辑中的步骤列表
        self._available_hosts: list[dict] = []  # 可用主机列表
        self._inline_editing: bool = False  # 是否正在行内编辑任务名称

        self._setup_ui()
        self._init_tooltip_manager()
        self._connect_signals()
        self.refresh_tasks()

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

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- 主布局（左侧任务列表 + 中央步骤画布） ---
        main_splitter = QHBoxLayout()
        main_splitter.setSpacing(0)

        # == 左侧：任务列表 ==
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 8, 6, 8)
        left_layout.setSpacing(8)

        left_title_bar = QHBoxLayout()
        left_title_bar.setContentsMargins(0, 0, 0, 0)
        left_title_bar.setSpacing(0)

        left_title = QLabel("已保存任务")
        left_title.setStyleSheet("font-size: 13px; font-weight: bold; color: #666666;")
        left_title_bar.addWidget(left_title)

        left_title_bar.addStretch()

        btn_new = self._make_small_btn("➕ 新建任务", self._on_new_task)
        left_title_bar.addWidget(btn_new)

        left_layout.addLayout(left_title_bar)

        self._task_list = QListWidget()
        self._task_list.setStyleSheet("""
            QListWidget {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                color: #333333;
                font-size: 13px;
            }
            QListWidget::item {
                border-bottom: 1px solid #E0E0E0;
            }
            QListWidget::item:selected {
                background-color: #E8F5E9;
                color: #1B5E20;
            }
            QListWidget::item:hover:!selected {
                background-color: #E3F2FD;
                color: #1565C0;
            }
        """)
        self._task_list.currentRowChanged.connect(self._on_task_selected)
        self._task_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._task_list.customContextMenuRequested.connect(self._show_task_context_menu)
        self._task_list.viewport().installEventFilter(self)  # 点击空白区域取消选中
        self._task_list.installEventFilter(self)
        left_layout.addWidget(self._task_list)

        main_splitter.addWidget(left_panel)

        # == 中央：步骤画布 ==
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(12, 8, 12, 8)
        center_layout.setSpacing(8)

        # 任务信息区
        info_bar = QHBoxLayout()
        info_bar.setSpacing(8)

        name_label = QLabel("任务名称")
        name_label.setFixedWidth(60)
        name_label.setStyleSheet("color: #666666; font-size: 13px;")
        info_bar.addWidget(name_label)

        self._task_name_input = QLineEdit()
        self._task_name_input.setPlaceholderText("请输入任务名称")
        self._task_name_input.setStyleSheet("""
            QLineEdit {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QLineEdit:focus { border-color: #1976D2; }
        """)
        info_bar.addWidget(self._task_name_input, 1)
        self._task_name_input.editingFinished.connect(self._on_name_editing_finished)

        desc_label = QLabel("任务描述")
        desc_label.setFixedWidth(60)
        desc_label.setStyleSheet("color: #666666; font-size: 13px;")
        info_bar.addWidget(desc_label)

        self._task_desc_input = QLineEdit()
        self._task_desc_input.setPlaceholderText("请输入任务描述（可选）")
        self._task_desc_input.setStyleSheet("""
            QLineEdit {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QLineEdit:focus { border-color: #1976D2; }
        """)
        info_bar.addWidget(self._task_desc_input, 1)

        center_layout.addLayout(info_bar)

        # 步骤画布（可滚动）
        canvas_label = QLabel("执行步骤（按顺序执行，双击或点击✏️编辑）")
        canvas_label.setStyleSheet("color: #666666; font-size: 12px;")
        center_layout.addWidget(canvas_label)

        self._canvas_scroll = QScrollArea()
        self._canvas_scroll.setWidgetResizable(True)
        self._canvas_scroll.setStyleSheet("""
            QScrollArea {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
            }
            QScrollBar:vertical {
                background-color: #F5F5F5;
                width: 8px;
            }
            QScrollBar::handle:vertical {
                background-color: #D0D0D0;
                border-radius: 4px;
            }
        """)

        self._canvas_container = QWidget()
        self._canvas_container.setStyleSheet("background-color: transparent;")
        self._canvas_layout = QVBoxLayout(self._canvas_container)
        self._canvas_layout.setContentsMargins(8, 8, 8, 8)
        self._canvas_layout.setSpacing(4)
        self._canvas_layout.addStretch()

        self._canvas_scroll.setWidget(self._canvas_container)
        center_layout.addWidget(self._canvas_scroll, 1)

        # 添加步骤按钮
        add_step_bar = QHBoxLayout()
        add_step_bar.setSpacing(8)

        self._btn_add_cmd = self._make_small_btn("⌨️ 添加命令步骤", lambda: self._add_step("ssh_command"))
        self._btn_add_cmd.setEnabled(False)
        add_step_bar.addWidget(self._btn_add_cmd)

        self._btn_add_upload = self._make_small_btn("📤 添加上传步骤", lambda: self._add_step("sftp_upload"))
        self._btn_add_upload.setEnabled(False)
        add_step_bar.addWidget(self._btn_add_upload)

        self._btn_add_download = self._make_small_btn("📥 添加下载步骤", lambda: self._add_step("sftp_download"))
        self._btn_add_download.setEnabled(False)
        add_step_bar.addWidget(self._btn_add_download)

        self._btn_add_from_template = self._make_small_btn("📦 从模板添加", self._on_add_from_template)
        self._btn_add_from_template.setEnabled(False)
        add_step_bar.addWidget(self._btn_add_from_template)

        self._btn_manage_templates = self._make_small_btn("📋 模板管理", self._on_manage_templates)
        add_step_bar.addWidget(self._btn_manage_templates)

        add_step_bar.addStretch()

        # 保存按钮（右对齐）
        self._btn_save = self._make_small_btn("💾 保存", self._on_save_task)
        add_step_bar.addWidget(self._btn_save)
        center_layout.addLayout(add_step_bar)

        # 目标主机选择面板
        host_panel_label = QLabel("目标主机（执行时将应用到所有步骤）")
        host_panel_label.setStyleSheet("color: #666666; font-size: 12px; margin-top: 8px;")
        center_layout.addWidget(host_panel_label)

        host_panel = QWidget()
        host_panel.setStyleSheet("""
            QWidget { background-color: #F5F5F5; border: 1px solid #E0E0E0; border-radius: 4px; }
        """)
        host_panel_layout = QVBoxLayout(host_panel)
        host_panel_layout.setContentsMargins(8, 4, 8, 4)
        host_panel_layout.setSpacing(2)

        # 搜索 + 全选行（紧凑）
        host_toolbar = QHBoxLayout()
        host_toolbar.setSpacing(6)
        self._host_search_input = QLineEdit()
        self._host_search_input.setFixedWidth(180)
        self._host_search_input.setPlaceholderText("🔍 搜索主机...")
        self._host_search_input.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 3px 6px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #1976D2; }
        """)
        self._host_search_input.textChanged.connect(self._on_host_search_changed)
        host_toolbar.addWidget(self._host_search_input)

        host_toolbar.addStretch()

        self._host_select_all_cb = QCheckBox("全选")
        self._host_select_all_cb.setChecked(True)
        self._host_select_all_cb.setStyleSheet("color: #333333; font-size: 12px;")
        self._host_select_all_cb.stateChanged.connect(self._on_host_select_all_changed)
        host_toolbar.addWidget(self._host_select_all_cb)

        self._host_count_label = QLabel("")
        self._host_count_label.setStyleSheet("color: #666666; font-size: 11px;")
        host_toolbar.addWidget(self._host_count_label)

        host_panel_layout.addLayout(host_toolbar)

        # 可滚动的主机 checkbox 列表
        self._host_check_scroll = QScrollArea()
        self._host_check_scroll.setWidgetResizable(True)
        self._host_check_scroll.setMinimumHeight(80)
        self._host_check_scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: #F5F5F5;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #D0D0D0;
                border-radius: 3px;
            }
        """)
        self._host_check_container = QWidget()
        self._host_check_container.setStyleSheet("background-color: transparent;")
        self._host_check_layout = QVBoxLayout(self._host_check_container)
        self._host_check_layout.setContentsMargins(4, 2, 4, 2)
        self._host_check_layout.setSpacing(1)
        self._host_check_layout.addStretch()
        self._host_check_scroll.setWidget(self._host_check_container)
        host_panel_layout.addWidget(self._host_check_scroll)

        center_layout.addWidget(host_panel, 1)

        main_splitter.addWidget(center_panel)

        layout.addLayout(main_splitter)

        # --- 底部操作栏 ---
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(16, 8, 16, 12)
        bottom_bar.setSpacing(12)

        bottom_bar.addStretch()

        self._btn_execute = QPushButton("🚀 执行任务")
        self._btn_execute.setFixedSize(140, 38)
        self._btn_execute.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_execute.clicked.connect(self._on_execute)
        self._btn_execute.setStyleSheet("""
            QPushButton {
                background-color: #43A047;
                color: #FFFFFF;
                border: none;
                padding: 8px 24px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #388E3C; }
            QPushButton:pressed { background-color: #2E7D32; }
        """)
        bottom_bar.addWidget(self._btn_execute)

        layout.addLayout(bottom_bar)

        # 页面样式
        self.setStyleSheet("background-color: #FFFFFF;")

    def _connect_signals(self):
        """连接信号"""
        pass


    # ============ 主机选择面板 ============

    def _refresh_host_check_list(self):
        """刷新目标主机 checkbox 列表"""
        # 清除旧的 checkbox（立即移除，不使用 deleteLater 避免 UI 遍历时残留）
        while self._host_check_layout.count() > 0:
            item = self._host_check_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        for host in self._available_hosts:
            name = host.get("name", "")
            host_addr = host.get("host", "")
            group = host.get("group_name", "")
            display = f"{name} ({host_addr})"
            if group:
                display += f" [{group}]"
            cb = QCheckBox(display)
            cb.setProperty("host_id", host.get("id"))
            cb.setStyleSheet("color: #333333; font-size: 12px;")
            cb.setChecked(True)
            cb.stateChanged.connect(self._on_host_check_changed)
            self._host_check_layout.addWidget(cb)
        self._host_check_layout.addStretch()
        self._update_host_count_label()
        # 所有子 checkbox 均为 checked=True，直接同步全选状态
        self._host_select_all_cb.blockSignals(True)
        self._host_select_all_cb.setChecked(len(self._available_hosts) > 0)
        self._host_select_all_cb.blockSignals(False)

    def _update_host_count_label(self):
        """更新已选主机计数"""
        total = len(self._available_hosts)
        selected = self._get_selected_host_ids()
        self._host_count_label.setText(f"已选 {len(selected)}/{total} 台")

    def _on_host_search_changed(self, text: str):
        """搜索主机"""
        keyword = text.strip().lower()
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                if keyword:
                    cb.setVisible(keyword in cb.text().lower())
                else:
                    cb.setVisible(True)
        self._sync_select_all_checkbox()

    def _on_host_select_all_changed(self, state):
        """全选/取消全选"""
        checked = state == Qt.CheckState.Checked.value
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                cb.blockSignals(True)
                cb.setChecked(checked)
                cb.blockSignals(False)
        self._update_host_count_label()
        self._sync_select_all_checkbox()

    def _on_host_check_changed(self):
        """子 checkbox 状态变化时同步全选状态"""
        self._update_host_count_label()
        self._sync_select_all_checkbox()

    def _get_selected_host_ids(self) -> list[int]:
        """获取当前面板选中的主机 ID 列表"""
        selected = []
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                if cb.isChecked():
                    host_id = cb.property("host_id")
                    if host_id:
                        selected.append(host_id)
        return selected

    def _restore_host_selection(self, selected_ids: set[int]):
        """恢复主机面板的选中状态（refresh_tasks 后会被重置为全选）"""
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                host_id = cb.property("host_id")
                if host_id is not None:
                    cb.setChecked(host_id in selected_ids)
        self._update_host_count_label()
        self._sync_select_all_checkbox()

    def _sync_select_all_checkbox(self):
        """同步「全选」checkbox 状态（根据所有子 checkbox 的选中状态）"""
        total_visible = 0
        total_checked = 0
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                # isHidden() 只检查控件自身的 hide 状态，不受父控件可见性影响
                # 避免初始化时页面非活动 tab 导致 isVisible() 全部返回 False
                if not cb.isHidden():
                    total_visible += 1
                    if cb.isChecked():
                        total_checked += 1
        self._host_select_all_cb.blockSignals(True)
        self._host_select_all_cb.setChecked(total_visible > 0 and total_checked == total_visible)
        self._host_select_all_cb.blockSignals(False)

    def _restore_host_selection(self, selected_ids: set[int]):
        """恢复主机面板的选中状态（refresh_tasks 后会被重置为全选）"""
        for i in range(self._host_check_layout.count()):
            item = self._host_check_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), QCheckBox):
                cb = item.widget()
                host_id = cb.property("host_id")
                if host_id is not None:
                    cb.setChecked(host_id in selected_ids)
        self._update_host_count_label()
        self._sync_select_all_checkbox()

    def _restore_task_selection(self, task_id: int):
        """恢复任务列表的选中状态（refresh_tasks 后会被重置为未选中）"""
        for i in range(self._task_list.count()):
            item = self._task_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == task_id:
                self._task_list.setCurrentRow(i)
                break

    # ============ 公共方法 ============

    def set_app_signals(self, signals: AppSignals):
        """设置全局信号"""
        self._app_signals = signals

    @property
    def task_signals(self) -> TaskSignals:
        return self._task_signals

    def has_task_selected(self) -> bool:
        """返回当前是否有任务被选中（供主窗口菜单状态判断使用）"""
        return self._current_task is not None

    def trigger_import(self):
        """触发导入任务（由主窗口菜单调用）"""
        self._on_import_task()

    def trigger_export(self):
        """触发导出任务（由主窗口菜单调用）"""
        self._on_export_task()

    def refresh_tasks(self):
        """刷新任务列表"""
        try:
            tasks = self._task_service.list_tasks()
            self._task_list.clear()
            for row, task in enumerate(tasks):
                # 任务名称
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, task.id)
                if task.description:
                    item.setToolTip(task.description)
                item.setSizeHint(QSize(260, 42))
                self._task_list.addItem(item)

                # 自定义 widget：任务名 + 操作按钮
                item_widget = QWidget()
                item_widget.setStyleSheet("background: transparent;")
                item_layout = QHBoxLayout(item_widget)
                item_layout.setContentsMargins(6, 2, 4, 2)
                item_layout.setSpacing(0)

                name_label = QLabel(f"📋 {task.name}")
                name_label.setStyleSheet("color: #333333; font-size: 13px;")
                name_label.setCursor(Qt.CursorShape.IBeamCursor)
                item_layout.addWidget(name_label)

                item_layout.addStretch()

                # 执行按钮
                btn_exec = QPushButton("🚀")
                btn_exec.setFixedSize(28, 28)
                btn_exec.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_exec.setToolTip(f"执行任务: {task.name}")
                btn_exec.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        font-size: 14px;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #E8F5E9;
                        border-radius: 4px;
                    }
                """)
                task_id = task.id
                btn_exec.clicked.connect(lambda checked, t=task_id, r=row: self._on_execute_from_list(t, r))
                item_layout.addWidget(btn_exec)

                # 复制按钮
                btn_copy = QPushButton("📋")
                btn_copy.setFixedSize(28, 28)
                btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_copy.setToolTip(f"复制任务: {task.name}")
                btn_copy.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        font-size: 13px;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #E3F2FD;
                        border-radius: 4px;
                    }
                """)
                btn_copy.clicked.connect(lambda checked, t=task_id, r=row: self._on_copy_from_list(t, r))
                item_layout.addWidget(btn_copy)

                # 删除按钮
                btn_del = QPushButton("🗑️")
                btn_del.setFixedSize(28, 28)
                btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_del.setToolTip(f"删除任务: {task.name}")
                btn_del.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: none;
                        font-size: 13px;
                        padding: 0px;
                    }
                    QPushButton:hover {
                        background-color: #FFEBEE;
                        border-radius: 4px;
                    }
                """)
                btn_del.clicked.connect(lambda checked, t=task_id, r=row: self._on_delete_from_list(t, r))
                item_layout.addWidget(btn_del)

                self._task_list.setItemWidget(item, item_widget)

                # 双击名称标签进入编辑
                name_label.mouseDoubleClickEvent = lambda e, tid=task_id, lbl=name_label, ly=item_layout: self._start_inline_name_edit(e, tid, lbl, ly)

            # 刷新可用主机
            hosts = self._task_service.get_available_hosts()
            self._available_hosts = [h.to_dict() for h in hosts]
            self._refresh_host_check_list()
            logger.debug(f"Loaded {len(tasks)} tasks, {len(hosts)} hosts")
        except Exception as e:
            logger.error(f"Failed to load tasks: {e}")

    def get_current_task(self) -> Task | None:
        """获取当前选中的任务对象"""
        return self._current_task

    # ============ 行内编辑任务名称 ============

    def _set_step_buttons_enabled(self, enabled: bool):
        """启用/禁用添加步骤按钮"""
        for btn in (self._btn_add_cmd, self._btn_add_upload, self._btn_add_download, self._btn_add_from_template):
            btn.setEnabled(enabled)

    def _start_inline_name_edit(self, event, task_id: int, label: QLabel, layout: QHBoxLayout):
        """双击名称标签，替换为 QLineEdit 进入编辑"""
        if self._inline_editing:
            return
        self._inline_editing = True

        old_name = label.text().replace("📋 ", "")

        # 自定义 QLineEdit，重写 focusOutEvent 以确保焦点丢失时退出编辑
        class _InlineEdit(QLineEdit):
            def __init__(self, text, parent=None):
                super().__init__(text, parent)
                self._on_finish = None  # type: ignore

            def focusOutEvent(self, ev):
                super().focusOutEvent(ev)
                if self._on_finish:
                    self._on_finish()

            def keyPressEvent(self, ev):
                if ev.key() == Qt.Key.Key_Escape:
                    # Escape 取消编辑，恢复原名
                    self.setText(old_name)
                    self.clearFocus()
                    return
                super().keyPressEvent(ev)

        line_edit = _InlineEdit(old_name)
        line_edit.setStyleSheet("""
            QLineEdit {
                background-color: #FFFFFF;
                color: #333333;
                border: 1px solid #1976D2;
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 13px;
            }
        """)
        line_edit.selectAll()
        line_edit.setFrame(False)

        # 替换 label 为 line_edit
        layout.replaceWidget(label, label)
        label.deleteLater()
        layout.removeWidget(label)
        layout.insertWidget(0, line_edit)
        line_edit.setFocus()

        def finish_edit():
            if not self._inline_editing:
                return
            new_name = line_edit.text().strip()
            if new_name and new_name != old_name:
                try:
                    self._task_service.update_task(task_id, {
                        "name": new_name,
                        "description": self._current_task.description if self._current_task and self._current_task.id == task_id else "",
                        "steps": [dict(s) for s in self._steps] if self._current_task and self._current_task.id == task_id else [],
                    })
                    if self._app_signals:
                        self._app_signals.status_message.emit(f"任务名称已更新: {new_name}")
                except ServiceError as e:
                    QMessageBox.warning(self, "更新失败", e.message)
            # 刷新列表恢复正常显示
            self._inline_editing = False
            self.refresh_tasks()
            # 恢复选中状态
            if self._current_task:
                for i in range(self._task_list.count()):
                    item = self._task_list.item(i)
                    if item.data(Qt.ItemDataRole.UserRole) == self._current_task.id:
                        self._task_list.blockSignals(True)
                        self._task_list.setCurrentRow(i)
                        self._task_list.blockSignals(False)
                        break

        # 回车确认 + 焦点丢失确认 + Escape 取消
        line_edit._on_finish = finish_edit  # type: ignore
        line_edit.returnPressed.connect(finish_edit)

    def _enter_inline_name_edit(self, task_id: int):
        """自动进入指定任务的行内编辑（新建任务时使用）"""
        for i in range(self._task_list.count()):
            item = self._task_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == task_id:
                widget = self._task_list.itemWidget(item)
                if widget:
                    label = widget.findChild(QLabel)
                    layout = widget.findChild(QHBoxLayout) if widget.findChild(QHBoxLayout) else widget.layout()
                    if label and layout:
                        # 用 QTimer 延迟，确保列表渲染完成
                        QTimer.singleShot(0, lambda: self._start_inline_name_edit(None, task_id, label, layout))
                break

    # ============ 任务操作 ============

    def _on_task_selected(self, row: int):
        """任务列表选中"""
        if row < 0:
            self._current_task = None
            self._steps.clear()
            self._task_name_input.clear()
            self._task_desc_input.clear()
            self._refresh_canvas()
            self._set_step_buttons_enabled(False)
            return

        item = self._task_list.item(row)
        task_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            task = self._task_service.get_task(task_id)
            self._current_task = task
            self._task_name_input.setText(task.name)
            self._task_desc_input.setText(task.description or "")
            self._steps = [s.to_dict() for s in task.steps]
            self._refresh_canvas()
            self._set_step_buttons_enabled(True)
            self.task_selected.emit(task)
        except ServiceError as e:
            QMessageBox.warning(self, "加载任务失败", e.message)

    def _on_new_task(self):
        """新建任务：立即在数据库创建，列表中进入行内编辑"""
        try:
            default_name = self._task_service._generate_unique_name()
            task_info = {"name": default_name, "description": "", "steps": []}
            task = self._task_service.create_task(task_info)
            self._current_task = task
            self._task_name_input.setText(default_name)
            self._task_desc_input.clear()
            self._steps.clear()
            self._refresh_canvas()
            self.refresh_tasks()
            # 选中新建的任务
            for i in range(self._task_list.count()):
                item = self._task_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == task.id:
                    self._task_list.setCurrentRow(i)
                    break
            self._set_step_buttons_enabled(True)
            # 自动进入行内编辑
            QTimer.singleShot(0, lambda: self._enter_inline_name_edit(task.id))
            if self._app_signals:
                self._app_signals.status_message.emit("已创建新任务，请编辑名称和步骤")
        except ServiceError as e:
            QMessageBox.warning(self, "新建失败", e.message)

    def _on_name_editing_finished(self):
        """任务名称输入框失焦或回车时，自动保存名称到数据库"""
        if not self._current_task:
            return
        new_name = self._task_name_input.text().strip()
        if not new_name:
            # 名称为空则恢复原名
            self._task_name_input.setText(self._current_task.name)
            return
        if new_name == self._current_task.name:
            return
        try:
            task = self._task_service.update_task(self._current_task.id, {
                "name": new_name,
                "description": self._current_task.description or "",
                "steps": [dict(s) for s in self._steps],
            })
            self._current_task = task
            current_task_id = task.id
            self.refresh_tasks()
            self._restore_task_selection(current_task_id)
            if self._app_signals:
                self._app_signals.status_message.emit(f"任务名称已更新: {new_name}")
        except ServiceError as e:
            QMessageBox.warning(self, "更新失败", e.message)
            self._task_name_input.setText(self._current_task.name)

    def _on_duplicate_task(self):
        """复制任务"""
        if not self._current_task:
            QMessageBox.information(self, "提示", "请先选中一个任务")
            return
        try:
            new_task = self._task_service.duplicate_task(self._current_task.id)
            self._task_signals.task_saved.emit(new_task.to_dict())
            self.refresh_tasks()
            if self._app_signals:
                self._app_signals.status_message.emit(f"任务已复制: {new_task.name}")
        except ServiceError as e:
            QMessageBox.warning(self, "复制失败", e.message)

    def _on_delete_task(self):
        """删除任务"""
        if not self._current_task:
            QMessageBox.information(self, "提示", "请先选中一个任务")
            return
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除任务 '{self._current_task.name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self._task_service.delete_task(self._current_task.id)
                self._task_signals.task_deleted.emit(self._current_task.id)
                self._current_task = None
                self._steps.clear()
                self._task_name_input.clear()
                self._task_desc_input.clear()
                self.refresh_tasks()
                self._refresh_canvas()
                self._set_step_buttons_enabled(False)
                if self._app_signals:
                    self._app_signals.status_message.emit("任务已删除")
            except ServiceError as e:
                QMessageBox.warning(self, "删除失败", e.message)

    def _show_task_context_menu(self, pos):
        """任务列表右键菜单"""
        item = self._task_list.itemAt(pos)
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background-color: #FFFFFF; border: 1px solid #E0E0E0; color: #333333; }
            QMenu::item:selected { background-color: #E0E0E0; }
        """)

        if item:
            export_action = QAction("📤 导出任务", self)
            export_action.triggered.connect(self._on_export_task)
            menu.addAction(export_action)
        else:
            import_action = QAction("📥 导入任务", self)
            import_action.triggered.connect(self._on_import_task)
            menu.addAction(import_action)

        menu.exec(self._task_list.mapToGlobal(pos))

    def _on_import_task(self):
        """从 JSON 文件导入任务"""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入任务", "",
            "JSON 文件 (*.json)",
        )
        if not path:
            return

        try:
            # 读取 JSON 文件
            with open(path, "r", encoding="utf-8") as f:
                task_data = json.load(f)

            # 校验导入数据格式
            if not isinstance(task_data, dict):
                QMessageBox.warning(self, "导入失败", "JSON 文件格式错误：根元素必须是对象")
                return

            # 生成不重复的任务名称（避免与现有任务重名）
            # 使用 "导入" 后缀，如原名为 "MyTask" → "MyTask 导入"
            base_name = task_data.get("name", "导入的任务")
            new_name = self._task_service._generate_unique_name(base_name, suffix="导入")
            task_data["name"] = new_name

            # 调用 service 导入（含校验）
            task = self._task_service.import_task(task_data)

            # 刷新任务列表并选中新导入的任务
            self.refresh_tasks()
            if task:
                for i in range(self._task_list.count()):
                    item = self._task_list.item(i)
                    if item.data(Qt.ItemDataRole.UserRole) == task.id:
                        self._task_list.setCurrentRow(i)
                        break

            QMessageBox.information(self, "导入成功", f"任务 '{task.name}' 已成功导入")
            if self._app_signals:
                self._app_signals.status_message.emit(f"任务已导入: {task.name}")

        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "导入失败", f"JSON 格式错误:\n{e}")
        except ServiceError as e:
            QMessageBox.warning(self, "校验失败", e.message)
        except Exception as e:
            QMessageBox.warning(self, "导入失败", f"导入过程中发生错误:\n{e}")

    def _on_export_task(self):
        """导出当前选中任务为 JSON 文件"""
        if not self._current_task:
            QMessageBox.information(self, "提示", "请先选中一个任务")
            return

        # 默认文件名：任务名.json
        default_name = f"{self._current_task.name}.json"
        # 替换文件名中的非法字符
        for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
            default_name = default_name.replace(ch, '_')

        path, _ = QFileDialog.getSaveFileName(
            self, "导出任务", default_name,
            "JSON 文件 (*.json)",
        )
        if not path:
            return

        try:
            task_data = self._task_service.export_task(self._current_task.id)

            # 写入 JSON 文件（中文可读，缩进 2 空格）
            with open(path, "w", encoding="utf-8") as f:
                json.dump(task_data, f, ensure_ascii=False, indent=2)

            QMessageBox.information(self, "导出成功", f"任务 '{self._current_task.name}' 已导出到:\n{path}")
            if self._app_signals:
                self._app_signals.status_message.emit(f"任务已导出: {path}")

        except ServiceError as e:
            QMessageBox.warning(self, "导出失败", e.message)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", f"导出过程中发生错误:\n{e}")

    # ============ 步骤操作 ============

    def _add_step(self, step_type: str):
        """添加新步骤（通过弹窗）"""
        default_name = {
            "ssh_command": "新命令步骤",
            "sftp_upload": "新上传步骤",
            "sftp_download": "新下载步骤",
        }
        step = {
            "id": None,
            "task_id": None,
            "order_index": len(self._steps),
            "step_type": step_type,
            "name": default_name.get(step_type, "新步骤"),
            "command": "",
            "timeout": DEFAULT_SSH_TIMEOUT,
            "workdir": DEFAULT_WORKDIR,
            "local_path": "",
            "remote_path": "",
            "continue_on_error": False,
            "target_host_ids": [],
        }

        dlg = StepEditDialog(self, step_data=step, available_hosts=self._available_hosts)
        if dlg.exec() == StepEditDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                step.update(result)
                step["order_index"] = len(self._steps)
                # 自动校验步骤内容
                errors = self._validate_steps(show_dialog=True)
                if errors:
                    return
                self._steps.append(step)
                self._refresh_canvas()
                self._on_save_task()
                if self._app_signals:
                    self._app_signals.status_message.emit(f"已添加步骤: {step['name']}")

    def _remove_step(self, index: int):
        """删除步骤"""
        if 0 <= index < len(self._steps):
            removed = self._steps.pop(index)
            self._refresh_canvas()
            self._on_save_task()
            if self._app_signals:
                self._app_signals.status_message.emit(f"已删除步骤: {removed.get('name', '')}")

    def _move_step_up(self, index: int):
        """上移步骤"""
        if index > 0:
            self._steps[index], self._steps[index - 1] = self._steps[index - 1], self._steps[index]
            self._refresh_canvas()
            self._on_save_task()

    def _move_step_down(self, index: int):
        """下移步骤"""
        if index < len(self._steps) - 1:
            self._steps[index], self._steps[index + 1] = self._steps[index + 1], self._steps[index]
            self._refresh_canvas()
            self._on_save_task()

    def _edit_step(self, index: int):
        """编辑步骤（通过弹窗）"""
        if 0 <= index < len(self._steps):
            step = self._steps[index]
            # 备份原始数据，校验失败时恢复
            original_step = dict(step)
            dlg = StepEditDialog(self, step_data=step, available_hosts=self._available_hosts)
            if dlg.exec() == StepEditDialog.DialogCode.Accepted:
                result = dlg.get_result()
                if result:
                    self._steps[index].update(result)
                    # 自动校验步骤内容
                    errors = self._validate_steps(show_dialog=True)
                    if errors:
                        self._steps[index].update(original_step)
                        self._refresh_canvas()
                        return
                    self._refresh_canvas()
                    self._on_save_task()
                    if self._app_signals:
                        self._app_signals.status_message.emit(f"已更新步骤: {result.get('name', '')}")

    def _copy_step(self, index: int):
        """复制步骤（在原步骤下方插入一份副本）"""
        if 0 <= index < len(self._steps):
            original = dict(self._steps[index])
            new_step = {
                **original,
                "id": None,
                "order_index": index + 1,
                "name": f"{original['name']} (副本)",
            }
            self._steps.insert(index + 1, new_step)
            self._refresh_canvas()
            self._on_save_task()
            if self._app_signals:
                self._app_signals.status_message.emit(f"已复制步骤: {original.get('name', '')}")

    def _save_step_as_template(self, index: int):
        """保存步骤为模板"""
        if 0 <= index < len(self._steps):
            step = self._steps[index]
            step_name = step.get("name", "")
            default_tpl_name = f"{step_name} 模板"

            tpl_name, ok = QInputDialog.getText(
                self, "保存为模板", "模板名称:",
                text=default_tpl_name,
            )
            if ok and tpl_name.strip():
                try:
                    result = self._template_service.save_template(step, tpl_name.strip())
                    saved_name = result.get("name", tpl_name.strip()) if result else tpl_name.strip()
                    if self._app_signals:
                        self._app_signals.status_message.emit(f"已保存模板: {saved_name}")
                except ServiceError as e:
                    QMessageBox.warning(self, "保存失败", e.message)
                except Exception as e:
                    QMessageBox.warning(self, "保存失败", f"保存模板时发生错误: {e}")

    def _on_add_from_template(self):
        """从模板添加步骤"""
        dlg = StepTemplateDialog(self, mode="select")
        if dlg.exec() == StepTemplateDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                result["order_index"] = len(self._steps)
                self._steps.append(result)
                self._refresh_canvas()
                if self._app_signals:
                    self._app_signals.status_message.emit(f"已从模板添加步骤: {result.get('name', '')}")

    def _on_manage_templates(self):
        """打开模板管理弹窗"""
        dlg = StepTemplateDialog(self, mode="manage")
        dlg.exec()

    def _refresh_canvas(self):
        """刷新步骤画布"""
        # 立即清除旧组件（避免 deleteLater 延迟导致残留）
        while self._canvas_layout.count() > 0:
            item = self._canvas_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        # 添加步骤卡片
        for idx, step in enumerate(self._steps):
            card = StepCard(idx, step, self)
            card.remove_requested.connect(self._remove_step)
            card.move_up_requested.connect(self._move_step_up)
            card.move_down_requested.connect(self._move_step_down)
            card.edit_requested.connect(self._edit_step)
            card.copy_requested.connect(self._copy_step)
            card.save_template_requested.connect(self._save_step_as_template)
            self._canvas_layout.addWidget(card)

        self._canvas_layout.addStretch()

    def eventFilter(self, obj, event):
        """事件过滤器：处理任务列表空白取消选中和自定义 tooltip"""
        if event.type() == QEvent.ToolTip:
            tooltip_text = ""
            if obj is self._task_list.viewport():
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                item = self._task_list.itemAt(pos)
                if item is not None:
                    tooltip_text = item.toolTip()
            if not tooltip_text and isinstance(obj, QWidget) and self.isAncestorOf(obj):
                tooltip_text = obj.toolTip()
            if tooltip_text:
                self._show_global_tooltip(obj, tooltip_text, event)
                return True
            self._global_tooltip.hide()
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Leave and isinstance(obj, QWidget) and self.isAncestorOf(obj):
            self._global_tooltip.hide()
            return super().eventFilter(obj, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            task_viewport = self._task_list.viewport()
            if obj is task_viewport:
                pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                item = self._task_list.itemAt(pos)
                if item is None:
                    self._task_list.clearSelection()
                    self._task_list.setCurrentRow(-1)
                return False

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

    # ============ 事件处理 ============

    def _validate_steps(self, show_dialog: bool = False) -> list[str]:
        """
        校验所有步骤的完整性和合法性。

        Args:
            show_dialog: 是否在校验失败时弹出对话框

        Returns:
            错误信息列表，空列表表示校验通过
        """
        errors = []

        # 步骤名称不可重复（跳过空名的）
        names = [s.get("name") for s in self._steps if s.get("name")]
        seen = {}
        for n in names:
            seen[n] = seen.get(n, 0) + 1
        for n, count in seen.items():
            if count > 1:
                errors.append(f"步骤名称重复: '{n}' 出现了 {count} 次")

        for idx, step in enumerate(self._steps):
            name = step.get("name") or f"步骤 {idx + 1}"

            # 名称非空
            if not step.get("name"):
                errors.append(f"步骤 {idx + 1}: 名称不能为空")

            # 命令步骤
            if step["step_type"] == "ssh_command":
                cmd = step.get("command", "").strip()
                if not cmd:
                    errors.append(f"'{name}': 命令不能为空")

            # SFTP 上传/下载步骤
            if step["step_type"] in ("sftp_upload", "sftp_download"):
                local = step.get("local_path", "").strip()
                remote = step.get("remote_path", "").strip()

                if not local:
                    errors.append(f"'{name}': 本地路径不能为空")
                elif step["step_type"] == "sftp_upload" and not os.path.exists(local):
                    errors.append(f"'{name}': 本地路径不存在: {local}")

                if not remote:
                    errors.append(f"'{name}': 远程路径不能为空")

        if show_dialog and errors:
            QMessageBox.warning(self, "校验失败", "以下问题需要修复:\n\n" + "\n".join(errors))
        return errors

    def _on_save_task(self) -> Task | None:
        """保存任务，返回保存后的 Task 对象（含 steps），失败返回 None"""
        name = self._task_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "保存失败", "任务名称不能为空")
            return None

        if self._validate_steps(show_dialog=True):
            return None

        task_info = {
            "name": name,
            "description": self._task_desc_input.text().strip(),
            "steps": [dict(s) for s in self._steps],
        }

        try:
            if self._current_task:
                task = self._task_service.update_task(self._current_task.id, task_info)
            else:
                task = self._task_service.create_task(task_info)
                self._current_task = task

            self._task_signals.task_saved.emit(task.to_dict())
            # 保存当前任务 ID，refresh 后恢复选中状态
            current_task_id = self._current_task.id if self._current_task else None
            self.refresh_tasks()
            if current_task_id:
                self._restore_task_selection(current_task_id)
            if self._app_signals:
                self._app_signals.status_message.emit(f"任务 '{task.name}' 已保存")
            return task
        except ServiceError as e:
            QMessageBox.warning(self, "保存失败", e.message)
            return None

    def _on_execute(self):
        """执行任务"""
        # 先保存当前面板选中的主机 ID（保存任务后 refresh_tasks 会重置选中状态）
        pre_selected_ids = set(self._get_selected_host_ids())

        # 先尝试保存
        task = self._on_save_task()
        if not task:
            QMessageBox.warning(self, "执行失败", "请先保存任务")
            return

        # 恢复之前的主机选中状态
        self._restore_host_selection(pre_selected_ids)

        # 使用面板选中的主机
        selected_host_ids = self._get_selected_host_ids()
        if not selected_host_ids:
            QMessageBox.warning(self, "执行失败", "没有可执行的目标主机")
            return

        # 直接使用保存后返回的 task 对象（已含 steps），避免再次查询
        self._current_task = task
        self.task_selected.emit(task)
        self.execute_task_requested.emit(task, selected_host_ids)

    def _on_execute_from_list(self, task_id: int, row: int):
        """从任务列表的执行按钮触发执行"""
        # 先选中该任务（加载步骤到画布）
        self._task_list.setCurrentRow(row)
        if not self._current_task or self._current_task.id != task_id:
            return
        # 复用执行逻辑
        self._on_execute()

    def _on_copy_from_list(self, task_id: int, row: int):
        """从任务列表的复制按钮触发复制"""
        self._task_list.setCurrentRow(row)
        if self._current_task and self._current_task.id == task_id:
            self._on_duplicate_task()

    def _on_delete_from_list(self, task_id: int, row: int):
        """从任务列表的删除按钮触发删除"""
        self._task_list.setCurrentRow(row)
        if self._current_task and self._current_task.id == task_id:
            self._on_delete_task()

    # ============ 样式工具 ============

    @staticmethod
    def _make_small_btn(text: str, callback) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(30)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(callback)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #E0E0E0;
                color: #333333;
                border: 1px solid #D0D0D0;
                padding: 4px 12px;
                border-radius: 4px;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #D0D0D0; }
        """)
        return btn

    @staticmethod
    def _make_action_btn(text: str, callback) -> QPushButton:
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
            QPushButton:hover { background-color: #D0D0D0; border-color: #1976D2; }
        """)
        return btn
