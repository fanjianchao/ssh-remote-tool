from __future__ import annotations
# -*- coding: utf-8 -*-
"""
日志查看器

终端风格日志面板，按主机分色显示，支持自动滚动、搜索过滤和主机筛选。
"""

from datetime import datetime
import re
from dataclasses import dataclass, field
from PySide6.QtWidgets import (
    QTextEdit, QVBoxLayout, QHBoxLayout, QWidget, QLineEdit,
    QPushButton, QLabel, QCheckBox, QComboBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QColor, QTextCharFormat, QTextCursor, QTextDocument, QAction


# 预定义的主机颜色池（适合白色背景的深色系）
HOST_COLORS = [
    "#333333",  # 默认黑
    "#1565C0",  # 蓝色
    "#2E7D32",  # 绿色
    "#E65100",  # 橙色
    "#6A1B9A",  # 紫色
    "#AD1457",  # 粉红
    "#00695C",  # 青色
    "#BF360C",  # 深橙
    "#0277BD",  # 天蓝
    "#4527A0",  # 深紫
]

# 输出类型颜色（适合白色背景）
OUTPUT_COLORS = {
    "stdout": "#333333",
    "stderr": "#E53935",
    "system": "#666666",
    "success": "#43A047",
    "error": "#E53935",
    "warning": "#F9A825",
    "info": "#1976D2",
}


# 匹配 ANSI 转义码的正则
# \x1b[...m / \033[...m: 完整 ESC 前缀的 CSI 序列
# [数字;数字m: ESC 前缀丢失后残留的 CSI 序列（如 [1;32m, [0m）
# 注意: [100] 等不含分号且不以 m 结尾的文本不会被误匹配
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]|\033\[[0-9;]*[a-zA-Z]|\[[0-9;]*m')


@dataclass
class LogEntry:
    """日志条目记录"""
    host_id: str = ""           # 主机 ID，空字符串表示系统日志
    html: str = ""              # 渲染后的 HTML 片段
    output_type: str = "stdout"  # 输出类型


class LogViewer(QWidget):
    """终端风格日志查看器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_color_map: dict[str, str] = {}  # host_id → 颜色
        self._host_name_map: dict[str, str] = {}   # host_id → 主机名
        self._color_index = 0
        self._auto_scroll = True
        self._search_keyword = ""
        self._log_count = 0
        self._log_entries: list[LogEntry] = []  # 所有日志条目
        self._filter_host_id: str | None = None  # 当前筛选的主机 ID，None 表示全部
        self._highlight_cursors: list[tuple[int, int]] = []  # 高亮区域 (start, end) 位置列表

        self._setup_ui()

        # 自动清理计时器（超过 10000 行时清理旧日志）
        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.timeout.connect(self._cleanup_old_logs)
        self._cleanup_timer.start(5000)

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # --- 工具栏 ---
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍 搜索日志...")
        self._search_input.setClearButtonEnabled(True)
        self._search_input.setFixedHeight(28)
        self._search_input.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._search_input)

        # --- 主机筛选下拉框 ---
        self._host_filter = QComboBox()
        self._host_filter.addItem("🌐 全部主机")  # index=0, 无 UserRole data → 不筛选
        self._host_filter.setFixedHeight(28)
        self._host_filter.setMinimumWidth(140)
        self._host_filter.currentIndexChanged.connect(self._on_host_filter_changed)
        toolbar.addWidget(self._host_filter)

        self._auto_scroll_cb = QCheckBox("自动滚动")
        self._auto_scroll_cb.setChecked(True)
        self._auto_scroll_cb.stateChanged.connect(
            lambda state: setattr(self, "_auto_scroll", state == Qt.CheckState.Checked.value)
        )
        toolbar.addWidget(self._auto_scroll_cb)

        toolbar.addStretch()

        self._count_label = QLabel("0 条日志")
        self._count_label.setStyleSheet("color: #666666; font-size: 11px;")
        toolbar.addWidget(self._count_label)

        clear_btn = QPushButton("清空")
        clear_btn.setFixedSize(60, 28)
        clear_btn.clicked.connect(self.clear_logs)
        toolbar.addWidget(clear_btn)

        export_btn = QPushButton("导出")
        export_btn.setFixedSize(60, 28)
        export_btn.clicked.connect(self._export_logs)
        toolbar.addWidget(export_btn)

        layout.addLayout(toolbar)

        # --- 日志文本区 ---
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Consolas", 11))
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #FAFAFA;
                color: #333333;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 4px;
            }
        """)

        layout.addWidget(self._text_edit)

    # ============ 公共方法 ============

    def append_log(self, host_id: str, text: str, output_type: str = "stdout"):
        """
        追加一条日志。

        Args:
            host_id: 主机标识
            text: 日志文本
            output_type: 输出类型 ("stdout" | "stderr" | "system" | "success" | "error" | "warning" | "info")
        """
        color = OUTPUT_COLORS.get(output_type, OUTPUT_COLORS["stdout"])

        # 去除 ANSI 转义码（终端颜色控制字符）
        text = _ANSI_RE.sub('', text)

        # 构建 HTML 行
        if host_id:
            # 所有带 host_id 的日志都显示 [主机名@时间] 前缀（统一风格，便于识别和筛选）
            host_color = self._get_host_color(host_id)
            display_name = self._host_name_map.get(host_id, host_id)
            timestamp = datetime.now().strftime("%H:%M:%S")
            html = f'<span style="color:{host_color}">[{display_name}@{timestamp}]</span> <span style="color:{color}">{self._escape_html(text)}</span>'
        elif output_type == "system":
            timestamp = datetime.now().strftime("%H:%M:%S")
            html = f'<span style="color:{color}">[{timestamp}] {self._escape_html(text)}</span>'
        else:
            html = f'<span style="color:{color}">{self._escape_html(text)}</span>'

        # 记录日志条目
        entry = LogEntry(host_id=host_id, html=html, output_type=output_type)
        self._log_entries.append(entry)

        # 筛选模式下，仅显示匹配的日志
        if self._filter_host_id is not None and host_id != self._filter_host_id:
            # 系统日志(host_id="")在筛选时始终显示
            if host_id != "":
                self._log_count += 1
                self._count_label.setText(f"{self._log_count} 条日志")
                return

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html + "<br>")
        self._text_edit.setTextCursor(cursor)

        self._log_count += 1
        self._count_label.setText(f"{self._log_count} 条日志")

        if self._auto_scroll:
            self._text_edit.ensureCursorVisible()

    def append_system_log(self, text: str, log_type: str = "info"):
        """
        追加系统日志（非主机输出）。

        Args:
            text: 日志文本
            log_type: "info" | "success" | "error" | "warning"
        """
        self.append_log("", text, log_type)

    def clear_logs(self):
        """清空所有日志"""
        self._text_edit.clear()
        self._log_count = 0
        self._log_entries.clear()
        self._filter_host_id = None
        self._search_keyword = ""
        self._search_input.clear()
        self._count_label.setText("0 条日志")
        self._host_color_map.clear()
        self._host_name_map.clear()
        self._color_index = 0
        # 清空筛选下拉框
        self._host_filter.blockSignals(True)
        self._host_filter.clear()
        self._host_filter.addItem("🌐 全部主机")
        self._host_filter.setCurrentIndex(0)
        self._host_filter.blockSignals(False)

    def assign_host_color(self, host_id: str, host_name: str = ""):
        """为指定主机分配颜色并记录主机名，同时更新筛选下拉框"""
        if host_id not in self._host_color_map:
            self._host_color_map[host_id] = HOST_COLORS[self._color_index % len(HOST_COLORS)]
            self._color_index += 1
        if host_name:
            self._host_name_map[host_id] = host_name

        # 更新主机筛选下拉框（去重），blockSignals 防止 addItem 触发 currentIndexChanged
        display_name = host_name or host_id
        exists = False
        for i in range(self._host_filter.count()):
            item_data = self._host_filter.itemData(i, Qt.ItemDataRole.UserRole)
            if item_data == host_id:
                exists = True
                break
        if not exists and host_id:
            host_color = self._host_color_map.get(host_id, "#333333")
            self._host_filter.blockSignals(True)
            self._host_filter.addItem(f"  {display_name}")
            idx = self._host_filter.count() - 1
            self._host_filter.setItemData(idx, host_id, Qt.ItemDataRole.UserRole)
            self._host_filter.setItemData(idx, QColor(host_color), Qt.ItemDataRole.ForegroundRole)
            self._host_filter.blockSignals(False)

    # ============ 内部方法 ============

    def _get_host_color(self, host_id: str) -> str:
        """获取主机颜色（自动分配）"""
        if host_id not in self._host_color_map:
            self._host_color_map[host_id] = HOST_COLORS[self._color_index % len(HOST_COLORS)]
            self._color_index += 1
        return self._host_color_map[host_id]

    def _escape_html(self, text: str) -> str:
        """转义 HTML 特殊字符"""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    def _on_search_changed(self, text: str):
        """搜索高亮：高亮所有匹配项并滚动到第一个"""
        self._search_keyword = text.strip()
        self._highlight_matches()

    def _on_host_filter_changed(self, index: int):
        """主机筛选切换"""
        if index < 0:
            self._filter_host_id = None
            return

        host_id = self._host_filter.itemData(index, Qt.ItemDataRole.UserRole)
        if host_id is None:
            self._filter_host_id = None
        else:
            self._filter_host_id = str(host_id)

        self._rerender_logs()

    def filter_host(self, host_id: str):
        """按主机 ID 筛选日志（同步更新下拉框）"""
        if not host_id:
            self._host_filter.setCurrentIndex(0)
            return
        for i in range(self._host_filter.count()):
            item_data = self._host_filter.itemData(i, Qt.ItemDataRole.UserRole)
            if item_data == host_id:
                self._host_filter.setCurrentIndex(i)
                return

    def _highlight_matches(self):
        """在当前日志文本中高亮所有搜索关键词匹配"""
        # 先清除旧高亮（只还原之前高亮过的区域）
        self._clear_highlight()
        if not self._search_keyword:
            self._update_count_label(-1)
            return

        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#FFF176"))   # 黄色高亮背景
        fmt.setForeground(QColor("#333333"))    # 深色前景确保文字可读

        # 智能大小写：关键词含大写字母时区分大小写，否则忽略
        flags = QTextDocument.FindFlag(0)
        if any(c.isupper() for c in self._search_keyword):
            flags = QTextDocument.FindFlag.FindCaseSensitively

        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        first_pos = None
        match_count = 0
        self._highlight_cursors = []

        while True:
            found = self._text_edit.document().find(self._search_keyword, cursor, flags)
            if found.isNull():
                break
            start = found.position()
            end = start + len(self._search_keyword)
            self._highlight_cursors.append((start, end))
            found.mergeCharFormat(fmt)
            match_count += 1
            if first_pos is None:
                first_pos = found
            # 下一次搜索从当前匹配之后开始
            cursor.setPosition(end)

        # 滚动到第一个匹配位置
        if first_pos is not None:
            self._text_edit.setTextCursor(first_pos)
            self._text_edit.ensureCursorVisible()

        self._update_count_label(match_count)

    def _clear_highlight(self):
        """通过重渲染日志文本来彻底清除高亮（insertHtml 内联样式优先级高于 CharFormat）"""
        if not self._highlight_cursors:
            return
        # 由于 insertHtml 产生的内联 span style 优先级高于 QTextCharFormat，
        # setCharFormat(transparent) 无法覆盖高亮。最可靠的方式是重渲染。
        self._highlight_cursors.clear()
        self._rerender_logs(skip_highlight=True)

    def _update_count_label(self, match_count: int = -1):
        """更新计数标签，可选显示搜索匹配数。match_count=-1 表示不显示匹配数"""
        total = len(self._log_entries)
        visible = self._log_count
        base = f"{visible}/{total}" if self._filter_host_id is not None else f"{total}"
        if self._search_keyword and match_count >= 0:
            self._count_label.setText(f"{base} 条日志 | 匹配: {match_count}")
        else:
            self._count_label.setText(f"{base} 条日志")

    def _rerender_logs(self, skip_highlight: bool = False):
        """根据当前筛选条件重新渲染所有日志"""
        self._text_edit.clear()
        self._highlight_cursors.clear()  # 位置列表已失效，必须清空
        self._log_count = 0  # 重置计数
        visible_count = 0

        for entry in self._log_entries:
            # 系统日志始终显示
            if entry.host_id == "":
                cursor = self._text_edit.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertHtml(entry.html + "<br>")
                self._text_edit.setTextCursor(cursor)
                visible_count += 1
                continue

            # 筛选模式下，只显示匹配的主机日志
            if self._filter_host_id is not None and entry.host_id != self._filter_host_id:
                continue

            cursor = self._text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertHtml(entry.html + "<br>")
            self._text_edit.setTextCursor(cursor)
            visible_count += 1

        self._log_count = visible_count
        # 如果有搜索关键词且不是跳过高亮模式，重渲染后自动重放高亮
        if self._search_keyword and not skip_highlight:
            self._highlight_matches()
        else:
            self._update_count_label(-1)

    def _cleanup_old_logs(self):
        """清理过多的日志（保持最近 10000 条记录）"""
        if len(self._log_entries) > 10000:
            self._log_entries = self._log_entries[-8000:]

        block_count = self._text_edit.document().blockCount()
        if block_count > 10000:
            cursor = self._text_edit.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.movePosition(
                QTextCursor.MoveOperation.Down,
                QTextCursor.MoveMode.KeepAnchor,
                block_count - 8000,
            )
            cursor.removeSelectedText()

    def _export_logs(self):
        """导出日志到剪贴板"""
        text = self._text_edit.toPlainText()
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.append_system_log("日志已复制到剪贴板", "info")
