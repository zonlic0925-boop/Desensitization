@echo off
chcp 65001 >nul
title 工程图纸脱敏系统
echo 正在启动工程图纸脱敏系统交互界面...
python main_ui.py
if %errorlevel% neq 0 (
    echo.
    echo 启动失败，请检查 Python 环境与依赖是否已安装：
    echo pip install -r requirements.txt
    pause
)
