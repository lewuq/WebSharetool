@echo off
title SeeedShareTool Launcher
echo 正在检查系统环境...

:: 1. 检测 Python 是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Python 环境！
    echo 正在为您打开 Python 下载页面，请安装后再运行本工具。
    echo 注意：安装时请务必勾选 [Add Python to PATH] 选项。
    start https://www.python.org/downloads/
    pause
    exit
)

:: 2. 检测 Flask 是否安装
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo [提示] 检测到缺少 Flask 库。
    echo 正在自动安装 Flask...
    pip install flask -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo [错误] Flask 安装失败，请检查网络。
        pause
        exit
    )
    echo Flask 安装成功！
) else (
    echo 环境检查通过：Python 和 Flask 已就绪。
)

echo ------------------------------------------
echo 正在启动工具...
python WebShareTool.py
pause