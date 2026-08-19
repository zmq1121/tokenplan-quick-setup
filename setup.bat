@echo off
chcp 65001 >nul
title 腾讯云 Token Plan 一键接入

echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║   腾讯云 Token Plan — 小白一键接入          ║
echo   ╚══════════════════════════════════════════════╝
echo.

REM 检查 Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   ❌ 未安装 Python 3
    echo.
    echo   请先安装 Python：打开 Microsoft Store 搜索 "Python 3.12"
    echo   或访问 https://www.python.org/downloads
    echo.
    pause
    exit /b 1
)

echo   ✅ Python 已就绪
echo.

REM 下载并运行 setup.py
set "URL=https://raw.githubusercontent.com/zmq1121/tokenplan-quick-setup/main/setup.command"
set "TMPFILE=%TEMP%\tokenplan-setup.py"

echo   → 正在下载安装脚本...
curl -fsSL "%URL%" -o "%TMPFILE%" 2>nul
if %errorlevel% neq 0 (
    echo   ❌ 下载失败，请检查网络连接
    echo   手动下载: %URL%
    echo   保存为 setup.command 后双击运行
    pause
    exit /b 1
)

echo   ✅ 下载完成
echo.

python "%TMPFILE%"
del "%TMPFILE%" 2>nul

pause
