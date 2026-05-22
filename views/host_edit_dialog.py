from __future__ import annotations
# -*- coding: utf-8 -*-
"""
主机编辑对话框

表单输入（IP、端口、用户名、密码/密钥、分组、备注）。
支持新建和编辑两种模式。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QTextEdit, QPushButton,
    QLabel, QGroupBox, QFileDialog, QMessageBox, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from config.constants import DEFAULT_SSH_PORT, DEFAULT_GROUP


class HostEditDialog(QDialog):
    """主机编辑对话框"""

    def __init__(self, parent=None, host_data: dict | None = None):
        """
        Args:
            parent: 父窗口
            host_data: 编辑模式时传入的主机数据字典（含 id）；新建时为 None
        """
        super().__init__(parent)
        self._is_edit = host_data is not None
        self._host_data = host_data or {}
        self._result_data: dict | None = None

        self.setWindowTitle("编辑主机" if self._is_edit else "添加主机")
        self.setMinimumWidth(480)
        self._setup_ui()
        self._fill_data()

    def _setup_ui(self):
        """初始化 UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # --- 基本信息组 ---
        basic_group = QGroupBox("基本信息")
        basic_group.setStyleSheet("""
            QGroupBox {
                color: #333333;
                font-weight: bold;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """)
        basic_layout = QFormLayout(basic_group)
        basic_layout.setSpacing(12)
        basic_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("例如: 生产服务器-01")
        basic_layout.addRow("主机名 *:", self._name_input)

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("IP 地址或域名")
        basic_layout.addRow("IP / 域名 *:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(DEFAULT_SSH_PORT)
        basic_layout.addRow("SSH 端口:", self._port_input)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("登录用户名")
        basic_layout.addRow("用户名 *:", self._username_input)

        layout.addWidget(basic_group)

        # --- 认证信息组 ---
        auth_group = QGroupBox("认证方式")
        auth_group.setStyleSheet(basic_group.styleSheet())
        auth_layout = QVBoxLayout(auth_group)
        auth_layout.setSpacing(10)

        # 认证方式选择
        auth_type_layout = QHBoxLayout()
        auth_type_layout.setSpacing(16)
        auth_type_label = QLabel("方式:")
        auth_type_label.setFixedWidth(70)
        auth_type_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self._auth_combo = QComboBox()
        self._auth_combo.addItem("密码认证", "password")
        self._auth_combo.addItem("密钥认证", "key")
        self._auth_combo.currentIndexChanged.connect(self._on_auth_type_changed)
        auth_type_layout.addWidget(auth_type_label)
        auth_type_layout.addWidget(self._auth_combo)
        auth_layout.addLayout(auth_type_layout)

        # 密码输入
        self._password_input = QLineEdit()
        self._password_input.setPlaceholderText("输入 SSH 密码")
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_widget = QWidget()
        pw_layout = QHBoxLayout(self._password_widget)
        pw_layout.setContentsMargins(0, 0, 0, 0)
        pw_layout.setSpacing(8)
        pw_layout.addWidget(QLabel("密码:"))
        pw_layout.addWidget(self._password_input)

        self._btn_show_pw = QPushButton("显示")
        self._btn_show_pw.setFixedWidth(60)
        self._btn_show_pw.clicked.connect(self._toggle_password_visibility)
        pw_layout.addWidget(self._btn_show_pw)
        auth_layout.addWidget(self._password_widget)

        # 密钥路径输入
        self._key_widget = QWidget()
        key_layout = QHBoxLayout(self._key_widget)
        key_layout.setContentsMargins(0, 0, 0, 0)
        key_layout.setSpacing(8)
        key_layout.addWidget(QLabel("密钥:"))
        self._key_path_input = QLineEdit()
        self._key_path_input.setPlaceholderText("选择私钥文件 (.pem / .key)")
        key_layout.addWidget(self._key_path_input)
        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse_key_file)
        key_layout.addWidget(browse_btn)
        self._key_widget.setVisible(False)

        auth_layout.addWidget(self._key_widget)

        layout.addWidget(auth_group)

        # --- 其他信息组 ---
        other_group = QGroupBox("其他信息")
        other_group.setStyleSheet(basic_group.styleSheet())
        other_layout = QFormLayout(other_group)
        other_layout.setSpacing(12)
        other_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self._group_input = QLineEdit()
        self._group_input.setPlaceholderText(DEFAULT_GROUP)
        other_layout.addRow("分组:", self._group_input)

        self._remark_input = QTextEdit()
        self._remark_input.setPlaceholderText("备注信息（可选）")
        self._remark_input.setMaximumHeight(60)
        other_layout.addRow("备注:", self._remark_input)

        layout.addWidget(other_group)

        # --- 按钮 ---
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(90)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确认")
        ok_btn.setFixedWidth(90)
        ok_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 对话框样式
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
                color: #333333;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border: 1px solid #1976D2;
            }
            QLabel {
                color: #333333;
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
        """)

    def _fill_data(self):
        """编辑模式：填充已有数据"""
        if not self._is_edit:
            return

        d = self._host_data
        self._name_input.setText(d.get("name", ""))
        self._host_input.setText(d.get("host", ""))
        self._port_input.setValue(d.get("port", DEFAULT_SSH_PORT))
        self._username_input.setText(d.get("username", ""))

        auth_type = d.get("auth_type", "password")
        idx = 0 if auth_type == "password" else 1
        self._auth_combo.setCurrentIndex(idx)

        # 密码字段：编辑时留空，除非用户修改
        self._password_input.setPlaceholderText("留空则保持原密码不变")

        self._key_path_input.setText(d.get("key_path", ""))
        self._group_input.setText(d.get("group", DEFAULT_GROUP))
        self._remark_input.setPlainText(d.get("remark", ""))

    # ============ 事件处理 ============

    def _on_auth_type_changed(self, index: int):
        """认证方式切换"""
        is_password = index == 0
        self._password_widget.setVisible(is_password)
        self._key_widget.setVisible(not is_password)

    def _toggle_password_visibility(self):
        """切换密码可见性"""
        if self._password_input.echoMode() == QLineEdit.EchoMode.Password:
            self._password_input.setEchoMode(QLineEdit.EchoMode.Normal)
            self._btn_show_pw.setText("隐藏")
        else:
            self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._btn_show_pw.setText("显示")

    def _browse_key_file(self):
        """浏览选择密钥文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择私钥文件", "",
            "所有文件 (*.*) ;; PEM 文件 (*.pem) ;; 密钥文件 (*.key)",
        )
        if path:
            self._key_path_input.setText(path)

    def _on_confirm(self):
        """确认按钮点击"""
        name = self._name_input.text().strip()
        host = self._host_input.text().strip()
        username = self._username_input.text().strip()

        # 基本校验
        errors = []
        if not name:
            errors.append("主机名不能为空")
        if not host:
            errors.append("IP/域名不能为空")
        if not username:
            errors.append("用户名不能为空")

        auth_type = self._auth_combo.currentData()
        if auth_type == "password" and not self._is_edit and not self._password_input.text():
            errors.append("密码不能为空（新建主机时）")
        if auth_type == "key" and not self._key_path_input.text().strip():
            errors.append("密钥路径不能为空")

        if errors:
            QMessageBox.warning(self, "校验失败", "\n".join(errors))
            return

        # 收集结果
        self._result_data = {
            "name": name,
            "host": host,
            "port": self._port_input.value(),
            "username": username,
            "auth_type": auth_type,
            "password": self._password_input.text(),  # 明文，由 Service 层加密
            "key_path": self._key_path_input.text().strip(),
            "group": self._group_input.text().strip() or DEFAULT_GROUP,
            "remark": self._remark_input.toPlainText().strip(),
        }

        self.accept()

    def get_result(self) -> dict | None:
        """获取表单结果数据"""
        return self._result_data
