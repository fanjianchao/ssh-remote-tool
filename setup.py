from __future__ import annotations
# -*- coding: utf-8 -*-
"""
SSH Remote Tool - 打包配置
"""

from setuptools import setup, find_packages

setup(
    name="ssh-remote-tool",
    version="0.1.0",
    description="SSH 远程运维工具 - 批量主机管理、文件传输和命令执行",
    author="SSH Remote Tool",
    python_requires=">=3.10",
    packages=find_packages(),
    install_requires=[
        "PySide6>=6.6.0",
        "paramiko>=3.4.0",
        "SQLAlchemy>=2.0.0",
        "cryptography>=42.0.0",
        "colorlog>=6.8.0",
    ],
    entry_points={
        "console_scripts": [
            "ssh-remote-tool=main:main",
        ],
    },
)
