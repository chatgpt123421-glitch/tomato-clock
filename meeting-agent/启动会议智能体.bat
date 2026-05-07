@echo off
chcp 65001 >nul
title 会议统筹智能体
color 0A

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                                                              ║
echo ║              🤖 会议统筹智能体 v1.0                           ║
echo ║                                                              ║
echo ║     正在启动...                                              ║
echo ║                                                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

python meeting_simple.py

if %errorlevel% neq 0 (
    echo.
    echo [错误] 无法运行Python脚本
    echo.
    echo 请确保:
    echo 1. 已安装Python 3.x
    echo 2. Python已添加到系统环境变量
    echo.
    pause
)
