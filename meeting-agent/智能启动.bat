@echo off
chcp 65001 >nul
title 会议统筹智能体 - 智能启动器
color 0B

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║            🤖 会议统筹智能体 - 智能启动器                     ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

set PYTHON_CMD=

:: 尝试不同的Python命令
echo [检测] 正在寻找Python...
echo.

:: 1. 尝试python
python --version >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ 找到: python
    set PYTHON_CMD=python
    goto RUN
)

:: 2. 尝试py
py --version >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ 找到: py
    set PYTHON_CMD=py
    goto RUN
)

:: 3. 尝试python3
python3 --version >nul 2>&1
if %errorlevel% == 0 (
    echo ✓ 找到: python3
    set PYTHON_CMD=python3
    goto RUN
)

:: 4. 检查具体路径
if exist "C:\Python312\python.exe" (
    echo ✓ 找到: C:\Python312\python.exe
    set PYTHON_CMD=C:\Python312\python.exe
    goto RUN
)
if exist "C:\Python311\python.exe" (
    echo ✓ 找到: C:\Python311\python.exe
    set PYTHON_CMD=C:\Python311\python.exe
    goto RUN
)
if exist "C:\Python310\python.exe" (
    echo ✓ 找到: C:\Python310\python.exe
    set PYTHON_CMD=C:\Python310\python.exe
    goto RUN
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
    echo ✓ 找到: Python 3.12
    set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe
    goto RUN
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    echo ✓ 找到: Python 3.11
    set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
    goto RUN
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe" (
    echo ✓ 找到: Python 3.10
    set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe
    goto RUN
)

:: 没找到
goto NOTFOUND

:RUN
echo.
echo ═══════════════════════════════════════════════════════════════
echo ✅ 已找到Python，正在启动会议智能体...
echo ═══════════════════════════════════════════════════════════════
echo.

%PYTHON_CMD% meeting_simple.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误码: %errorlevel%
    echo.
    pause
)
exit

:NOTFOUND
echo.
echo ═══════════════════════════════════════════════════════════════
echo ❌ 未找到Python！
echo ═══════════════════════════════════════════════════════════════
echo.
echo 你的系统似乎没有安装Python。
echo.
echo ┌─────────────────────────────────────────────────────────────┐
echo │  解决方案：                                                 │
echo ├─────────────────────────────────────────────────────────────┤
echo │                                                             │
echo │  方法1：从官网下载安装（推荐）                              │
echo │  1. 访问：https://www.python.org/downloads/                 │
echo │  2. 点击 "Download Python 3.12.x"                          │
echo │  3. 运行下载的安装程序                                      │
echo │  4. ⚠️ 重要：勾选 "Add Python to PATH"                     │
echo │  5. 点击 Install Now                                        │
echo │  6. 安装完成后重新双击此文件                                │
echo │                                                             │
echo │  方法2：从Microsoft Store安装                               │
echo │  1. 打开Microsoft Store                                     │
echo │  2. 搜索 "Python"                                           │
echo │  3. 安装Python 3.11或3.12                                   │
echo │  4. 重新双击此文件                                          │
echo │                                                             │
echo └─────────────────────────────────────────────────────────────┘
echo.
echo 安装完成后，重新运行本程序即可。
echo.
pause
