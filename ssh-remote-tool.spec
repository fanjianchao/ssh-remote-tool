# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec - SSH Remote Tool (单目录模式)
"""

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT_ROOT = os.path.abspath(SPECPATH)

block_cipher = None

# 需要打包的资源文件
datas = [
    (os.path.join(PROJECT_ROOT, 'resources'), 'resources'),
]

# 隐式导入（PyInstaller 无法自动检测的模块）
hiddenimports = [
    'paramiko',
    'cryptography',
    'cryptography.hazmat.backends.openssl',
    'cryptography.hazmat.primitives.serialization',
    'sqlalchemy',
    'pynacl',
    'nacl',
    '_cffi_backend',
]

# 需要排除的模块（减小体积）
excludes = [
    'tkinter',
    'unittest',
    'xmlrpc',
    'pydoc',
    'distutils',
    'setuptools',
    'pip',
    'IPython',
    'jupyter',
    'notebook',
    'matplotlib',
    'numpy',
    'pandas',
    'scipy',
    'pytest',
    'PySide6.QtMultimedia',
    'PySide6.Qt3DCore',
    'PySide6.Qt3DExtras',
    'PySide6.Qt3DInput',
    'PySide6.Qt3DRender',
    'PySide6.QtBluetooth',
    'PySide6.QtNfc',
    'PySide6.QtPositioning',
    'PySide6.QtSensors',
    'PySide6.QtSerialPort',
    'PySide6.QtWebChannel',
    'PySide6.QtWebEngine',
    'PySide6.QtWebSockets',
    'PySide6.QtQuick',
    'PySide6.QtQml',
    'PySide6.QtRemoteObjects',
    'PySide6.QtStateMachine',
    'PySide6.QtTextToSpeech',
    'PySide6.QtHelp',
    'PySide6.QtSql',
    'PySide6.QtOpenGL',
]

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SSHRemoteTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # GUI 程序，不显示控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(PROJECT_ROOT, 'resources', 'icons', 'app.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SSHRemoteTool',
)
