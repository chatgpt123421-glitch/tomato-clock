@echo off
chcp 65001 >nul
title 环境检查
color 0E

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                    🔍 Python环境检查                          ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

:: 检查python命令
echo [1/4] 检查 "python" 命令...
python --version >nul 2>&1
if %errorlevel% == 0 (
    echo      ✓ python 可用
    python --version
    goto FOUND
) else (
    echo      ✗ python 不可用
)

:: 检查py命令
echo.
echo [2/4] 检查 "py" 命令...
py --version >nul 2>&1
if %errorlevel% == 0 (
    echo      ✓ py 可用
    py --version
    set PYTHON_CMD=py
    goto FOUND
) else (
    echo      ✗ py 不可用
)

:: 检查Python常见安装路径
echo.
echo [3/4] 检查常见安装路径...
set FOUND_PATH=

if exist "C:\Python312\python.exe" (
    set FOUND_PATH=C:\Python312\python.exe
    goto PATH_FOUND
)
if exist "C:\Python311\python.exe" (
    set FOUND_PATH=C:\Python311\python.exe
    goto PATH_FOUND
)
if exist "C:\Python310\python.exe" (
    set FOUND_PATH=C:\Python310\python.exe
    goto PATH_FOUND
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe" (
    set FOUND_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312\python.exe
    goto PATH_FOUND
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe" (
    set FOUND_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python311\python.exe
    goto PATH_FOUND
)
if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe" (
    set FOUND_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python310\python.exe
    goto PATH_FOUND
)

:PATH_FOUND
if defined FOUND_PATH (
    echo      ✓ 找到Python: %FOUND_PATH%
    "%FOUND_PATH%" --version
    goto FOUND
) else (
    echo      ✗ 未在常见路径找到Python
)

:: 检查Microsoft Store Python
echo.
echo [4/4] 检查Microsoft Store Python...
if exist "C:\Users\%USERNAME%\AppData\Local\Microsoft\WindowsApps\python.exe" (
    echo      ⚠ 找到Microsoft Store Python
    echo        这可能是假执行文件，需要安装实际Python
    goto MSSTORE
) else (
    echo      ✗ 未找到
)

echo.
echo ═══════════════════════════════════════════════════════════════
echo ❌ 未找到可用的Python安装
echo ═══════════════════════════════════════════════════════════════
echo.
echo 解决方案:
echo 1. 安装Python: https://www.python.org/downloads/
echo 2. 安装时勾选 "Add Python to PATH"
echo 3. 重新打开命令提示符再试
echo.
pause
exit

:MSSTORE
echo.
echo ═══════════════════════════════════════════════════════════════
echo ⚠️ 检测到Microsoft Store占位符
echo ═══════════════════════════════════════════════════════════════
echo.
echo 说明: 你的系统上有Python的快捷方式，但没有实际安装
echo.
echo 解决方案:
echo 1. 从Microsoft Store安装Python，或者
echo 2. 从官网下载安装: https://www.python.org/downloads/
echo.
echo 推荐: 从官网下载安装，更稳定
echo.
pause
exit

:FOUND
echo.
echo ═══════════════════════════════════════════════════════════════
echo ✅ Python环境正常！
echo ═══════════════════════════════════════════════════════════════
echo.
echo 现在可以运行会议智能体了！
echo.
pause
