from __future__ import annotations
# -*- coding: utf-8 -*-
"""
步骤模板弹窗

两种使用模式：
- 管理模式 (mode="manage"): 查看模板列表、编辑、删除模板
- 选择模式 (mode="select"): 选择一个模板后转为步骤字典返回
"""
from typing import Literal

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem,
    QMessageBox, QWidget, QInputDialog,
)
from PySide6.QtCore import Qt, QSize

from core.step_template_service import StepTemplateService


class StepTemplateDialog(QDialog):
    """步骤模板弹窗（管理/选择）"""

    STEP_ICONS = {
        "ssh_command": "\u2328\ufe0f",
        "sftp_upload": "\ud83d\udce5",
        "sftp_download": "\ud83d\udce5",
    }

    STEP_TYPE_LABELS = {
        "ssh_command": "命令执行",
        "sftp_upload": "文件上传",
        "sftp_download": "文件下载",
    }

    def __init__(self, parent=None, mode: Literal["select", "manage"] = "select"):
        """
        Args:
            parent: 父窗口
            mode: "select" 选择模式（用于从模板添加步骤），"manage" 管理模式（纯管理）
        """
        super().__init__(parent)
        self._mode = mode
        self._service = StepTemplateService()
        self._templates: list[dict] = []
        self._result: dict | None = None
        self._setup_ui()
        self._load_templates()

    def _setup_ui(self):
        """初始化 UI"""
        is_manage = self._mode == "manage"

        if is_manage:
            self.setWindowTitle("模板管理")
        else:
            self.setWindowTitle("从模板添加步骤")
        self.setMinimumWidth(560)
        self.setMinimumHeight(450)
        self.setStyleSheet("background-color: #FFFFFF; color: #333333;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # 标题 + 搜索
        header = QHBoxLayout()
        header.setSpacing(8)

        title_text = "步骤模板管理" if is_manage else "已保存的步骤模板"
        title = QLabel(title_text)
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #333333;")
        header.addWidget(title)

        header.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setFixedWidth(180)
        self._search_input.setPlaceholderText("\U0001f50d 搜索模板...")
        self._search_input.setStyleSheet("""
            QLineEdit {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QLineEdit:focus { border-color: #1976D2; }
        """)
        self._search_input.textChanged.connect(self._on_search)
        header.addWidget(self._search_input)

        layout.addLayout(header)

        # 模板列表
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                background-color: #F5F5F5;
                border: 1px solid #E0E0E0;
                border-radius: 4px;
                color: #333333;
                font-size: 13px;
            }
            QListWidget::item {
                border-bottom: 1px solid #E0E0E0;
                padding: 4px 0px;
            }
            QListWidget::item:selected {
                background-color: #E3F2FD;
                color: #1565C0;
            }
            QListWidget::item:hover:!selected {
                background-color: #FFFFFF;
            }
        """)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, 1)

        # 提示
        self._hint_label = QLabel("")
        self._hint_label.setStyleSheet("color: #999999; font-size: 11px;")
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        # 底部按钮
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(12)

        btn_cancel = QPushButton("关闭")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #E0E0E0;
                color: #333333;
                border: 1px solid #D0D0D0;
                padding: 6px 20px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #D0D0D0; }
        """)
        btn_bar.addWidget(btn_cancel)

        btn_bar.addStretch()

        # 管理模式下：重命名 + 删除
        if is_manage:
            btn_rename = QPushButton("\u270f\ufe0f 重命名")
            btn_rename.setFixedHeight(34)
            btn_rename.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rename.clicked.connect(self._on_rename)
            btn_rename.setStyleSheet("""
                QPushButton {
                    background-color: #E3F2FD;
                    color: #1565C0;
                    border: 1px solid #90CAF9;
                    padding: 6px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                }
                QPushButton:hover { background-color: #BBDEFB; }
            """)
            btn_bar.addWidget(btn_rename)

        btn_delete = QPushButton("\U0001f5d1\ufe0f 删除选中")
        btn_delete.setFixedHeight(34)
        btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_delete.clicked.connect(self._on_delete)
        btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #FFEBEE;
                color: #E53935;
                border: 1px solid #EF9A9A;
                padding: 6px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #FFCDD2; }
        """)
        btn_bar.addWidget(btn_delete)

        # 选择模式下：插入按钮
        if not is_manage:
            btn_insert = QPushButton("\U0001f4e6 插入步骤")
            btn_insert.setFixedHeight(34)
            btn_insert.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_insert.clicked.connect(self._on_insert)
            btn_insert.setStyleSheet("""
                QPushButton {
                    background-color: #1976D2;
                    color: #FFFFFF;
                    border: none;
                    padding: 6px 20px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1565C0; }
            """)
            btn_bar.addWidget(btn_insert)

        layout.addLayout(btn_bar)

    def _load_templates(self):
        """加载模板列表"""
        self._templates = self._service.list_templates()
        self._populate_list()

    def _populate_list(self, keyword: str = ""):
        """填充列表（支持搜索过滤）"""
        self._list.clear()
        kw = keyword.strip().lower()
        for tpl in self._templates:
            name = tpl.get("name", "")
            if kw and kw not in name.lower():
                continue

            item = QListWidgetItem()
            template_id = tpl.get("id")
            item.setData(Qt.ItemDataRole.UserRole, template_id)
            item.setSizeHint(QSize(540, 52))

            # 自定义 widget
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(8, 4, 8, 4)
            item_layout.setSpacing(8)

            step_type = tpl.get("step_type", "ssh_command")
            icon = self.STEP_ICONS.get(step_type, "\ud83d\udccb")
            type_label = self.STEP_TYPE_LABELS.get(step_type, step_type)

            icon_label = QLabel(icon)
            icon_label.setFixedWidth(24)
            icon_label.setStyleSheet("font-size: 14px;")
            item_layout.addWidget(icon_label)

            name_label = QLabel(f"<b>{name}</b>")
            name_label.setStyleSheet("color: #333333; font-size: 13px;")
            item_layout.addWidget(name_label)

            type_tag = QLabel(type_label)
            type_tag.setStyleSheet("color: #666666; font-size: 11px; padding: 1px 6px; background-color: #E8E8E8; border-radius: 3px;")
            item_layout.addWidget(type_tag)

            item_layout.addStretch()

            # 摘要信息
            summary_parts = []
            command = tpl.get("command", "") or ""
            local_path = tpl.get("local_path", "") or ""
            remote_path = tpl.get("remote_path", "") or ""
            if command:
                summary_parts.append(f"命令: {command[:40]}")
            if local_path:
                summary_parts.append(f"本地: {local_path[:30]}")
            if remote_path:
                summary_parts.append(f"远程: {remote_path[:30]}")
            summary = " | ".join(summary_parts[:2])
            if summary:
                summary_label = QLabel(summary)
                summary_label.setStyleSheet("color: #999999; font-size: 11px;")
                summary_label.setToolTip(summary)
                item_layout.addWidget(summary_label)

            # 行内删除按钮
            btn_del = QPushButton("\U0001f5d1\ufe0f")
            btn_del.setFixedSize(24, 24)
            btn_del.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_del.setToolTip("删除此模板")
            btn_del.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    border: none;
                    font-size: 12px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #FFEBEE;
                    border-radius: 3px;
                }
            """)
            btn_del.clicked.connect(lambda checked, tid=template_id, tpl_name=name: self._on_delete_one(tid, tpl_name))
            item_layout.addWidget(btn_del)

            # 先 addItem 再 setItemWidget
            self._list.addItem(item)
            self._list.setItemWidget(item, item_widget)

        count = self._list.count()
        if count == 0:
            if kw:
                self._hint_label.setText(f"没有匹配 '{keyword}' 的模板。")
            else:
                self._hint_label.setText("暂无模板。在步骤卡片上点击「📌保存」可将步骤保存为模板。")
        else:
            if self._mode == "manage":
                self._hint_label.setText(f"共 {count} 个模板")
            else:
                self._hint_label.setText(f"共 {count} 个模板，双击模板或选中后点击「插入步骤」")

    def _on_search(self, text: str):
        """搜索过滤"""
        self._populate_list(text)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """双击：选择模式插入，管理模式无操作"""
        if self._mode == "select":
            self._on_insert()

    def _on_insert(self):
        """插入选中的模板（仅选择模式）"""
        current = self._list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return

        template_id = current.data(Qt.ItemDataRole.UserRole)
        try:
            self._result = self._service.get_as_step_dict(template_id)
            self.accept()
        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载模板失败: {e}")

    def _on_rename(self):
        """重命名选中的模板（仅管理模式）"""
        current = self._list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return

        template_id = current.data(Qt.ItemDataRole.UserRole)
        tpl_name = ""
        for tpl in self._templates:
            if tpl.get("id") == template_id:
                tpl_name = tpl.get("name", "")
                break

        new_name, ok = QInputDialog.getText(
            self, "重命名模板", "新模板名称:", text=tpl_name,
        )
        if ok and new_name.strip() and new_name.strip() != tpl_name:
            try:
                from data.database import get_db
                from data.step_template_repository import StepTemplateRepository
                with get_db().session_scope() as session:
                    repo = StepTemplateRepository(session)
                    template = repo.get_by_id(template_id)
                    if template:
                        template.name = new_name.strip()
                self._load_templates()
            except Exception as e:
                QMessageBox.warning(self, "重命名失败", f"重命名时发生错误: {e}")

    def _on_delete(self):
        """删除选中的模板"""
        current = self._list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择一个模板")
            return

        template_id = current.data(Qt.ItemDataRole.UserRole)
        tpl_name = ""
        for tpl in self._templates:
            if tpl.get("id") == template_id:
                tpl_name = tpl.get("name", "")
                break

        self._do_delete(template_id, tpl_name)

    def _on_delete_one(self, template_id: int, template_name: str):
        """行内删除按钮"""
        self._do_delete(template_id, template_name)

    def _do_delete(self, template_id: int, template_name: str):
        """执行删除"""
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除模板 '{template_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._service.delete_template(template_id)
            self._load_templates()

    def get_result(self) -> dict | None:
        """获取选中的模板步骤字典，取消返回 None"""
        return self._result
