from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SSH Remote Tool - 程序入口

初始化应用配置、数据库、日志系统，启动主窗口。
"""

import sys
import os

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication, QToolTip
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QFont, QPalette, QColor

from config.settings import get_settings
from utils.logger import setup_logger
from data.database import init_db
from views.main_window import MainWindow


def _resource_path(relative_path: str) -> str:
    """获取资源文件绝对路径（兼容 PyInstaller 打包）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(PROJECT_ROOT, relative_path)


def main():
    """应用主入口"""

    # 1. 初始化配置
    settings = get_settings()

    # 2. 初始化日志
    logger = setup_logger("ssh_manager", settings.LOG_LEVEL)
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # 3. 初始化数据库
    init_db(settings.db_path)
    logger.info(f"Database initialized: {settings.db_path}")

    # 4. 启用高 DPI 缩放（必须在 QApplication 创建之前）
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # 5. 创建 Qt 应用
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 强制 Qt 自渲染，绕过 Windows 原生 API（修复 tooltip 黑方块问题）
    tooltip_styles = "QToolTip { background-color: #FFFFFF; color: #D32F2F; border: 1px solid #E0E0E0; padding: 6px; }"
    # 应用为应用级样式表（覆盖大部分情况）
    app.setStyleSheet(tooltip_styles)

    # QToolTip 不一定支持 setStyleSheet，使用调色板和字体做兼容性设置以确保生效
    try:
        palette = QPalette()
        palette.setColor(QPalette.ToolTipBase, QColor("#FFFFFF"))
        palette.setColor(QPalette.ToolTipText, QColor("#D32F2F"))
        app.setPalette(palette)
        QToolTip.setPalette(palette)
        QToolTip.setFont(QFont("Segoe UI", 9))
    except Exception:
        # 在极端环境中若方法不可用，继续使用应用样式表作为后备
        pass

    app.setApplicationName(settings.APP_NAME)
    app.setApplicationVersion(settings.APP_VERSION)

    # 设置应用图标
    icon_path = _resource_path("resources/icons/app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 6. 创建并显示主窗口
    window = MainWindow()
    window.show()

    logger.info("Application started successfully")

    # 7. 运行事件循环
    exit_code = app.exec()
    logger.info(f"Application exiting with code {exit_code}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
