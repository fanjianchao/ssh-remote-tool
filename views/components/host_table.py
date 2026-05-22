from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机表格组件

支持多选、搜索过滤、右键菜单、状态指示灯、行内编辑。
"""

from typing import List, Optional, Callable

from PySide6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu,
    QAbstractItemView, QLineEdit, QHBoxLayout, QVBoxLayout, QWidget, QLabel,
    QComboBox, QPushButton, QMessageBox, QFileDialog, QStyledItemDelegate, QStyle,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QAction, QFont, QKeyEvent

from config.constants import COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING, COLOR_PENDING


# 主机状态 → 颜色映射
STATUS_COLORS = {
    "unknown": COLOR_PENDING,
    "connected": COLOR_SUCCESS,
    "disconnected": COLOR_ERROR,
    "error": COLOR_ERROR,
    "testing": COLOR_WARNING,
}

# 列定义
HOST_COLUMNS = [
    ("状态", 40),            # 0: 状态图标（悬浮显示文字）
    ("主机名", 150),         # 1: name
    ("IP:端口", 190),        # 2: host:port（行内编辑时拆分为 IP + 端口）
    ("用户名", 100),         # 3: username
    ("认证方式", 230),       # 4: auth_type（行内编辑：密码/密钥输入 + 认证切换）
    ("分组", 100),           # 5: group_name
    ("备注", 130),           # 6: remark
    ("操作", 130),           # 7: 操作按钮列（行内编辑时改为保存/取消）
]

# 支持行内直接编辑的列（col_index → host_dict key）
INLINE_EDITABLE_COLS = {
    1: "name",
    3: "username",
    5: "group",
    6: "remark",
}


class NoFocusDelegate(QStyledItemDelegate):
    """去掉单元格获得焦点时的虚线框"""

    def paint(self, painter, option, index):
        # 清除 State_HasFocus，阻止 Qt 绘制焦点虚线框
        opt = option
        opt.state &= ~QStyle.StateFlag.State_HasFocus
        super().paint(painter, opt, index)


class HostTable(QWidget):
    """主机表格组件"""

    # 信号
    edit_requested = Signal(int)                     # host_id → 弹窗编辑（密码/密钥等）
    delete_requested = Signal(int)                   # host_id
    test_requested = Signal(int)                     # host_id
    selection_changed = Signal(list)                 # 选中的 host_id 列表
    batch_delete_requested = Signal(list)            # host_id 列表
    connect_status_changed = Signal(int, str)        # host_id, status
    inline_save_requested = Signal(int, dict)        # host_id, 变更字典 → 由 View 层持久化

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_data: list[dict] = []  # 缓存主机数据
        self._status_map: dict[int, str] = {}  # host_id → 连接状态
        self._group_count: int = 0  # 分组数量
        self._ops_btns: dict[int, tuple[QPushButton, QPushButton]] = {}  # host_id → (编辑btn, 测试btn)
        # 行内编辑状态：row → {col: QLineEdit, ...}
        self._editing_row: int | None = None
        self._editing_widgets: dict[int, object] = {}  # col → QLineEdit / QComboBox
        # IP/端口行内编辑组件（第3列特殊处理，拆成 ip + port）
        self._editing_ip: QLineEdit | None = None
        self._editing_port: QLineEdit | None = None
        # 认证行内编辑组件（第5列）
        self._editing_pw: QLineEdit | None = None
        self._editing_key: QLineEdit | None = None
        self._auth_type_combo: QComboBox | None = None
        # 编辑 widget Tab 顺序列表（按编辑流程排列）
        self._edit_tab_order: list[str] = [
            "name", "ip", "port", "username", "auth_input", "group", "remark",
        ]

        self._setup_ui()
        self._connect_signals()
        # 给表格安装事件过滤器，处理 Esc 键取消编辑
        self._table.installEventFilter(self)

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # --- 搜索过滤栏 ---
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(12)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 搜索主机名 / IP / 用户名...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedHeight(32)
        self._search_input.textChanged.connect(self._apply_filter)
        filter_bar.addWidget(self._search_input)

        self._group_filter = QComboBox()
        self._group_filter.setPlaceholderText("全部分组")
        self._group_filter.setFixedWidth(140)
        self._group_filter.setFixedHeight(32)
        self._group_filter.currentIndexChanged.connect(self._apply_filter)
        filter_bar.addWidget(self._group_filter)

        # 全选 / 反选按钮
        select_btn_style = """
            QPushButton {
                background-color: #F5F5F5;
                color: #555555;
                border: 1px solid #E0E0E0;
                border-radius: 3px;
                padding: 4px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #E0E0E0;
                border-color: #BDBDBD;
            }
        """
        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.setFixedHeight(32)
        self._btn_select_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_select_all.setStyleSheet(select_btn_style)
        self._btn_select_all.clicked.connect(self._on_select_all)
        filter_bar.addWidget(self._btn_select_all)

        self._btn_invert_selection = QPushButton("反选")
        self._btn_invert_selection.setFixedHeight(32)
        self._btn_invert_selection.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_invert_selection.setStyleSheet(select_btn_style)
        self._btn_invert_selection.clicked.connect(self._on_invert_selection)
        filter_bar.addWidget(self._btn_invert_selection)

        filter_bar.addStretch()

        self._count_label = QLabel("共 0 台主机")
        self._count_label.setStyleSheet("color: #666666; font-size: 12px;")
        filter_bar.addWidget(self._count_label)

        layout.addLayout(filter_bar)

        # --- 表格 ---
        self._table = QTableWidget()
        self._table.setColumnCount(len(HOST_COLUMNS))
        self._table.setHorizontalHeaderLabels([col[0] for col in HOST_COLUMNS])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.setSortingEnabled(False)
        self._table.setItemDelegate(NoFocusDelegate())

        # 设置列宽
        header = self._table.horizontalHeader()
        for idx, (_, width) in enumerate(HOST_COLUMNS):
            header.setSectionResizeMode(idx, QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(idx, width)
        # 最后一列自适应填满剩余空间
        header.setStretchLastSection(True)

        # 选择变化信号
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        # 双击单元格 → 行内编辑
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        layout.addWidget(self._table)

        # 表格样式
        self._table.setStyleSheet("""
            QTableWidget {
                background-color: #FFFFFF;
                alternate-background-color: #F5F5F5;
                gridline-color: #E0E0E0;
                border: none;
                font-size: 13px;
                color: #333333;
                outline: none;
            }
            QTableWidget::item:focus {
                outline: none;
                border: none;
            }
            QTableWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #E0E0E0;
                color: #333333;
                outline: none;
            }
            QTableWidget::item:selected {
                background-color: #E8F5E9;
                color: #1B5E20;
                outline: none;
            }
            QTableWidget::item:selected:hover {
                background-color: #C8E6C9;
                color: #1B5E20;
                outline: none;
            }
            QTableWidget::item:hover {
                background-color: #F0F4FF;
                color: #333333;
                outline: none;
            }
            QHeaderView::section {
                background-color: #F5F5F5;
                color: #666666;
                padding: 8px;
                border: none;
                border-bottom: 2px solid #E0E0E0;
                font-weight: bold;
                font-size: 12px;
            }
        """)

    def _connect_signals(self):
        """连接内部信号"""
        pass

    # ============ 公共方法 ============

    def load_data(self, hosts: list, groups: list[str] | None = None):
        """
        加载主机数据到表格。

        Args:
            hosts: Host ORM 对象列表
            groups: 可选的分组列表（用于筛选下拉框）
        """
        # 重置行内编辑状态（防止旧行号残留）
        self._editing_row = None
        self._editing_widgets.clear()
        self._editing_ip = None
        self._editing_port = None
        self._editing_pw = None
        self._editing_key = None
        self._auth_type_combo = None

        self._host_data = []
        for h in hosts:
            d = h.to_dict() if hasattr(h, "to_dict") else h
            self._host_data.append(d)

        # 更新分组筛选
        if groups is not None:
            self._group_count = len(groups) if groups else 0
            self._group_filter.blockSignals(True)
            current = self._group_filter.currentText()
            self._group_filter.clear()
            self._group_filter.addItem("全部分组")
            for g in sorted(groups):
                self._group_filter.addItem(g)
            # 恢复之前的选择
            idx = self._group_filter.findText(current)
            if idx >= 0:
                self._group_filter.setCurrentIndex(idx)
            else:
                self._group_filter.setCurrentIndex(0)
            self._group_filter.blockSignals(False)

        self._apply_filter()

    def get_selected_host_ids(self) -> list[int]:
        """获取选中的主机 ID 列表（通过 selectionModel 读取行号，再从 UserRole 取 host_id）"""
        ids = []
        selected_rows = set()
        for idx in self._table.selectionModel().selectedRows():
            selected_rows.add(idx.row())
        # 若 selectedRows 为空则退化到 selectedItems（兼容老选择方式）
        if not selected_rows:
            for item in self._table.selectedItems():
                selected_rows.add(item.row())
        for row in sorted(selected_rows):
            hid = self._get_host_id_from_row(row)
            if hid is not None:
                ids.append(hid)
        return ids

    def set_connection_status(self, host_id: int, status: str):
        """更新主机的连接状态指示灯"""
        self._status_map[host_id] = status
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.data(Qt.ItemDataRole.UserRole) == host_id:
                self._update_status_indicator(row, status)
                break

    def update_row(self, host_dict: dict):
        """更新单行数据"""
        host_id = host_dict["id"]
        for i, d in enumerate(self._host_data):
            if d["id"] == host_id:
                self._host_data[i] = host_dict
                break
        self._apply_filter()

    def remove_rows(self, host_ids: list[int]):
        """移除指定行"""
        id_set = set(host_ids)
        self._host_data = [d for d in self._host_data if d["id"] not in id_set]
        self._apply_filter()

    # ============ 内部方法 ============

    def _apply_filter(self):
        """应用搜索和分组过滤"""
        keyword = self._search_input.text().strip().lower()
        group = self._group_filter.currentText()

        filtered = self._host_data

        # 分组过滤
        if group and group != "全部分组":
            filtered = [d for d in filtered if d.get("group") == group]

        # 关键词过滤
        if keyword:
            filtered = [d for d in filtered if
                        keyword in d.get("name", "").lower()
                        or keyword in d.get("host", "").lower()
                        or keyword in d.get("username", "").lower()
                        or keyword in d.get("group", "").lower()]

        self._refresh_table(filtered)

    def _refresh_table(self, data: list[dict]):
        """刷新表格内容"""
        self._table.setRowCount(len(data))
        self._ops_btns.clear()  # 清理旧的按钮引用
        self._count_label.setText(f"共 {len(data)} 台主机，{self._group_count} 个分组")

        # 设置行高，确保按钮完整显示
        row_height = 40
        for row in range(len(data)):
            self._table.setRowHeight(row, row_height)

        for row, host in enumerate(data):
            host_id = host.get("id", 0)
            status = self._status_map.get(host_id, "unknown")

            # 0: 状态图标（用 QLabel widget，避免选中时系统高亮覆盖颜色）
            # 用 QTableWidgetItem 存储 host_id（UserRole），label 仅负责显示
            status_item = QTableWidgetItem()
            status_item.setData(Qt.ItemDataRole.UserRole, host_id)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, status_item)
            self._update_status_indicator(row, status)

            # 1: 主机名（默认为 IP）
            name = host.get("name", "") or host.get("host", "")
            name_item = QTableWidgetItem(name)
            self._table.setItem(row, 1, name_item)

            # 2: IP:端口
            addr = f"{host.get('host', '')}:{host.get('port', 22)}"
            addr_item = QTableWidgetItem(addr)
            font = QFont("Consolas", 12)
            addr_item.setFont(font)
            self._table.setItem(row, 2, addr_item)

            # 3: 用户名
            self._table.setItem(row, 3, QTableWidgetItem(host.get("username", "")))

            # 4: 认证方式
            auth_map = {"password": "密码", "key": "密钥"}
            auth_text = auth_map.get(host.get("auth_type", ""), host.get("auth_type", ""))
            self._table.setItem(row, 4, QTableWidgetItem(auth_text))

            # 5: 分组
            self._table.setItem(row, 5, QTableWidgetItem(host.get("group", "")))

            # 6: 备注
            self._table.setItem(row, 6, QTableWidgetItem(host.get("remark", "")))

            # 7: 操作按钮（嵌入真实 QPushButton）
            ops_widget = QWidget()
            ops_layout = QHBoxLayout(ops_widget)
            ops_layout.setContentsMargins(4, 2, 4, 2)
            ops_layout.setSpacing(6)

            btn_edit = QPushButton("编辑")
            btn_edit.setFixedHeight(26)
            btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_edit.setStyleSheet("""
                QPushButton {
                    background-color: #D0D0D0;
                    color: #333333;
                    border: 1px solid #BDBDBD;
                    border-radius: 3px;
                    padding: 0px 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #BDBDBD;
                    border-color: #1976D2;
                }
            """)
            btn_edit.clicked.connect(lambda checked, h=host_id: self.edit_requested.emit(h))

            btn_test = QPushButton("测试")
            btn_test.setFixedHeight(26)
            btn_test.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_test.setStyleSheet("""
                QPushButton {
                    background-color: #D0D0D0;
                    color: #333333;
                    border: 1px solid #BDBDBD;
                    border-radius: 3px;
                    padding: 0px 4px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #BDBDBD;
                    border-color: #1976D2;
                }
            """)
            btn_test.clicked.connect(lambda checked, h=host_id: self.test_requested.emit(h))

            ops_layout.addWidget(btn_edit)
            ops_layout.addWidget(btn_test)
            self._table.setCellWidget(row, 7, ops_widget)
            self._ops_btns[host_id] = (btn_edit, btn_test)

    def _get_host_id_from_row(self, row: int) -> int | None:
        """从指定行获取 host_id（从第0列 UserRole 数据读取，兼容过滤后行号）"""
        item = self._table.item(row, 0)
        if item is None:
            return None
        hid = item.data(Qt.ItemDataRole.UserRole)
        return hid if hid is not None else None

    def _update_status_indicator(self, row: int, status: str, item: QTableWidgetItem | None = None):
        """更新状态图标（◆ QLabel widget），颜色不受行选中 QSS 影响"""
        # 悬浮提示中文状态
        status_tooltip_map = {
            "unknown": "状态：未知",
            "connected": "状态：已连接",
            "disconnected": "状态：未连接",
            "error": "状态：连接失败",
            "testing": "状态：测试中...",
        }

        # 状态颜色
        color_map = {
            "unknown": "#9E9E9E",
            "connected": "#43A047",
            "disconnected": "#E53935",
            "error": "#E53935",
            "testing": "#F9A825",
        }
        dot_color = color_map.get(status, "#9E9E9E")
        tooltip = status_tooltip_map.get(status, "状态：未知")

        # 用 QLabel widget 显示 ●，避免 item:selected QSS 覆盖前景色
        existing = self._table.cellWidget(row, 0)
        if isinstance(existing, QLabel):
            # 复用已有 label，直接更新颜色和 tooltip
            label = existing
        else:
            label = QLabel("●")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFont(QFont("Segoe UI Symbol", 18))
            label.setMinimumSize(36, 36)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self._table.setCellWidget(row, 0, label)

        label.setStyleSheet(
            f"color: {dot_color}; background: transparent; font-size: 18px;"
        )
        label.setToolTip(tooltip)

    def _on_selection_changed(self):
        """选择变化事件"""
        ids = self.get_selected_host_ids()
        self.selection_changed.emit(ids)

    def _on_select_all(self):
        """全选当前过滤后的所有行"""
        self._table.selectAll()

    def _on_invert_selection(self):
        """反选：选中当前未选中的行，取消已选中的行"""
        total_rows = self._table.rowCount()
        selected_rows = set()
        for item in self._table.selectedItems():
            selected_rows.add(item.row())

        self._table.blockSignals(True)  # 暂时屏蔽信号，避免频繁触发
        self._table.clearSelection()
        for row in range(total_rows):
            if row not in selected_rows:
                self._table.selectRow(row)
        self._table.blockSignals(False)
        # 手动触发一次选择变化信号
        self._on_selection_changed()

    def _on_cell_double_clicked(self, row: int, col: int):
        """双击单元格 → 进入行内编辑模式（状态图标/操作列除外）"""
        if col in (0, 7):
            # 状态图标、操作列 → 不行内编辑
            return
        host_id = self._get_host_id_from_row(row)
        if host_id is None:
            return
        self._start_inline_edit(row, host_id)

    def _start_inline_edit(self, row: int, host_id: int):
        """进入行内编辑模式"""
        # 若已有其他行处于编辑中，先取消
        if self._editing_row is not None and self._editing_row != row:
            self._cancel_inline_edit()

        if self._editing_row == row:
            return  # 已在编辑中

        self._editing_row = row
        self._editing_widgets.clear()
        self._editing_ip = None
        self._editing_port = None

        # 找到该主机数据
        host = self._get_host_data_by_id(host_id)
        if host is None:
            return

        edit_style = """
            QLineEdit {
                background-color: #FFF9C4;
                color: #333333;
                border: 1px solid #F9A825;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1.5px solid #F57F17;
            }
        """

        # 为可编辑列嵌入 QLineEdit
        for col, key in INLINE_EDITABLE_COLS.items():
            le = QLineEdit(str(host.get(key, "")))
            le.setStyleSheet(edit_style)
            le.setFixedHeight(28)
            le.returnPressed.connect(self._on_inline_return_pressed)
            self._table.setCellWidget(row, col, le)
            self._editing_widgets[col] = le

        # 第3列 IP:端口 → 拆成两个 QLineEdit
        ip_port_widget = QWidget()
        ip_port_layout = QHBoxLayout(ip_port_widget)
        ip_port_layout.setContentsMargins(2, 2, 2, 2)
        ip_port_layout.setSpacing(4)

        ip_le = QLineEdit(host.get("host", ""))
        ip_le.setStyleSheet(edit_style)
        ip_le.setFixedHeight(28)
        ip_le.setPlaceholderText("IP/域名")
        ip_le.returnPressed.connect(self._on_inline_return_pressed)

        port_le = QLineEdit(str(host.get("port", 22)))
        port_le.setStyleSheet(edit_style)
        port_le.setFixedWidth(52)
        port_le.setFixedHeight(28)
        port_le.setPlaceholderText("端口")
        port_le.returnPressed.connect(self._on_inline_return_pressed)

        ip_port_layout.addWidget(ip_le, stretch=1)
        ip_port_layout.addWidget(port_le)
        self._table.setCellWidget(row, 2, ip_port_widget)
        self._editing_ip = ip_le
        self._editing_port = port_le

        # 第4列（认证方式）：密码认证 → 密码输入框，密钥认证 → 密钥路径输入框
        auth_type = host.get("auth_type", "password")
        auth_widget = QWidget()
        auth_layout = QHBoxLayout(auth_widget)
        auth_layout.setContentsMargins(2, 2, 2, 2)
        auth_layout.setSpacing(4)

        self._auth_type_combo = QComboBox()
        self._auth_type_combo.setFixedHeight(28)
        self._auth_type_combo.setFixedWidth(70)
        self._auth_type_combo.addItem("密码", "password")
        self._auth_type_combo.addItem("密钥", "key")
        idx = 0 if auth_type == "password" else 1
        self._auth_type_combo.setCurrentIndex(idx)
        self._editing_widgets[4] = self._auth_type_combo  # 复用 dict 存引用

        if auth_type == "password":
            self._editing_pw = QLineEdit()
            self._editing_pw.setStyleSheet(edit_style)
            self._editing_pw.setFixedHeight(28)
            self._editing_pw.setEchoMode(QLineEdit.EchoMode.Password)
            self._editing_pw.setPlaceholderText("留空保持不变")
            self._editing_pw.returnPressed.connect(self._on_inline_return_pressed)
            auth_layout.addWidget(self._editing_pw, stretch=1)

            toggle_btn = QPushButton("👁")
            toggle_btn.setFixedSize(24, 28)
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; } QPushButton:hover { background: #E0E0E0; }")
            toggle_btn.clicked.connect(self._toggle_inline_password)
            auth_layout.addWidget(toggle_btn)
            self._editing_key = None
        else:
            self._editing_pw = None
            self._editing_key = QLineEdit()
            self._editing_key.setStyleSheet(edit_style)
            self._editing_key.setFixedHeight(28)
            self._editing_key.setPlaceholderText("密钥路径")
            self._editing_key.returnPressed.connect(self._on_inline_return_pressed)
            auth_layout.addWidget(self._editing_key, stretch=1)

            browse_btn = QPushButton("📂")
            browse_btn.setFixedSize(28, 28)
            browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            browse_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; } QPushButton:hover { background: #E0E0E0; }")
            browse_btn.clicked.connect(self._browse_inline_key)
            auth_layout.addWidget(browse_btn)

        self._auth_type_combo.currentIndexChanged.connect(self._on_inline_auth_type_changed)
        auth_layout.addWidget(self._auth_type_combo)
        self._table.setCellWidget(row, 4, auth_widget)
        ops_widget = QWidget()
        ops_layout = QHBoxLayout(ops_widget)
        ops_layout.setContentsMargins(4, 2, 4, 2)
        ops_layout.setSpacing(6)

        btn_save = QPushButton("✅ 保存")
        btn_save.setFixedHeight(26)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.setStyleSheet("""
            QPushButton {
                background-color: #C8E6C9;
                color: #1B5E20;
                border: 1px solid #A5D6A7;
                border-radius: 3px;
                padding: 0px 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #A5D6A7;
                border-color: #388E3C;
            }
        """)
        btn_save.clicked.connect(lambda checked: self._commit_inline_edit())

        btn_cancel = QPushButton("❌ 取消")
        btn_cancel.setFixedHeight(26)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #FFCDD2;
                color: #B71C1C;
                border: 1px solid #EF9A9A;
                border-radius: 3px;
                padding: 0px 4px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #EF9A9A;
                border-color: #C62828;
            }
        """)
        btn_cancel.clicked.connect(self._cancel_inline_edit)

        ops_layout.addWidget(btn_save)
        ops_layout.addWidget(btn_cancel)
        self._table.setCellWidget(row, 7, ops_widget)

        # 为所有编辑 widget 安装事件过滤器（处理 Esc 和失焦保存）
        for key in self._edit_tab_order:
            w = self._get_edit_widget_by_key(key)
            if w:
                w.installEventFilter(self)
        if self._auth_type_combo:
            self._auth_type_combo.installEventFilter(self)

        # 高亮整行背景
        for c in range(self._table.columnCount()):
            item = self._table.item(row, c)
            if item:
                item.setBackground(QColor("#FFFDE7"))

        # 聚焦第一个可编辑字段（主机名）
        name_le = self._editing_widgets.get(1)
        if name_le:
            name_le.setFocus()
            name_le.selectAll()

    def _get_current_edit_row(self) -> int | None:
        """获取当前编辑行号"""
        return self._editing_row

    def _get_current_edit_host_id(self) -> int | None:
        """获取当前编辑的 host_id"""
        if self._editing_row is None:
            return None
        return self._get_host_id_from_row(self._editing_row)

    def _get_edit_widget_by_key(self, key: str) -> QWidget | None:
        """按 Tab 顺序的 key 获取当前编辑中的 widget"""
        if key == "name":
            return self._editing_widgets.get(1)
        elif key == "ip":
            return self._editing_ip
        elif key == "port":
            return self._editing_port
        elif key == "username":
            return self._editing_widgets.get(3)
        elif key == "auth_input":
            return self._editing_pw or self._editing_key
        elif key == "group":
            return self._editing_widgets.get(5)
        elif key == "remark":
            return self._editing_widgets.get(6)
        return None

    def _on_inline_return_pressed(self):
        """编辑框 Enter 键处理：最后一个字段 → 保存，其他字段 → 跳到下一个"""
        # 找到当前焦点所在的 widget 对应的 tab key
        focused = self._table.focusWidget()
        current_key = None
        for key in self._edit_tab_order:
            w = self._get_edit_widget_by_key(key)
            if w is focused:
                current_key = key
                break

        if current_key is None:
            return

        idx = self._edit_tab_order.index(current_key)
        if idx < len(self._edit_tab_order) - 1:
            # 非最后一个字段 → 跳到下一个
            next_key = self._edit_tab_order[idx + 1]
            next_w = self._get_edit_widget_by_key(next_key)
            if next_w:
                next_w.setFocus()
                if isinstance(next_w, QLineEdit):
                    next_w.selectAll()
        else:
            # 最后一个字段 → 保存
            self._commit_inline_edit()

    def _check_focus_after_leave(self):
        """延迟检查焦点是否仍在编辑行内"""
        if self._editing_row is None:
            return  # 已经提交/取消了
        focused = self._table.focusWidget()
        # 检查焦点是否仍在编辑行的某个 widget 上
        for key in self._edit_tab_order:
            w = self._get_edit_widget_by_key(key)
            if w is focused:
                return  # 还在编辑行内，不保存
        # 检查是否在 auth_type_combo 上
        if focused is self._auth_type_combo:
            return
        # 检查是否在操作按钮上（保存/取消按钮不应触发失焦保存）
        if focused and isinstance(focused, QPushButton):
            return
        # 焦点离开了编辑行 → 自动保存
        self._commit_inline_edit()

    def _toggle_inline_password(self):
        """切换行内编辑中密码框的可见性"""
        if self._editing_pw:
            if self._editing_pw.echoMode() == QLineEdit.EchoMode.Password:
                self._editing_pw.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                self._editing_pw.setEchoMode(QLineEdit.EchoMode.Password)

    def _browse_inline_key(self):
        """行内编辑中浏览选择密钥文件"""
        if self._editing_key is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self._table, "选择私钥文件", "",
            "所有文件 (*.*) ;; PEM 文件 (*.pem) ;; 密钥文件 (*.key)",
        )
        if path:
            self._editing_key.setText(path)

    def _on_inline_auth_type_changed(self, index: int):
        """行内编辑中认证方式切换 → 替换密码/密钥输入框"""
        if self._editing_row is None:
            return

        row = self._editing_row
        is_password = (index == 0)

        edit_style = """
            QLineEdit {
                background-color: #FFF9C4;
                color: #333333;
                border: 1px solid #F9A825;
                border-radius: 3px;
                padding: 2px 6px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 1.5px solid #F57F17;
            }
        """

        # 获取当前第4列的 widget，替换其 layout 内容
        auth_widget = self._table.cellWidget(row, 4)
        if auth_widget is None:
            return

        # 清空旧内容（保留 combo，只删除密码/密钥输入框和切换按钮）
        old_layout = auth_widget.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                w = item.widget()
                if w and w is not self._auth_type_combo:
                    w.deleteLater()

        # 重建：输入框 + 认证切换 combo
        if is_password:
            self._editing_pw = QLineEdit()
            self._editing_pw.setStyleSheet(edit_style)
            self._editing_pw.setFixedHeight(28)
            self._editing_pw.setEchoMode(QLineEdit.EchoMode.Password)
            self._editing_pw.setPlaceholderText("留空保持不变")
            self._editing_pw.returnPressed.connect(self._on_inline_return_pressed)
            self._editing_pw.installEventFilter(self)
            old_layout.addWidget(self._editing_pw, stretch=1)

            toggle_btn = QPushButton("👁")
            toggle_btn.setFixedSize(24, 28)
            toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            toggle_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; } QPushButton:hover { background: #E0E0E0; }")
            toggle_btn.clicked.connect(self._toggle_inline_password)
            old_layout.addWidget(toggle_btn)
            self._editing_key = None
        else:
            self._editing_pw = None
            self._editing_key = QLineEdit()
            self._editing_key.setStyleSheet(edit_style)
            self._editing_key.setFixedHeight(28)
            self._editing_key.setPlaceholderText("密钥路径")
            self._editing_key.returnPressed.connect(self._on_inline_return_pressed)
            self._editing_key.installEventFilter(self)
            old_layout.addWidget(self._editing_key, stretch=1)

            browse_btn = QPushButton("📂")
            browse_btn.setFixedSize(28, 28)
            browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            browse_btn.setStyleSheet("QPushButton { border: none; background: transparent; font-size: 14px; } QPushButton:hover { background: #E0E0E0; }")
            browse_btn.clicked.connect(self._browse_inline_key)
            old_layout.addWidget(browse_btn)

        # combo 已保留在旧 layout 中，需重新添加
        old_layout.addWidget(self._auth_type_combo)

    def _commit_inline_edit(self):
        """提交行内编辑，发出 inline_save_requested 信号"""
        if self._editing_row is None:
            return
        row = self._editing_row
        host_id = self._get_host_id_from_row(row)
        if host_id is None:
            self._finish_inline_edit()
            return
        changes: dict = {}

        # 收集普通字段（col 2/4/6/7）
        for col, key in INLINE_EDITABLE_COLS.items():
            le = self._editing_widgets.get(col)
            if le and isinstance(le, QLineEdit):
                changes[key] = le.text().strip()

        # 收集 IP / 端口
        if self._editing_ip and self._editing_port:
            ip = self._editing_ip.text().strip()
            port_str = self._editing_port.text().strip()

            # 字段校验
            errors = []
            if not changes.get("name"):
                errors.append("主机名不能为空")
            if not ip:
                errors.append("IP/域名不能为空")
            if not changes.get("username"):
                errors.append("用户名不能为空")
            try:
                port = int(port_str)
                if not (1 <= port <= 65535):
                    raise ValueError()
            except ValueError:
                errors.append("端口号必须为 1~65535 的整数")
                port = 22

            if errors:
                QMessageBox.warning(self._table, "输入有误", "\n".join(errors))
                return

            changes["host"] = ip
            changes["port"] = port

        # 收集认证信息
        auth_combo = self._editing_widgets.get(4)
        if auth_combo and isinstance(auth_combo, QComboBox):
            auth_type = auth_combo.currentData()
            changes["auth_type"] = auth_type
            if auth_type == "password":
                pw = self._editing_pw.text() if self._editing_pw else ""
                if pw:  # 非空才覆盖，空 = 保持原密码
                    changes["password"] = pw
            else:
                key_path = self._editing_key.text().strip() if self._editing_key else ""
                if key_path:
                    changes["key_path"] = key_path

        self._finish_inline_edit()
        self.inline_save_requested.emit(host_id, changes)

    def _cancel_inline_edit(self):
        """取消行内编辑，恢复原始显示"""
        self._finish_inline_edit()

    def _finish_inline_edit(self):
        """清理行内编辑状态"""
        row = self._editing_row
        self._editing_row = None
        self._editing_widgets.clear()
        self._editing_ip = None
        self._editing_port = None
        self._editing_pw = None
        self._editing_key = None
        self._auth_type_combo = None

        if row is None:
            return

        # 显式移除所有嵌入的 cellWidget
        # Qt 中 setItem 不会自动移除 setCellWidget 嵌入的 widget，必须手动清除
        for col in range(self._table.columnCount()):
            widget = self._table.cellWidget(row, col)
            if widget is not None:
                widget.deleteLater()
                self._table.removeCellWidget(row, col)

        # 刷新表格恢复正常显示
        self._apply_filter()

    def _get_host_data_by_id(self, host_id: int) -> dict | None:
        """从缓存中按 host_id 查找主机数据"""
        for d in self._host_data:
            if d.get("id") == host_id:
                return d
        return None

    def eventFilter(self, watched: object, event: QKeyEvent):
        """事件过滤器：Esc 键取消编辑，焦点离开编辑行自动保存"""
        if self._editing_row is not None:
            # Esc 取消
            if event.type() == event.Type.KeyPress:
                if event.key() == Qt.Key.Key_Escape:
                    self._cancel_inline_edit()
                    return True
            # 焦点离开编辑 widget → 延迟检查是否还在编辑行内
            if event.type() == event.Type.FocusOut:
                QTimer.singleShot(0, self._check_focus_after_leave)
        return super().eventFilter(watched, event)

    def _show_context_menu(self, pos):
        """右键菜单"""
        row = self._table.rowAt(pos.y())
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                color: #333333;
            }
            QMenu::item:selected {
                background-color: #E0E0E0;
            }
        """)

        if row >= 0:
            host_id = self._get_host_id_from_row(row)
            if host_id is not None:
                edit_action = QAction("✏️ 编辑主机", self)
                edit_action.triggered.connect(lambda: self.edit_requested.emit(host_id))
                menu.addAction(edit_action)

                test_action = QAction("🔌 连接测试", self)
                test_action.triggered.connect(lambda: self.test_requested.emit(host_id))
                menu.addAction(test_action)

                menu.addSeparator()

                delete_action = QAction("🗑️ 删除主机", self)
                delete_action.triggered.connect(lambda: self.delete_requested.emit(host_id))
                menu.addAction(delete_action)
        if menu.actions():
            selected = self.get_selected_host_ids()
            if selected:
                batch_delete = QAction(f"🗑️ 批量删除 ({len(selected)})", self)
                batch_delete.triggered.connect(lambda: self.batch_delete_requested.emit(selected))
                menu.addAction(batch_delete)

        menu.exec(self._table.viewport().mapToGlobal(pos))
