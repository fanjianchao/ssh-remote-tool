from __future__ import annotations
# -*- coding: utf-8 -*-
"""
步骤编辑弹窗

编辑单个步骤的配置：类型、名称、命令/SFTP参数、超时、目标主机。
支持新建和编辑两种模式，点击确认后返回步骤数据字典。
"""

from PySide6.QtWidgets import (
    QDialog, QWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLineEdit, QSpinBox, QComboBox, QTextEdit, QPushButton,
    QLabel, QGroupBox, QFileDialog, QCheckBox, QSizePolicy,
)
from PySide6.QtCore import Qt

from config.constants import DEFAULT_SSH_TIMEOUT, DEFAULT_WORKDIR


class StepEditDialog(QDialog):
    """步骤编辑弹窗"""

    def __init__(self, parent=None, step_data: dict | None = None,
                 available_hosts: list[dict] | None = None):
        """
        Args:
            parent: 父窗口
            step_data: 编辑模式时传入的步骤数据字典；新建时为 None
            available_hosts: 可用主机列表（用于目标主机选择）
        """
        super().__init__(parent)
        self._available_hosts = available_hosts or []
        self._result: dict | None = None
        self._setup_ui()
        if step_data:
            self._load_data(step_data)

    def _setup_ui(self):
        """初始化 UI"""
        self.setWindowTitle("编辑步骤")
        self.setMinimumWidth(520)
        self.setMinimumHeight(500)
        self.setMaximumHeight(720)
        self.setStyleSheet("background-color: #FFFFFF; color: #333333;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ---- 步骤类型 ----
        type_hbox = QHBoxLayout()
        type_label = QLabel("步骤类型:")
        type_label.setFixedWidth(72)
        type_label.setStyleSheet("color: #333333; font-size: 13px; font-weight: bold;")
        type_hbox.addWidget(type_label)
        self._step_type_combo = QComboBox()
        self._step_type_combo.addItem("⌨️ 命令执行", "ssh_command")
        self._step_type_combo.addItem("📤 文件上传", "sftp_upload")
        self._step_type_combo.addItem("📥 文件下载", "sftp_download")
        self._step_type_combo.setStyleSheet(self._combo_style())
        self._step_type_combo.currentIndexChanged.connect(self._on_step_type_changed)
        type_hbox.addWidget(self._step_type_combo)
        type_hbox.addStretch()
        layout.addLayout(type_hbox)

        # ---- 步骤名称 ----
        name_hbox = QHBoxLayout()
        name_label = QLabel("步骤名称:")
        name_label.setFixedWidth(72)
        name_label.setStyleSheet("color: #333333; font-size: 13px; font-weight: bold;")
        name_hbox.addWidget(name_label)
        self._step_name_input = QLineEdit()
        self._step_name_input.setPlaceholderText("例如: 重启 Nginx")
        self._step_name_input.setStyleSheet(self._input_style())
        name_hbox.addWidget(self._step_name_input)
        layout.addLayout(name_hbox)

        # ---- SSH 命令配置（QGridLayout 精确控制）----
        self._ssh_group = QGroupBox("命令配置")
        self._ssh_group.setStyleSheet(self._group_style())
        ssh_grid = QGridLayout(self._ssh_group)
        ssh_grid.setSpacing(8)
        ssh_grid.setContentsMargins(12, 16, 12, 12)

        # Row 0: Shell 命令标签
        cmd_label = QLabel("Shell 命令:")
        cmd_label.setStyleSheet("color: #666666; font-size: 12px;")
        ssh_grid.addWidget(cmd_label, 0, 0, 1, 4)

        # Row 1: 命令输入框
        self._command_input = QTextEdit()
        self._command_input.setPlaceholderText("输入要执行的命令...")
        self._command_input.setFixedHeight(90)
        self._command_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._command_input.setStyleSheet("""
            QTextEdit {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 6px;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QTextEdit:focus { border-color: #1976D2; }
        """)
        ssh_grid.addWidget(self._command_input, 1, 0, 1, 4)

        # Row 2: 超时(秒) | 工作目录
        # 超时
        timeout_label = QLabel("超时(秒):")
        timeout_label.setStyleSheet("color: #666666; font-size: 12px;")
        timeout_label.setFixedWidth(72)
        ssh_grid.addWidget(timeout_label, 2, 0)
        self._timeout_input = QSpinBox()
        self._timeout_input.setRange(0, 3600)
        self._timeout_input.setValue(DEFAULT_SSH_TIMEOUT)
        self._timeout_input.setSuffix(" 秒")
        # 移除原生上下按钮，使用自定义小按钮以保证在各平台一致显示
        self._timeout_input.setButtonSymbols(QSpinBox.NoButtons)
        self._timeout_input.setStyleSheet(self._input_style())
        self._timeout_input.setFixedWidth(88)
        self._timeout_input.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # 包装到一个带垂直按钮的容器中
        timeout_widget = QWidget()
        timeout_h = QHBoxLayout(timeout_widget)
        timeout_h.setContentsMargins(0, 0, 0, 0)
        timeout_h.setSpacing(4)
        timeout_h.addWidget(self._timeout_input)
        btn_col = QWidget()
        btn_col.setFixedWidth(36)
        btn_layout = QVBoxLayout(btn_col)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(2)
        _spin_btn_style = (
            "QPushButton {"
            "  background-color: #D6D6D6;"
            "  border: 1px solid #AAAAAA;"
            "  color: #000000;"
            "  font-family: Arial, sans-serif;"
            "  font-size: 14px;"
            "  font-weight: bold;"
            "  border-radius: 3px;"
            "  padding: 0px;"
            "}"
            "QPushButton:hover { background-color: #BBBBBB; }"
            "QPushButton:pressed { background-color: #999999; }"
        )
        btn_up = QPushButton("+")
        btn_up.setFixedSize(24, 18)
        btn_up.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_up.setToolTip("增加超时时间")
        btn_up.setStyleSheet(_spin_btn_style)
        btn_down = QPushButton("\u2212")  # Unicode 减号 −，比连字符更宽更清晰
        btn_down.setFixedSize(24, 18)
        btn_down.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_down.setToolTip("减少超时时间")
        btn_down.setStyleSheet(_spin_btn_style)
        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        timeout_h.addWidget(btn_col)
        timeout_widget.setMinimumWidth(180)
        timeout_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        ssh_grid.addWidget(timeout_widget, 2, 1)
        # 按钮行为：调用 spinbox 的 stepUp/stepDown
        btn_up.clicked.connect(lambda: self._timeout_input.stepUp())
        btn_down.clicked.connect(lambda: self._timeout_input.stepDown())
        # 不让第 1 列无限拉伸以避免按钮被挤出
        ssh_grid.setColumnStretch(1, 0)

        # 工作目录
        workdir_label = QLabel("工作目录:")
        workdir_label.setStyleSheet("color: #666666; font-size: 12px;")
        workdir_label.setFixedWidth(72)
        ssh_grid.addWidget(workdir_label, 2, 2)
        self._workdir_input = QLineEdit()
        self._workdir_input.setText(DEFAULT_WORKDIR)
        self._workdir_input.setStyleSheet(self._input_style())
        ssh_grid.addWidget(self._workdir_input, 2, 3)
        ssh_grid.setColumnStretch(3, 2)

        layout.addWidget(self._ssh_group)

        # ---- SFTP 配置 ----
        self._sftp_group = QGroupBox("文件传输配置")
        self._sftp_group.setStyleSheet(self._group_style())
        sftp_layout = QFormLayout(self._sftp_group)
        sftp_layout.setSpacing(8)
        sftp_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # 本地路径（输入框 + 浏览按钮）
        local_row = QHBoxLayout()
        local_row.setSpacing(6)
        self._local_path_input = QLineEdit()
        self._local_path_input.setPlaceholderText("/path/to/local/file")
        self._local_path_input.setStyleSheet(self._input_style())
        local_row.addWidget(self._local_path_input)
        btn_browse_local = QPushButton("📁")
        btn_browse_local.setFixedSize(30, 30)
        btn_browse_local.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_browse_local.setToolTip("浏览本地文件/目录")
        self._btn_browse_local = btn_browse_local
        btn_browse_local.clicked.connect(self._browse_local_path)
        btn_browse_local.setStyleSheet("""
            QPushButton {
                background-color: #D0D0D0; color: #333333;
                border: none; border-radius: 4px; font-size: 14px;
            }
            QPushButton:hover { background-color: #BDBDBD; }
        """)
        local_row.addWidget(btn_browse_local)
        sftp_layout.addRow(QLabel("本地路径:"), local_row)

        self._remote_path_input = QLineEdit()
        self._remote_path_input.setPlaceholderText("/path/to/remote/file")
        self._remote_path_input.setStyleSheet(self._input_style())
        sftp_layout.addRow(QLabel("远程路径:"), self._remote_path_input)

        layout.addWidget(self._sftp_group)
        self._sftp_group.setVisible(False)

        # ---- 执行策略 ----
        strategy_group = QGroupBox("执行策略")
        strategy_group.setStyleSheet(self._group_style())
        strategy_layout = QVBoxLayout(strategy_group)
        strategy_layout.setSpacing(6)

        # 使用标准 QCheckBox，外层容器保持结构一致
        cont_widget = QWidget()
        cont_layout = QHBoxLayout(cont_widget)
        cont_layout.setContentsMargins(0, 0, 0, 0)
        cont_layout.setSpacing(8)

        # 使用标准 QCheckBox，QSS 放大 indicator 以确保视觉尺寸清晰
        self._continue_on_error_cb = QCheckBox("步骤执行失败后，继续执行下一步")
        self._continue_on_error_cb.setStyleSheet("""
            QCheckBox {
                color: #333333;
                font-size: 13px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border: 2px solid #BDBDBD;
                border-radius: 3px;
                background-color: #FFFFFF;
            }
            QCheckBox::indicator:hover {
                border-color: #1976D2;
            }
            QCheckBox::indicator:checked {
                background-color: #1976D2;
                border-color: #1976D2;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #1565C0;
                border-color: #1565C0;
            }
        """)
        self._continue_on_error_cb.setChecked(False)
        cont_layout.addWidget(self._continue_on_error_cb)
        strategy_layout.addWidget(cont_widget)
        hint_label = QLabel("默认：步骤失败后停止该主机后续步骤")
        hint_label.setStyleSheet("color: #999999; font-size: 11px; margin-left: 24px;")
        strategy_layout.addWidget(hint_label)

        layout.addWidget(strategy_group)

        # 弹性空间：把按钮栏推到底部，防止高 DPI 下布局散开
        layout.addStretch(1)

        # ---- 底部按钮 ----
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(12)

        btn_cancel = QPushButton("取消")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #E0E0E0;
                color: #333333;
                border: 1px solid #D0D0D0;
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #D0D0D0; }
        """)
        btn_bar.addWidget(btn_cancel)

        btn_bar.addStretch()

        btn_confirm = QPushButton("确认")
        btn_confirm.setFixedHeight(36)
        btn_confirm.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_confirm.clicked.connect(self._on_confirm)
        btn_confirm.setStyleSheet("""
            QPushButton {
                background-color: #1976D2;
                color: #FFFFFF;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #1565C0; }
        """)
        btn_bar.addWidget(btn_confirm)

        layout.addLayout(btn_bar)

    def _load_data(self, step: dict):
        """加载步骤数据到编辑面板"""
        type_idx = self._step_type_combo.findData(step.get("step_type", "ssh_command"))
        if type_idx >= 0:
            self._step_type_combo.setCurrentIndex(type_idx)

        self._step_name_input.setText(step.get("name", ""))
        self._command_input.setPlainText(step.get("command", ""))
        self._timeout_input.setValue(step.get("timeout", DEFAULT_SSH_TIMEOUT))
        self._workdir_input.setText(step.get("workdir", DEFAULT_WORKDIR))
        self._local_path_input.setText(step.get("local_path", ""))
        self._remote_path_input.setText(step.get("remote_path", ""))
        self._continue_on_error_cb.setChecked(step.get("continue_on_error", False))

    def _browse_local_path(self):
        """浏览本地路径，根据步骤类型区分行为"""
        step_type = self._step_type_combo.currentData()
        current = self._local_path_input.text().strip()
        initial_dir = current if current else ""

        if step_type == "sftp_download":
            # 下载：选择本地目录，自动拼接远程文件名
            path = QFileDialog.getExistingDirectory(
                self, "选择下载到本地的目标文件夹", initial_dir
            )
            if path:
                remote = self._remote_path_input.text().strip().rstrip("/")
                # 取远程路径最后一段作为文件/文件夹名
                remote_name = remote.rsplit("/", 1)[-1] if remote else ""
                if remote_name:
                    self._local_path_input.setText(
                        path.replace("\\", "/") + "/" + remote_name
                    )
                else:
                    self._local_path_input.setText(path.replace("\\", "/"))
        else:
            # 上传：先选文件，取消后选目录
            path, _ = QFileDialog.getOpenFileName(
                self, "选择本地文件", initial_dir, "所有文件 (*)"
            )
            if not path:
                path = QFileDialog.getExistingDirectory(
                    self, "选择本地目录", initial_dir
                )
            if path:
                self._local_path_input.setText(path.replace("\\", "/"))

    def _on_step_type_changed(self, index: int):
        """步骤类型切换"""
        step_type = self._step_type_combo.currentData()
        is_ssh = step_type == "ssh_command"
        self._ssh_group.setVisible(is_ssh)
        self._sftp_group.setVisible(not is_ssh)
        if step_type == "sftp_download":
            self._btn_browse_local.setToolTip("选择下载目标文件夹（自动拼接远程文件名）")
        else:
            self._btn_browse_local.setToolTip("浏览本地文件/目录")

    def _collect_data(self) -> dict:
        """收集编辑面板的数据"""
        return {
            "step_type": self._step_type_combo.currentData(),
            "name": self._step_name_input.text().strip() or "未命名步骤",
            "command": self._command_input.toPlainText().strip(),
            "timeout": self._timeout_input.value(),
            "workdir": self._workdir_input.text().strip() or DEFAULT_WORKDIR,
            "local_path": self._local_path_input.text().strip(),
            "remote_path": self._remote_path_input.text().strip(),
            "continue_on_error": self._continue_on_error_cb.isChecked(),
            "target_host_ids": [],
        }

    def _on_confirm(self):
        """确认按钮"""
        self._result = self._collect_data()
        self.accept()

    def get_result(self) -> dict | None:
        """获取编辑结果（确认后返回数据字典，取消返回 None）"""
        return self._result

    # ============ 样式工具 ============

    @staticmethod
    def _group_style() -> str:
        return """
            QGroupBox {
                color: #333333;
                font-weight: bold;
                font-size: 13px;
                border: 1px solid #E0E0E0;
                border-radius: 6px;
                margin-top: 10px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
        """

    @staticmethod
    def _input_style() -> str:
        return """
            QLineEdit, QSpinBox {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 12px;
            }
            QLineEdit:focus, QSpinBox:focus { border-color: #1976D2; }
            /* Spinbox arrows */
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px;
                subcontrol-origin: padding;
                subcontrol-position: right;
            }
            QSpinBox::up-arrow {
                image: url("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D'http%3A//www.w3.org/2000/svg'%20viewBox%3D'0%200%2024%2024'%3E%3Cpath%20d%3D'M6%2015l6-6%206%206'%20stroke%3D'%23333'%20stroke-width%3D'2'%20fill%3D'none'/%3E%3C/svg%3E");
                width: 12px;
                height: 12px;
                background-repeat: no-repeat;
                background-position: center;
            }
            QSpinBox::down-arrow {
                image: url("data:image/svg+xml;utf8,%3Csvg%20xmlns%3D'http%3A//www.w3.org/2000/svg'%20viewBox%3D'0%200%2024%2024'%3E%3Cpath%20d%3D'M6%209l6%206%206-6'%20stroke%3D'%23333'%20stroke-width%3D'2'%20fill%3D'none'/%3E%3C/svg%3E");
                width: 12px;
                height: 12px;
                background-repeat: no-repeat;
                background-position: center;
            }
        """

    @staticmethod
    def _combo_style() -> str:
        return """
            QComboBox {
                background-color: #F5F5F5;
                color: #333333;
                border: 1px solid #D0D0D0;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
            }
            QComboBox:focus { border-color: #1976D2; }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #E0E0E0;
                color: #333333;
                selection-background-color: #E0E0E0;
            }
        """
