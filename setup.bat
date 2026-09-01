@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title 腾讯云 Token Plan 一键接入

echo.
echo   ╔══════════════════════════════════════════════╗
echo   ║   腾讯云 Token Plan — 一键接入              ║
echo   ╚══════════════════════════════════════════════╝
echo.

REM ── 1. 检测 Python（优先 py 启动器，其次 python） ──────────────
set "PY_CMD="
py -3 --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=py -3"
    goto :python_ok
)
python --version >nul 2>&1
if not errorlevel 1 (
    set "PY_CMD=python"
    goto :python_ok
)

echo   ❌ 未找到 Python 3
echo.
echo   请先安装 Python（任选其一）：
echo     1. Microsoft Store 搜索 "Python 3.12"
echo     2. https://www.python.org/downloads
echo     3. winget install Python.Python.3.12
echo   安装时请勾选 "Add python.exe to PATH"
echo.
pause
exit /b 1

:python_ok
echo   ✅ Python 已就绪 (%PY_CMD%)
echo.

REM ── 2. 下载主脚本（多镜像依次回退） ────────────────────────────
set "TMPFILE=%TEMP%\tokenplan-setup.py"

set "URL_1=https://cdn.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@main/setup.command"
set "URL_2=https://fastly.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@main/setup.command"
set "URL_3=https://raw.githubusercontent.com/zmq1121/tokenplan-quick-setup/main/setup.command"

echo   → 正在下载安装脚本...
set "DOWNLOADED="
for %%U in ("%URL_1%" "%URL_2%" "%URL_3%") do (
    if not defined DOWNLOADED (
        curl -fsSL --connect-timeout 10 %%U -o "%TMPFILE%" 2>nul
        if not errorlevel 1 (
            set "DOWNLOADED=1"
        )
    )
)

if not defined DOWNLOADED (
    echo   ❌ 所有下载源均失败，请检查网络连接
    echo.
    echo   可选镜像（手动下载后重命名为 setup.py 运行）：
    echo     %URL_1%
    echo     %URL_3%
    echo.
    pause
    exit /b 1
)

REM ── 3. 校验下载内容确实是 Python 脚本（防止镜像返回错误页） ────
findstr /C:"python3" /C:"import" "%TMPFILE%" >nul 2>&1
if errorlevel 1 (
    echo   ❌ 下载内容校验失败，文件可能不完整
    del "%TMPFILE%" >nul 2>&1
    pause
    exit /b 1
)
echo   ✅ 下载完成
echo.

REM ── 4. 运行（透传所有参数，如 doctor / --tools 等） ───────────
%PY_CMD% "%TMPFILE%" %*
set "EXITCODE=%ERRORLEVEL%"
del "%TMPFILE%" >nul 2>&1

if not "%EXITCODE%"=="0" (
    echo.
    echo   安装器退出码: %EXITCODE%
)

echo.
pause
endlocal
