@echo off
chcp 65001 >nul 2>&1
echo ========================================
echo   SSH Remote Tool - Build Script
echo ========================================
echo.

:: 1. 检查 Python
"C:\Program Files\Python314\python.exe" --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)

:: 2. 检查 PyInstaller
"C:\Program Files\Python314\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    "C:\Program Files\Python314\python.exe" -m pip install pyinstaller
)

:: 3. 清理旧构建
echo [1/3] Cleaning old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist installer rmdir /s /q installer

:: 4. PyInstaller 打包
echo [2/3] Building with PyInstaller...
"C:\Program Files\Python314\python.exe" -m PyInstaller ssh-remote-tool.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed!
    pause
    exit /b 1
)

:: 5. 统计体积
echo.
echo Build output:
if exist dist\SSHRemoteTool (
    echo   Output: dist\SSHRemoteTool\
    dir dist\SSHRemoteTool\SSHRemoteTool.exe 2>nul | find "SSHRemoteTool.exe"
)

echo.
echo [3/3] Inno Setup installer...
echo.
echo   PyInstaller build completed successfully!
echo   Output: dist\SSHRemoteTool\
echo.
echo   To create installer:
echo   1. Install Inno Setup from https://jrsoftware.org/isdl.php
echo   2. Open installer.iss with Inno Setup Compiler
echo   3. Click Build ^> Compile
echo   4. Output: installer\SSHRemoteTool-Setup-v0.1.0.exe
echo.
pause
