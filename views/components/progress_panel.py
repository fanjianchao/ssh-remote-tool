from __future__ import annotations
# -*- coding: utf-8 -*-
"""
进度面板

多主机并行进度条、统计信息、主机状态列表。
支持单台主机的传输进度条实时更新。
主机按状态排序：failed > running/transferring > pending > success。
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QFrame, QScrollArea, QMenu,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QAction

from config.constants import (
    COLOR_SUCCESS, COLOR_ERROR, COLOR_WARNING,
    COLOR_INFO, COLOR_RUNNING, COLOR_PENDING,
)


# 状态图标
STATUS_ICONS = {
    "pending": "⏸",
    "running": "⏳",
    "success": "✅",
    "failed": "❌",
    "skipped": "⏭",
    "cancelled": "🚫",
    "transferring": "⏳",
}

# 状态标签
STATUS_LABELS = {
    "pending": "等待",
    "running": "执行中",
    "success": "成功",
    "failed": "失败",
    "skipped": "跳过",
    "cancelled": "已取消",
    "transferring": "传输中",
}

# 进度条颜色
STATUS_BAR_COLORS = {
    "pending": "#BDBDBD",
    "running": "#1976D2",
    "success": "#43A047",
    "failed": "#E53935",
    "skipped": "#BDBDBD",
    "cancelled": "#F9A825",
    "transferring": "#1976D2",
}

# 行背景颜色
STATUS_ROW_COLORS = {
    "pending": "#F5F5F5",
    "running": "#E3F2FD",
    "success": "#E8F5E9",
    "failed": "#FFEBEE",
    "skipped": "#F5F5F5",
    "cancelled": "#FFF8E1",
    "transferring": "#E3F2FD",
}

# 排序优先级（越小越靠前）
STATUS_SORT_ORDER = {
    "failed": 0,
    "running": 1,
    "transferring": 1,
    "cancelled": 2,
    "pending": 3,
    "success": 4,
    "skipped": 5,
}


class StepProgressBar(QWidget):
    """
    分段进度条：每个步骤一段，独立着色。

    颜色方案：
      pending   → #E0E0E0 (浅灰)
      running   → #1976D2 (蓝)
      success   → #43A047 (绿)
      failed    → #E53935 (红)
      skipped   → #BDBDBD (灰)
      cancelled → #F9A825 (黄)
    """

    STEP_COLORS = {
        "pending": "#E0E0E0",
        "running": "#1976D2",
        "success": "#43A047",
        "failed": "#E53935",
        "skipped": "#BDBDBD",
        "cancelled": "#F9A825",
    }

    def __init__(self, total_steps: int = 0, step_names: list[str] | None = None, parent=None):
        super().__init__(parent)
        self._total_steps = max(total_steps, 1)
        self._step_names: list[str] = list(step_names or [])
        self._step_statuses: list[str] = ["pending"] * self._total_steps
        self.setFixedHeight(12)
        self.setMinimumWidth(60)
        self.setMouseTracking(True)
        self._hovered_index: int = -1

    def set_total_steps(self, total: int, step_names: list[str] | None = None):
        """设置总步骤数（重置所有状态）"""
        self._total_steps = max(total, 1)
        self._step_names = list(step_names or [])
        self._step_statuses = ["pending"] * self._total_steps
        self.update()

    def set_step_status(self, step_index: int, status: str):
        """设置指定步骤的状态"""
        if 0 <= step_index < self._total_steps:
            self._step_statuses[step_index] = status
            self.update()

    def _status_label(self, status: str) -> str:
        """状态中文标签"""
        labels = {
            "pending": "等待",
            "running": "执行中",
            "success": "成功",
            "failed": "失败",
            "skipped": "跳过",
            "cancelled": "已取消",
        }
        return labels.get(status, status)

    def _seg_rect(self, index: int):
        """计算第 index 段的 (x, width)，基于当前 widget 宽度"""
        gap = 2
        n = self._total_steps
        total_gap = gap * (n - 1) if n > 1 else 0
        seg_w = max((self.width() - total_gap) / n, 4)
        x = index * (seg_w + gap)
        return x, seg_w

    def _hit_test(self, pos_x: int) -> int:
        """根据鼠标 x 坐标返回所在段索引，-1 表示不在任何段内"""
        gap = 2
        n = self._total_steps
        total_gap = gap * (n - 1) if n > 1 else 0
        seg_w = max((self.width() - total_gap) / n, 4)
        for i in range(n):
            x0 = i * (seg_w + gap)
            if x0 <= pos_x <= x0 + seg_w:
                return i
        return -1

    def mouseMoveEvent(self, event):
        idx = self._hit_test(event.position().x())
        if idx != self._hovered_index:
            self._hovered_index = idx
            if idx >= 0:
                name = self._step_names[idx] if idx < len(self._step_names) else f"步骤 {idx + 1}"
                status = self._step_statuses[idx] if idx < len(self._step_statuses) else "pending"
                self.setToolTip(f"步骤 {idx + 1}: {name}\n状态: {self._status_label(status)}")
            else:
                self.setToolTip("")

    def leaveEvent(self, event):
        self._hovered_index = -1
        self.setToolTip("")

    def get_step_statuses(self) -> list[str]:
        return list(self._step_statuses)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        gap = 2  # 段间距
        n = self._total_steps
        total_gap = gap * (n - 1) if n > 1 else 0
        seg_w = max((w - total_gap) / n, 4)  # 每段最小 4px
        radius = 3  # 圆角

        for i in range(n):
            color = QColor(self.STEP_COLORS.get(self._step_statuses[i], "#E0E0E0"))
            x = i * (seg_w + gap)

            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(int(x), 0, int(seg_w), h, radius, radius)

        painter.end()


class ProgressPanel(QWidget):
    """执行进度面板"""

    host_double_clicked = Signal(str)  # host_id，双击主机行时发出
    retry_host_requested = Signal(str)  # host_id，重试该主机（从第一个失败步骤开始）
    retry_step_requested = Signal(str, int)  # host_id, step_index，重试指定步骤
    retry_all_hosts_requested = Signal()  # 重试所有主机任务

    def __init__(self, parent=None):
        super().__init__(parent)
        self._host_status: dict[str, str] = {}  # host_id → status
        self._host_names: dict[str, str] = {}  # host_id → host_name
        self._host_info: dict[str, str] = {}  # host_id → "ip:port@user" 显示文本
        self._host_step_progress: dict[str, int] = {}  # host_id → 已完成步骤数
        self._host_step_statuses: dict[str, list[str]] = {}  # host_id → [每步状态]
        self._current_step_name: str = ""
        self._total_steps: int = 0
        self._current_step_index: int = 0
        self._start_time: datetime | None = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._elapsed_timer.setInterval(1000)

        # 行 widget 引用缓存（host_id → row QFrame），避免高频更新时重建
        self._row_widgets: dict[str, QFrame] = {}
        # 行内子控件引用（host_id → {icon_label, name_label, step_bar, detail_label, row_frame}）
        self._row_parts: dict[str, dict] = {}
        # 传输进度数据（host_id → {transferred, total, speed}）
        self._transfer_data: dict[str, dict] = {}
        self._app_signals = None
        # host_id → row 的反向映射（用于事件过滤器）
        self._row_host_map: dict[int, str] = {}
        # 当前高亮的主机 ID（日志筛选）
        self._highlighted_host: str | None = None

        self._setup_ui()

    def set_app_signals(self, signals):
        """设置全局信号，用于同步耗时到状态栏"""
        self._app_signals = signals

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        # === 第一行：统计信息 + 操作按钮（右对齐） ===
        self._stats_layout = QHBoxLayout()
        self._stats_layout.setSpacing(16)
        self._stats_labels: dict[str, QLabel] = {}

        for key, label_text in [
            ("total", "总主机"),
            ("success", "成功"),
            ("failed", "失败"),
            ("running", "执行中"),
            ("pending", "等待中"),
        ]:
            lbl = QLabel(f"{label_text}: 0")
            lbl.setStyleSheet("color: #666666; font-size: 12px;")
            self._stats_labels[key] = lbl
            self._stats_layout.addWidget(lbl)

        # stretch 撑开，按钮靠右
        self._stats_layout.addStretch()
        layout.addLayout(self._stats_layout)

        # === 第二行：当前步骤信息 + 总体进度条 ===
        step_info = QHBoxLayout()
        step_info.setContentsMargins(0, 0, 0, 0)
        step_info.setSpacing(12)

        self._step_label = QLabel("就绪")
        self._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")
        step_info.addWidget(self._step_label)

        # 总体进度条
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.setFixedHeight(20)
        self._progress_bar.setMinimumWidth(200)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E0E0E0;
                border: none;
                border-radius: 4px;
                color: #333333;
                font-size: 11px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #1976D2;
                border-radius: 4px;
            }
        """)
        # 启用右键菜单
        self._progress_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._progress_bar.customContextMenuRequested.connect(self._show_progress_bar_context_menu)
        step_info.addWidget(self._progress_bar, stretch=1)
        layout.addLayout(step_info)

        # === 第三区：主机状态列表（可滚动） ===
        self._host_scroll = QScrollArea()
        self._host_scroll.setWidgetResizable(True)
        self._host_scroll.setMinimumHeight(40)
        self._host_scroll.setMaximumHeight(200)
        self._host_scroll.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
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

        self._host_list_container = QWidget()
        self._host_list_container.setStyleSheet("background-color: transparent;")
        self._host_list_layout = QVBoxLayout(self._host_list_container)
        self._host_list_layout.setContentsMargins(4, 4, 4, 4)
        self._host_list_layout.setSpacing(2)

        # 空状态提示
        self._empty_label = QLabel("暂无主机")
        self._empty_label.setStyleSheet("color: #BDBDBD; font-size: 12px;")
        self._host_list_layout.addWidget(self._empty_label)

        self._host_scroll.setWidget(self._host_list_container)
        layout.addWidget(self._host_scroll)

    @property
    def stats_layout(self) -> QHBoxLayout:
        """暴露统计行布局，供外部插入操作按钮（靠右，stretch 之后）"""
        return self._stats_layout

    # ============ 公共方法 ============

    def start_execution(self, host_ids: list[str], host_names: dict[str, str],
                        total_steps: int, step_name: str = "",
                        host_info: dict[str, str] | None = None,
                        step_names: list[str] | None = None):
        """
        开始执行，初始化主机列表。

        Args:
            host_ids: 主机 ID 列表
            host_names: host_id → 主机名 映射
            total_steps: 总步骤数
            step_name: 第一个步骤名称
            host_info: host_id → 主机连接信息（如 "192.168.1.1:22@root"）
            step_names: 所有步骤名称列表（用于分段进度条悬浮提示）
        """
        # 清除行缓存（步骤数可能变化，必须重建）
        while self._host_list_layout.count():
            item = self._host_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._row_widgets.clear()
        self._row_parts.clear()
        self._row_host_map.clear()

        self._host_status = {hid: "pending" for hid in host_ids}
        self._host_names = host_names
        self._host_info = host_info or {}
        self._host_step_progress = {hid: 0 for hid in host_ids}
        self._host_step_statuses = {hid: ["pending"] * total_steps for hid in host_ids}
        self._total_steps = total_steps
        self._step_names = list(step_names or [])
        self._current_step_index = 0
        self._start_time = datetime.now()
        self._highlighted_host = None

        self._update_step_label(step_name)
        self._refresh_host_list()
        self._update_stats()
        self._progress_bar.setValue(0)
        self._elapsed_timer.start()

    def update_step(self, step_index: int, step_name: str):
        """更新当前步骤"""
        self._current_step_index = step_index
        self._update_step_label(step_name)

        if self._total_steps > 0:
            progress = int((step_index / self._total_steps) * 100)
            self._progress_bar.setValue(min(progress, 99))

    def update_host_status(self, host_id: str, status: str):
        """更新单台主机的状态（仅更新样式，不重排）"""
        self._host_status[host_id] = status
        # 传输结束/状态切换时清理传输进度数据
        if status != "transferring":
            self._transfer_data.pop(host_id, None)
        self._update_row_style(host_id)
        self._update_stats()

    def update_host_step_progress(self, host_id: str, completed_steps: int):
        """更新单台主机的步骤进度（已完成步骤数）"""
        self._host_step_progress[host_id] = completed_steps
        self._update_row_progress(host_id)

    def update_host_step_status(self, host_id: str, step_index: int, success: bool):
        """更新单台主机某个步骤的状态（成功/失败），用于分段进度条着色"""
        if host_id in self._host_step_statuses and 0 <= step_index < len(self._host_step_statuses[host_id]):
            self._host_step_statuses[host_id][step_index] = "success" if success else "failed"
            self._update_row_progress(host_id)

    def update_host_step_running(self, host_id: str, step_index: int):
        """更新单台主机某个步骤为运行中状态"""
        if host_id in self._host_step_statuses and 0 <= step_index < len(self._host_step_statuses[host_id]):
            self._host_step_statuses[host_id][step_index] = "running"
            self._update_row_progress(host_id)

    def init_transfer(self, host_id: str):
        """标记主机进入传输状态"""
        if host_id in self._host_status:
            self._host_status[host_id] = "transferring"
            self._transfer_data[host_id] = {"transferred": 0, "total": 0, "speed": 0}
            self._update_row_style(host_id)
            self._update_stats()

    def update_transfer_progress(self, host_id: str, transferred: int, total: int, speed: int):
        """更新单台主机的传输进度"""
        self._transfer_data[host_id] = {"transferred": transferred, "total": total, "speed": speed}
        self._update_row_transfer(host_id)

    def sort_and_refresh(self):
        """按状态排序并刷新主机列表（在 host_finished 时调用）"""
        self._refresh_host_list()

    def highlight_host(self, host_id: str | None):
        """高亮指定主机行（日志筛选时使用）"""
        self._highlighted_host = host_id
        for hid, parts in self._row_parts.items():
            row_frame = parts["row_frame"]
            if hid == host_id:
                row_frame.setStyleSheet(row_frame.styleSheet().replace(
                    "border: 1px solid transparent;",
                    "border: 2px solid #1976D2;"
                ))
            else:
                row_frame.setStyleSheet(row_frame.styleSheet().replace(
                    "border: 2px solid #1976D2;",
                    "border: 1px solid transparent;"
                ))

    def finish_execution(self, all_success: bool, summary: dict):
        """
        执行完成。

        Args:
            all_success: 是否全部成功
            summary: 结果摘要
        """
        self._elapsed_timer.stop()
        self._progress_bar.setValue(100)

        if all_success:
            self._progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E0E0E0;
                    border: none;
                    border-radius: 4px;
                    color: #fff;
                    text-align: center;
                    font-size: 11px;
                }
                QProgressBar::chunk {
                    background-color: #43A047;
                    border-radius: 4px;
                }
            """)
            self._step_label.setText("✅ 执行完成 - 全部成功")
            self._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #43A047;")
        else:
            self._progress_bar.setStyleSheet("""
                QProgressBar {
                    background-color: #E0E0E0;
                    border: none;
                    border-radius: 4px;
                    color: #fff;
                    text-align: center;
                    font-size: 11px;
                }
                QProgressBar::chunk {
                    background-color: #E53935;
                    border-radius: 4px;
                }
            """)
            failed = summary.get("failed_hosts", 0)
            total = summary.get("total_hosts", 0)
            self._step_label.setText(f"⚠️ 执行完成 - {failed}/{total} 台主机失败")
            self._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E53935;")

        duration = summary.get("duration_seconds", 0)
        if self._app_signals:
            self._app_signals.elapsed_updated.emit(self._format_duration(duration))

        # 更新最终状态
        for host_id, result in summary.get("host_results", {}).items():
            self._host_status[host_id] = "success" if result.get("success") else "failed"
            self._host_step_progress[host_id] = self._total_steps
        self._refresh_host_list()
        self._update_stats()

    def reset(self):
        """重置面板"""
        self._host_status.clear()
        self._host_names.clear()
        self._host_info.clear()
        self._host_step_progress.clear()
        self._row_widgets.clear()
        self._row_parts.clear()
        self._transfer_data.clear()
        self._row_host_map.clear()
        self._highlighted_host = None
        self._elapsed_timer.stop()
        self._step_label.setText("就绪")
        self._step_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #E0E0E0;
                border: none;
                border-radius: 4px;
                color: #333333;
                text-align: center;
                font-size: 11px;
            }
            QProgressBar::chunk {
                background-color: #1976D2;
                border-radius: 4px;
            }
        """)

        # 清空列表
        while self._host_list_layout.count():
            item = self._host_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

        self._empty_label = QLabel("暂无主机")
        self._empty_label.setStyleSheet("color: #BDBDBD; font-size: 12px;")
        self._host_list_layout.addWidget(self._empty_label)

        self._update_stats()

    # ============ 内部方法 ============

    def eventFilter(self, obj, event):
        """拦截主机行及其子控件的双击、右键事件"""
        host_id = self._row_host_map.get(id(obj))
        if host_id:
            # 双击 → 筛选日志
            if event.type() == event.Type.MouseButtonDblClick:
                self.host_double_clicked.emit(host_id)
                return True
            # 右键 → 弹出重试菜单（子控件上右键时，Qt 不会向上传播 contextMenu）
            if event.type() == event.Type.ContextMenu:
                # 将子控件本地坐标转换为屏幕坐标，再交给 _show_context_menu 定位
                from PySide6.QtWidgets import QWidget as _QWidget
                if isinstance(obj, _QWidget):
                    global_pos = obj.mapToGlobal(event.pos())
                else:
                    row = self._row_widgets.get(host_id)
                    global_pos = row.mapToGlobal(event.pos()) if row else event.pos()
                self._show_context_menu_global(global_pos, host_id)
                return True
        return super().eventFilter(obj, event)

    def _get_failed_step_indices(self, host_id: str) -> list[int]:
        """获取主机上所有失败步骤的索引"""
        statuses = self._host_step_statuses.get(host_id, [])
        return [i for i, s in enumerate(statuses) if s == "failed"]

    def _show_context_menu(self, pos, host_id: str):
        """显示主机行的右键菜单（pos 为行容器本地坐标）"""
        row = self._row_widgets.get(host_id)
        if not row:
            return
        global_pos = row.mapToGlobal(pos)
        self._show_context_menu_global(global_pos, host_id)

    def _show_context_menu_global(self, global_pos, host_id: str):
        """显示主机行的右键菜单（global_pos 为屏幕坐标）"""
        failed_steps = self._get_failed_step_indices(host_id)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                font-size: 13px;
                color: #333333;
            }
            QMenu::item:hover {
                background-color: #E3F2FD;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E0E0E0;
                margin: 4px 8px;
            }
        """)

        # 选项1：重试任务（从头开始执行所有步骤）
        action_retry_host = QAction("🔄 重试任务", self)
        action_retry_host.triggered.connect(
            lambda checked, hid=host_id: self.retry_host_requested.emit(hid)
        )
        menu.addAction(action_retry_host)

        # 选项2：重试失败步骤
        if len(failed_steps) > 1:
            retry_step_menu = menu.addMenu("🔄 重试失败步骤")
            for idx in failed_steps:
                step_name = self._step_names[idx] if idx < len(self._step_names) else f"步骤 {idx + 1}"
                action = QAction(f"步骤 {idx + 1}: {step_name}", self)
                action.triggered.connect(
                    lambda checked, hid=host_id, si=idx: self.retry_step_requested.emit(hid, si)
                )
                retry_step_menu.addAction(action)
        elif len(failed_steps) == 1:
            idx = failed_steps[0]
            step_name = self._step_names[idx] if idx < len(self._step_names) else f"步骤 {idx + 1}"
            action = QAction(f"🔄 重试失败步骤（步骤 {idx + 1}: {step_name}）", self)
            action.triggered.connect(
                lambda checked, hid=host_id, si=idx: self.retry_step_requested.emit(hid, si)
            )
            menu.addAction(action)
        else:
            action_no_failed = QAction("重试失败步骤（无失败步骤）", self)
            action_no_failed.setEnabled(False)
            menu.addAction(action_no_failed)

        if menu.actions():
            menu.exec(global_pos)

    def _update_step_label(self, step_name: str):
        """更新步骤标签"""
        if step_name:
            self._step_label.setText(f"📝 步骤 {self._current_step_index + 1}/{self._total_steps}: {step_name}")
        else:
            self._step_label.setText("就绪")

    def _sort_host_ids(self) -> list[str]:
        """按状态优先级排序主机 ID：failed > running/transferring > pending > success"""
        return sorted(
            self._host_status.keys(),
            key=lambda hid: (STATUS_SORT_ORDER.get(self._host_status.get(hid, "pending"), 99), hid),
        )

    def _refresh_host_list(self):
        """刷新主机列表（清空后按排序重建）"""
        # 清空现有行
        while self._host_list_layout.count():
            item = self._host_list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                # 不 deleteLater，缓存复用

        if not self._host_status:
            self._row_widgets.clear()
            self._row_parts.clear()
            self._empty_label = QLabel("暂无主机")
            self._empty_label.setStyleSheet("color: #BDBDBD; font-size: 12px;")
            self._host_list_layout.addWidget(self._empty_label)
            return

        # 按状态排序后添加
        sorted_ids = self._sort_host_ids()
        for host_id in sorted_ids:
            status = self._host_status.get(host_id, "pending")
            row = self._get_or_create_row(host_id, status)
            self._host_list_layout.addWidget(row)

        self._host_list_layout.addStretch()

    def _get_or_create_row(self, host_id: str, status: str) -> QFrame:
        """获取或创建主机行 widget"""
        name = self._host_names.get(host_id, host_id)
        bar_color = STATUS_BAR_COLORS.get(status, "#BDBDBD")
        row_bg = STATUS_ROW_COLORS.get(status, "#F5F5F5")
        completed = self._host_step_progress.get(host_id, 0)
        is_transferring = status == "transferring"

        if host_id in self._row_widgets:
            # 复用已有行，更新样式和进度
            row = self._row_widgets[host_id]
            parts = self._row_parts[host_id]
            self._apply_row_style(row, status, bar_color, row_bg)
            parts["icon_label"].setText(STATUS_ICONS.get(status, "⏸"))
            parts["name_label"].setText(name)
            self._update_row_progress(host_id)
            if is_transferring:
                self._update_row_transfer(host_id)
            return row

        # 创建新行
        row = QFrame()
        row.setFixedHeight(36)
        self._apply_row_style(row, status, bar_color, row_bg)
        row.installEventFilter(self)
        row.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        row.customContextMenuRequested.connect(
            lambda pos, hid=host_id: self._show_context_menu(pos, hid)
        )
        self._row_host_map[id(row)] = host_id

        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(8, 4, 8, 4)
        row_layout.setSpacing(8)

        # 状态图标
        icon_label = QLabel(STATUS_ICONS.get(status, "⏸"))
        icon_label.setFixedWidth(20)
        icon_label.setStyleSheet("font-size: 14px; border: none;")
        row_layout.addWidget(icon_label)

        # 主机名
        name_label = QLabel(name)
        name_label.setFixedWidth(140)
        name_label.setStyleSheet("font-size: 13px; font-weight: bold; color: #333333; border: none;")
        row_layout.addWidget(name_label)

        # 步骤分段进度条
        step_bar = StepProgressBar(self._total_steps, step_names=self._step_names)
        step_statuses = self._host_step_statuses.get(host_id, [])
        if step_statuses:
            step_bar._step_statuses = list(step_statuses)
        row_layout.addWidget(step_bar, stretch=1)

        # 进度详情文字
        detail_text = self._build_detail_text(host_id, status, completed, is_transferring)
        detail_label = QLabel(detail_text)
        detail_label.setFixedWidth(140)
        detail_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        detail_label.setStyleSheet("font-size: 11px; color: #666666; border: none;")
        row_layout.addWidget(detail_label)

        parts = {
            "row_frame": row,
            "icon_label": icon_label,
            "name_label": name_label,
            "step_bar": step_bar,
            "detail_label": detail_label,
        }
        self._row_widgets[host_id] = row
        self._row_parts[host_id] = parts

        # 将所有子控件也注册到 _row_host_map，并安装事件过滤器
        # 这样在子控件上右键/双击时也能被 eventFilter 捕获
        for child_widget in (icon_label, name_label, step_bar, detail_label):
            self._row_host_map[id(child_widget)] = host_id
            child_widget.installEventFilter(self)
            # 允许子控件接收右键事件（默认策略会把右键事件截断）
            child_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        return row

    def _apply_row_style(self, row: QFrame, status: str, bar_color: str, row_bg: str):
        """应用行的样式"""
        border = "border: 2px solid #1976D2;" if self._highlighted_host else "border: 1px solid transparent;"
        # 检查是否是高亮行
        for hid, parts in self._row_parts.items():
            if parts["row_frame"] is row and hid == self._highlighted_host:
                border = "border: 2px solid #1976D2;"
                break
        row.setStyleSheet(f"""
            QFrame {{
                background-color: {row_bg};
                {border}
                border-radius: 4px;
            }}
        """)

    def _build_detail_text(self, host_id: str, status: str,
                           completed: int, is_transferring: bool) -> str:
        """构建进度详情文字"""
        # 步骤进度
        step_text = f"{completed}/{self._total_steps}"

        # 传输进度
        if is_transferring:
            data = self._transfer_data.get(host_id)
            if data and data["total"] > 0:
                total_mb = data["total"] / (1024 * 1024)
                transferred_mb = data["transferred"] / (1024 * 1024)
                speed_kb = data["speed"] / 1024
                return f"{step_text}  {transferred_mb:.1f}/{total_mb:.1f}MB {speed_kb:.0f}KB/s"
            elif data:
                transferred_kb = data["transferred"] / 1024
                speed_kb = data["speed"] / 1024
                return f"{step_text}  {transferred_kb:.0f}KB {speed_kb:.0f}KB/s"

        # 普通状态
        status_text = STATUS_LABELS.get(status, status)
        return f"{status_text}({step_text})"

    def _update_row_style(self, host_id: str):
        """仅更新行的样式（不重排）"""
        if host_id not in self._row_parts:
            return
        parts = self._row_parts[host_id]
        status = self._host_status.get(host_id, "pending")
        bar_color = STATUS_BAR_COLORS.get(status, "#BDBDBD")
        row_bg = STATUS_ROW_COLORS.get(status, "#F5F5F5")
        row = parts["row_frame"]

        # 更新行背景
        self._apply_row_style(row, status, bar_color, row_bg)

        # 更新图标
        parts["icon_label"].setText(STATUS_ICONS.get(status, "⏸"))

        # 更新分段进度条
        step_bar = parts.get("step_bar")
        if step_bar and host_id in self._host_step_statuses:
            step_bar._step_statuses = list(self._host_step_statuses[host_id])
            step_bar.update()

    def _update_row_progress(self, host_id: str):
        """更新行的步骤进度（分段进度条）"""
        if host_id not in self._row_parts:
            return
        parts = self._row_parts[host_id]
        status = self._host_status.get(host_id, "pending")
        completed = self._host_step_progress.get(host_id, 0)
        is_transferring = status == "transferring"

        # 更新分段进度条
        step_bar = parts.get("step_bar")
        if step_bar and host_id in self._host_step_statuses:
            step_bar._step_statuses = list(self._host_step_statuses[host_id])
            step_bar.update()

        # 更新详情文字
        detail_text = self._build_detail_text(host_id, status, completed, is_transferring)
        parts["detail_label"].setText(detail_text)

    def _update_row_transfer(self, host_id: str):
        """更新行的传输进度文字"""
        if host_id not in self._row_parts:
            return
        parts = self._row_parts[host_id]
        status = self._host_status.get(host_id, "pending")
        completed = self._host_step_progress.get(host_id, 0)
        is_transferring = status == "transferring"

        detail_text = self._build_detail_text(host_id, status, completed, is_transferring)
        parts["detail_label"].setText(detail_text)

    def _update_stats(self):
        """更新统计信息"""
        total = len(self._host_status)
        success = sum(1 for s in self._host_status.values() if s == "success")
        failed = sum(1 for s in self._host_status.values() if s == "failed")
        running = sum(1 for s in self._host_status.values() if s in ("running", "transferring"))
        pending = sum(1 for s in self._host_status.values() if s == "pending")

        self._stats_labels["total"].setText(f"总主机: {total}")
        self._stats_labels["success"].setText(f"成功: {success}")
        self._stats_labels["success"].setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: bold;")
        self._stats_labels["failed"].setText(f"失败: {failed}")
        if failed > 0:
            self._stats_labels["failed"].setStyleSheet(f"color: {COLOR_ERROR}; font-size: 12px; font-weight: bold;")
        else:
            self._stats_labels["failed"].setStyleSheet(f"color: #666666; font-size: 12px;")
        self._stats_labels["running"].setText(f"执行中: {running}")
        self._stats_labels["running"].setStyleSheet("color: #1976D2; font-size: 12px; font-weight: bold;")
        self._stats_labels["pending"].setText(f"等待中: {pending}")

    def _show_progress_bar_context_menu(self, pos):
        """总进度条右键菜单"""
        # 只有存在主机时才显示菜单
        if not self._host_status:
            return

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px;
                font-size: 13px;
                color: #333333;
            }
            QMenu::item:hover {
                background-color: #E3F2FD;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E0E0E0;
                margin: 4px 8px;
            }
        """)

        total = len(self._host_status)
        failed = sum(1 for s in self._host_status.values() if s == "failed")
        success = sum(1 for s in self._host_status.values() if s == "success")

        # 重试所有主机
        action_retry_all = QAction(f"🔄 重试所有主机任务（共 {total} 台）", self)
        action_retry_all.triggered.connect(lambda: self.retry_all_hosts_requested.emit())
        menu.addAction(action_retry_all)

        # 如有失败主机，额外加一条"仅重试失败主机"提示性操作
        if failed > 0:
            menu.addSeparator()
            action_info = QAction(f"ℹ️ 当前: {success} 成功 / {failed} 失败", self)
            action_info.setEnabled(False)
            menu.addAction(action_info)

        global_pos = self._progress_bar.mapToGlobal(pos)
        menu.exec(global_pos)

    def _update_elapsed(self):
        """更新已用时间（同步到状态栏）"""
        if self._start_time:
            elapsed = (datetime.now() - self._start_time).total_seconds()
            if self._app_signals:
                self._app_signals.elapsed_updated.emit(self._format_duration(elapsed))

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """格式化时长（秒，保留1位小数）"""
        return f"{seconds:.1f}秒"
