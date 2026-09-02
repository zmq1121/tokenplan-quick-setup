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

REM ── 2. 下载主脚本（固定版本镜像，多源回退） ────────────────────
REM SETUP_VERSION / SETUP_SHA256 由 scripts/sync_npm_lib.py 自动注入,
REM 手动修改无效——修改 setup.command 后必须重新运行同步脚本。
set "SETUP_VERSION=2.2.0"
set "SETUP_SHA256=ae607ccb2b94781b59916a4feab04196890b5dd18776611e223ae84c9613f2bc"

set "TMPFILE=%TEMP%\tokenplan-setup.py"

set "URL_1=https://github.com/zmq1121/tokenplan-quick-setup/releases/download/v%SETUP_VERSION%/setup.command"
set "URL_2=https://cdn.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@v%SETUP_VERSION%/setup.command"
set "URL_3=https://fastly.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@v%SETUP_VERSION%/setup.command"

echo   → 正在下载安装脚本 (v%SETUP_VERSION%)...
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
    echo     %URL_2%
    echo.
    pause
    exit /b 1
)

REM ── 3. SHA256 完整性校验（防镜像篡改/损坏） ────────────────────
set "FILE_HASH="
for /f "skip=1 tokens=1 delims= " %%H in ('certutil -hashfile "%TMPFILE%" SHA256 2^>nul ^| findstr /r /i "^[0-9a-f][0-9a-f]*$"') do (
    if not defined FILE_HASH set "FILE_HASH=%%H"
)

if /i not "%FILE_HASH%"=="%SETUP_SHA256%" (
    echo   ❌ 完整性校验失败：下载内容与 v%SETUP_VERSION% 预期不符
    echo      文件可能损坏或镜像被篡改，已中止运行。
    echo.
    echo   请从官方 Release 重新获取 setup.bat：
    echo     https://github.com/zmq1121/tokenplan-quick-setup/releases
    del "%TMPFILE%" >nul 2>&1
    pause
    exit /b 1
)
echo   ✅ SHA256 校验通过
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
